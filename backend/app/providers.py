"""Adaptadores HTTP do OpenRouter e Tavily com validação e bloqueios de custo.

Erros esperados usam ProviderError; falhas de busca usam SearchUnavailable para preservar o debate."""

import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import httpx

class ProviderError(Exception):
    def __init__(self, message, code='provider_error', details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

class SearchUnavailable(ProviderError):
    pass

def free_model(model):
    """Aceita apenas saída textual e preços declarados iguais a zero em todas as taxas."""
    pricing = model.get('pricing', {})
    try:
        return pricing.get('prompt') is not None and pricing.get('completion') is not None and 'text' in model.get('architecture', {}).get('output_modalities', ['text']) and all(
            Decimal(str(v)) == 0 for v in pricing.values() if v is not None
        )
    except (InvalidOperation, ValueError):
        return False

def safe_url(url):
    """Filtra URLs de fontes por esquema HTTP(S) e host; não verifica a confiabilidade editorial."""
    parsed = urlparse(url)
    return parsed.scheme in ('https', 'http') and bool(parsed.netloc)

def output_example(schema):
    """Mostra uma instância de dados, evitando que o modelo devolva o JSON Schema."""
    definition = schema.model_json_schema()
    def sample(node):
        if '$ref' in node:
            return sample(definition['$defs'][node['$ref'].split('/')[-1]])
        if 'enum' in node:
            return node['enum'][0]
        kind = node.get('type')
        if kind == 'object':
            properties = node.get('properties', {})
            if properties:
                return {name: sample(value) for name, value in properties.items()}
            names = node.get('propertyNames', {}).get('enum', [])
            return {name: sample(node['additionalProperties']) for name in names}
        if kind == 'array':
            return [sample(node['items'])]
        if kind == 'boolean':
            return False
        if kind in ('number', 'integer'):
            return max(node.get('minimum', 0), 0)
        return 'Substitua pelo conteúdo correspondente ao contexto.'
    return sample(definition)

class OpenRouter:
    def __init__(self, key, client=None):
        self.key = key
        self.client = client or httpx.AsyncClient(timeout=90)

    async def limits(self):
        """Consulta o contador diário da conta e devolve apenas franquia e renovação prevista UTC."""
        try:
            response = await self.client.get('https://openrouter.ai/api/v1/key',
                headers={'Authorization': f'Bearer {self.key}'})
            response.raise_for_status()
            daily = response.json().get('data', {}).get('free_model_daily_requests')
            if not isinstance(daily, dict):
                return {'daily': None, 'reset_at': None}
            values = {name: daily.get(name) for name in ('used', 'limit', 'remaining')}
            if any(not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 for value in values.values()):
                raise ValueError('Contador diário inválido.')
            now = datetime.now(timezone.utc)
            reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            return {'daily': values, 'reset_at': reset.isoformat()}
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ProviderError('Não foi possível consultar a franquia gratuita do OpenRouter.', code='provider_limits_unavailable') from exc

    async def models(self):
        """Consulta e filtra o catálogo atual, preservando capacidades necessárias à geração."""
        try:
            response = await self.client.get('https://openrouter.ai/api/v1/models')
            response.raise_for_status()
            return sorted([{'id': m['id'], 'name': m['name'],
                            'reasoning': m.get('reasoning'),
                            'supported_parameters': m.get('supported_parameters', []),
                            'max_completion_tokens': (m.get('top_provider') or {}).get('max_completion_tokens')}
                           for m in response.json()['data']
                           if free_model(m) and m['id'] != 'openrouter/free'], key=lambda x: x['name'])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderError('Não foi possível consultar o catálogo de modelos gratuitos.') from exc

    async def complete(self, model, system, context, schema):
        """Revalida o modelo gratuito, gera JSON e valida o schema em até três tentativas.
        
        Não troca de modelo nem usa raciocínio interno como fala. Cotas interrompem a execução."""
        if not self.key:
            raise ProviderError('Configure OPENROUTER_API_KEY no ambiente do backend.')
        # Revalida preços antes de toda chamada. Não usa roteador nem fallback de modelo.
        selected = next((m for m in await self.models() if m['id'] == model), None)
        if selected is None:
            raise ProviderError('Modelo indisponível ou com preço diferente de zero. Partida interrompida.')
        output_limit = selected.get('max_completion_tokens') or 16384
        payload = {'model': model, 'messages': [
            {'role': 'system', 'content': system + '\nGere uma instância JSON de dados, não o JSON Schema. '
             'Não envolva os campos em properties e não devolva metadados como title, type ou required. '
             'O exemplo a seguir mostra somente o formato: substitua todos os valores conforme o contexto. Exemplo: '
             + json.dumps(output_example(schema), ensure_ascii=False) + '\nEsquema de validação: '
             + json.dumps(schema.model_json_schema(), ensure_ascii=False)},
            {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}],
            'max_tokens': min(4096, output_limit), 'temperature': 0.4,
            'provider': {'allow_fallbacks': False, 'max_price': {'prompt': 0, 'completion': 0, 'request': 0, 'image': 0}}}
        reasoning = selected.get('reasoning')
        if reasoning is not None:
            if not reasoning.get('mandatory', False):
                payload['reasoning'] = {'enabled': False, 'exclude': True}
            elif reasoning.get('supports_max_tokens'):
                payload['reasoning'] = {'max_tokens': 512, 'exclude': True}
            else:
                efforts = reasoning.get('supported_efforts')
                effort = next((level for level in ('minimal', 'low', 'medium', 'high', 'xhigh', 'max')
                               if efforts is None or level in efforts), None)
                if effort:
                    payload['reasoning'] = {'effort': effort, 'exclude': True}
        parameters = selected.get('supported_parameters', [])
        if 'response_format' in parameters:
            payload['response_format'] = {'type': 'json_object'}
        for attempt in range(3):
            try:
                response = await self.client.post('https://openrouter.ai/api/v1/chat/completions',
                    headers={'Authorization': f'Bearer {self.key}', 'X-Title': 'Tribunal dos LLMs'}, json=payload)
                if response.status_code == 429:
                    error = response.json().get('error') or {}
                    metadata = error.get('metadata') or {}
                    if metadata.get('limit_source') == 'openrouter_free_tier_daily' or 'free-models-per-day' in str(error.get('message', '')):
                        raise ProviderError('A franquia diária de requisições gratuitas do OpenRouter acabou. Esse limite é compartilhado pela conta; trocar de modelo não renova a franquia. Aguarde a renovação diária ou use a demonstração.',
                                            code='provider_daily_limit', details={'http_status': 429, 'model': model})
                    raise ProviderError('O modelo gratuito selecionado atingiu um limite de requisições ou de capacidade. Aguarde ou selecione outro modelo gratuito e inicie uma nova partida. Progresso preservado.',
                                        code='provider_rate_limit', details={'http_status': 429, 'model': model})
                if response.status_code == 402:
                    raise ProviderError('Cota gratuita da conta indisponível. Progresso preservado; nenhum modelo pago foi usado.',
                                        code='provider_quota', details={'http_status': 402, 'model': model})
                if response.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if response.status_code >= 400:
                    raise ProviderError('O provedor recusou a chamada. Verifique chave e disponibilidade do modelo.')
                data = response.json()
                actual = data.get('model')
                if actual not in {model, model.removesuffix(':free')}:
                    raise ProviderError('O provedor retornou um modelo diferente do selecionado; execução interrompida.')
                choices = data.get('choices')
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise ProviderError('O provedor retornou uma resposta sem alternativas válidas. Progresso preservado.',
                                        code='provider_invalid_response')
                choice = choices[0]
                message = choice.get('message') or {}
                if not isinstance(message, dict):
                    raise ProviderError('O provedor retornou uma mensagem inválida. Progresso preservado.',
                                        code='provider_invalid_response')
                content = message.get('content')
                if isinstance(content, list):
                    content = ''.join(part.get('text', '') for part in content
                                      if isinstance(part, dict) and part.get('type') == 'text'
                                      and isinstance(part.get('text'), str))
                if not isinstance(content, str) or not content.strip():
                    if message.get('refusal'):
                        raise ProviderError('O modelo recusou responder à solicitação. Reformule a pergunta.',
                                            code='provider_refusal')
                    if attempt < 2:
                        payload['max_tokens'] = min(payload['max_tokens'] * 2, output_limit)
                        continue
                    raise ProviderError('O modelo retornou a fala vazia após três tentativas. O limite de geração pode ter sido consumido pelo raciocínio interno. Tente outro modelo gratuito.',
                                        code='provider_empty_output', details={'finish_reason': choice.get('finish_reason'), 'attempts': 3})
                content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
                try:
                    result = schema.model_validate_json(content)
                except ValueError as exc:
                    if attempt < 2:
                        if choice.get('finish_reason') == 'length':
                            payload['max_tokens'] = min(payload['max_tokens'] * 2, output_limit)
                        payload['messages'].append({'role': 'assistant', 'content': content[:12000]})
                        errors = exc.errors(include_url=False, include_context=False, include_input=False) if hasattr(exc, 'errors') else []
                        payload['messages'].append({'role': 'user', 'content': 'Corrija a resposta anterior: gere o objeto de dados, não o esquema. JSON válido, campos exatos e até 180 palavras em text. Erros de validação: ' + json.dumps(errors, ensure_ascii=False)})
                        continue
                    raise ProviderError('O modelo não respondeu no formato esperado após três tentativas.',
                                        code='provider_invalid_json', details={'finish_reason': choice.get('finish_reason'), 'attempts': 3})
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
        """Usa cache ou confirma a franquia antes de reservar uma busca basic.
        
        Não repete POST incerto; uma falha gera SearchUnavailable em vez de evidência inventada."""
        query = ' '.join(query.lower().split())
        cached = self.store.cached(query)
        if cached is not None:
            return cached
        if not self.key:
            raise SearchUnavailable('Pesquisa indisponível: configure TAVILY_API_KEY. A afirmação permanece inconclusiva.')
        headers = {'Authorization': f'Bearer {self.key}'}
        try:
            usage_response = await self.client.get('https://api.tavily.com/usage', headers=headers)
            if usage_response.status_code == 401:
                raise SearchUnavailable('O Tavily recusou a chave de API. Confira TAVILY_API_KEY e reinicie o backend.',
                                        code='search_auth_error', details={'http_status': 401})
            if usage_response.status_code == 429:
                raise SearchUnavailable('O Tavily atingiu um limite de requisições. A pesquisa está temporariamente indisponível.',
                                        code='search_rate_limit', details={'http_status': 429})
            if usage_response.status_code != 200:
                raise SearchUnavailable('Não foi possível confirmar a cota gratuita do Tavily; busca bloqueada.',
                                        code='search_usage_unavailable', details={'http_status': usage_response.status_code})
            account = usage_response.json().get('account') or {}
            if any(account.get(field) is None for field in ('paygo_usage', 'plan_usage', 'plan_limit')) or 'paygo_limit' not in account:
                raise SearchUnavailable('O Tavily não confirmou todos os limites de faturamento (campo vazio ou ausente). Por segurança, a busca foi bloqueada e a afirmação permanece inconclusiva.',
                                        code='search_billing_unknown')
            # null não é interpretado como zero nem como autorização de cobrança.
            # A busca basic só é liberada com um crédito inteiro dentro da franquia
            # gratuita confirmada, limitada também ao teto local de 1.000 créditos.
            plan_usage = Decimal(str(account['plan_usage']))
            plan_limit = Decimal(str(account['plan_limit']))
            paygo_usage = Decimal(str(account['paygo_usage']))
            paygo_limit = Decimal(str(account['paygo_limit'])) if account['paygo_limit'] is not None else None
            values = [plan_usage, plan_limit, paygo_usage] + ([paygo_limit] if paygo_limit is not None else [])
            if (any(not value.is_finite() or value < 0 for value in values) or
                str(account.get('current_plan', '')).strip().lower() not in ('free', 'researcher') or
                (paygo_limit is not None and paygo_limit != 0) or paygo_usage != 0):
                raise SearchUnavailable('Tavily fora do plano gratuito ou com cobrança por uso indicada; busca bloqueada.',
                                        code='search_paid_plan_blocked')
            if plan_usage + 1 > min(plan_limit, self.budget):
                raise SearchUnavailable('A franquia gratuita de pesquisa está esgotada. Nenhuma busca paga foi feita.',
                                        code='search_quota_exhausted')
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
        except (httpx.HTTPError, ValueError, TypeError, KeyError, InvalidOperation) as exc:
            raise SearchUnavailable('Falha ao consultar a pesquisa; afirmação inconclusiva.') from exc
