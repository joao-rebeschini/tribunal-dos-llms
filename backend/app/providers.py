import asyncio
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import httpx

class ProviderError(Exception):
    pass

class SearchUnavailable(ProviderError):
    pass

def free_model(model):
    pricing = model.get('pricing', {})
    try:
        return pricing.get('prompt') is not None and pricing.get('completion') is not None and 'text' in model.get('architecture', {}).get('output_modalities', ['text']) and all(
            Decimal(str(v)) == 0 for v in pricing.values() if v is not None
        )
    except (InvalidOperation, ValueError):
        return False

def safe_url(url):
    parsed = urlparse(url)
    return parsed.scheme in ('https', 'http') and bool(parsed.netloc)

class OpenRouter:
    def __init__(self, key, client=None):
        self.key = key
        self.client = client or httpx.AsyncClient(timeout=90)

    async def models(self):
        try:
            response = await self.client.get('https://openrouter.ai/api/v1/models')
            response.raise_for_status()
            return sorted([{'id': m['id'], 'name': m['name']} for m in response.json()['data']
                           if free_model(m) and m['id'] != 'openrouter/free'], key=lambda x: x['name'])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderError('Não foi possível consultar o catálogo de modelos gratuitos.') from exc

    async def complete(self, model, system, context, schema):
        if not self.key:
            raise ProviderError('Configure OPENROUTER_API_KEY no ambiente do backend.')
        # Revalida preços antes de toda chamada. Não usa roteador nem fallback de modelo.
        if model not in {m['id'] for m in await self.models()}:
            raise ProviderError('Modelo indisponível ou com preço diferente de zero. Partida interrompida.')
        payload = {'model': model, 'messages': [
            {'role': 'system', 'content': system + '\nResponda somente JSON neste esquema: ' + json.dumps(schema.model_json_schema(), ensure_ascii=False)},
            {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}],
            'max_tokens': 1400, 'temperature': 0.4,
            'provider': {'allow_fallbacks': False, 'max_price': {'prompt': 0, 'completion': 0, 'request': 0, 'image': 0}}}
        for attempt in range(3):
            try:
                response = await self.client.post('https://openrouter.ai/api/v1/chat/completions',
                    headers={'Authorization': f'Bearer {self.key}', 'X-Title': 'Tribunal dos LLMs'}, json=payload)
                if response.status_code in (402, 429):
                    raise ProviderError('Cota ou capacidade gratuita esgotada. Progresso preservado; nenhum modelo pago foi usado.')
                if response.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if response.status_code >= 400:
                    raise ProviderError('O provedor recusou a chamada. Verifique chave e disponibilidade do modelo.')
                data = response.json()
                actual = data.get('model')
                if actual not in {model, model.removesuffix(':free')}:
                    raise ProviderError('O provedor retornou um modelo diferente do selecionado; execução interrompida.')
                content = data['choices'][0]['message']['content']
                content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
                try:
                    result = schema.model_validate_json(content)
                except ValueError:
                    if attempt < 2:
                        payload['messages'].append({'role': 'user', 'content': 'Corrija a resposta: JSON válido, esquema exato e até 180 palavras em text.'})
                        continue
                    raise ProviderError('O modelo não respondeu no formato esperado após três tentativas.')
                return result.model_dump(), actual
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise ProviderError('Falha temporária de conexão após três tentativas. Progresso preservado.') from exc
                await asyncio.sleep(2 ** attempt)
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError('Resposta inválida do provedor. Progresso preservado.') from exc
        raise ProviderError('O provedor não concluiu a chamada.')

class Tavily:
    def __init__(self, key, store, budget=1000, client=None):
        self.key, self.store, self.budget = key, store, min(max(budget, 0), 1000)
        self.client = client or httpx.AsyncClient(timeout=30)

    async def search(self, query):
        query = ' '.join(query.lower().split())
        cached = self.store.cached(query)
        if cached is not None:
            return cached
        if not self.key:
            raise SearchUnavailable('Pesquisa indisponível: configure TAVILY_API_KEY. A afirmação permanece inconclusiva.')
        headers = {'Authorization': f'Bearer {self.key}'}
        try:
            usage_response = await self.client.get('https://api.tavily.com/usage', headers=headers)
            if usage_response.status_code != 200:
                raise SearchUnavailable('Não foi possível confirmar a cota gratuita do Tavily; busca bloqueada.')
            account = usage_response.json().get('account', {})
            if (str(account.get('current_plan', '')).lower() not in ('free', 'researcher') or
                float(account.get('paygo_limit', -1)) != 0 or
                float(account.get('paygo_usage', -1)) != 0 or
                float(account.get('plan_usage', 1000)) >= min(float(account.get('plan_limit', 0)), self.budget)):
                raise SearchUnavailable('Tavily fora da cota gratuita ou com cobrança por uso habilitada; busca bloqueada.')
            if not self.store.reserve_search(self.budget):
                raise SearchUnavailable('Orçamento mensal local de buscas esgotado. A afirmação permanece inconclusiva.')
            # Uma chamada = um crédito basic. Nunca repete POST incerto para não duplicar gastos.
            response = await self.client.post('https://api.tavily.com/search', headers=headers, json={
                'query': query, 'search_depth': 'basic', 'auto_parameters': False,
                'max_results': 3, 'include_answer': False, 'include_raw_content': False, 'include_usage': True})
            if response.status_code != 200:
                raise SearchUnavailable('Pesquisa indisponível ou cota esgotada. Nenhuma evidência foi inventada.')
            results = [{'id': i, 'title': r.get('title', 'Fonte'), 'url': r['url'],
                        'content': r.get('content', '')[:2500]}
                       for i, r in enumerate(response.json().get('results', [])) if safe_url(r.get('url', ''))]
            self.store.cache(query, results)
            return results
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise SearchUnavailable('Falha ao consultar a pesquisa; afirmação inconclusiva.') from exc
