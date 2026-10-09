import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app.domain import Speech, ROLES
from app.main import create_app
from app.providers import OpenRouter, ProviderError, Tavily, SearchUnavailable
from app.storage import Store


def transport_for(responses, posts, reasoning=None):
    def handler(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{
                'id': 'test/free', 'name': 'Teste',
                'pricing': {'prompt': '0', 'completion': '0'},
                'supported_parameters': ['response_format', 'reasoning'],
                'reasoning': reasoning,
                'top_provider': {'max_completion_tokens': 16000},
            }]})
        posts.append(json.loads(request.content))
        return httpx.Response(200, json={'model': 'test/free', **responses.pop(0)})
    return httpx.MockTransport(handler)


def answer(content, finish='stop', **extra):
    return {'choices': [{'finish_reason': finish, 'message': {'content': content, **extra}}]}


@pytest.mark.asyncio
async def test_reasoning_only_response_recovers_without_using_internal_reasoning():
    posts = []
    responses = [answer(None, 'length', reasoning='Não é uma fala.'), answer('{"text":"Argumento válido."}')]
    async with httpx.AsyncClient(transport=transport_for(responses, posts, {'mandatory': False})) as client:
        result, model = await OpenRouter('TEST_TOKEN', client).complete('test/free', 'Defenda.', {}, Speech)
    assert result == {'text': 'Argumento válido.'} and model == 'test/free'
    assert [p['max_tokens'] for p in posts] == [4096, 8192]
    for payload in posts:
        assert payload['reasoning'] == {'enabled': False, 'exclude': True}
        assert payload['provider']['allow_fallbacks'] is False
        assert all(price == 0 for price in payload['provider']['max_price'].values())


@pytest.mark.asyncio
async def test_persistent_empty_response_has_actionable_error_and_bounded_retries():
    posts = []
    async with httpx.AsyncClient(transport=transport_for([answer(None, 'length')] * 3, posts)) as client:
        with pytest.raises(ProviderError) as error:
            await OpenRouter('TEST_TOKEN', client).complete('test/free', 'Defenda.', {}, Speech)
    assert error.value.code == 'provider_empty_output'
    assert error.value.details == {'finish_reason': 'length', 'attempts': 3}
    assert [p['max_tokens'] for p in posts] == [4096, 8192, 16000]


@pytest.mark.asyncio
async def test_wrong_schema_response_is_corrected_with_validation_feedback():
    posts = []
    responses = [answer('{"properties":{"text":"Fala"}}'), answer('{"text":"Fala corrigida."}')]
    async with httpx.AsyncClient(transport=transport_for(responses, posts)) as client:
        result, _ = await OpenRouter('TEST_TOKEN', client).complete('test/free', 'Defenda.', {}, Speech)
    assert result['text'] == 'Fala corrigida.'
    assert 'Exemplo: {"text":' in posts[0]['messages'][0]['content']
    assert 'Erros de validação' in posts[1]['messages'][-1]['content']


@pytest.mark.asyncio
@pytest.mark.parametrize('response,code', [
    ({'choices': []}, 'provider_invalid_response'),
    (answer(None, refusal='PRIVATE_PROVIDER_TEXT'), 'provider_refusal'),
])
async def test_invalid_response_and_refusal_do_not_leak_provider_content(response, code):
    posts = []
    async with httpx.AsyncClient(transport=transport_for([response], posts)) as client:
        with pytest.raises(ProviderError) as error:
            await OpenRouter('TEST_TOKEN', client).complete('test/free', 'Defenda.', {}, Speech)
    assert error.value.code == code
    assert 'PRIVATE_PROVIDER_TEXT' not in str(error.value)
    assert len(posts) == 1


@pytest.mark.asyncio
async def test_mandatory_reasoning_is_not_disabled():
    posts = []
    async with httpx.AsyncClient(transport=transport_for(
        [answer('{"text":"Fala válida."}')], posts,
        {'mandatory': True, 'supported_efforts': ['low', 'high']},
    )) as client:
        await OpenRouter('TEST_TOKEN', client).complete('test/free', 'Defenda.', {}, Speech)
    assert posts[0]['reasoning'] == {'effort': 'low', 'exclude': True}


def test_empty_output_error_reaches_saved_events_and_sse(tmp_path):
    class EmptyLLM:
        async def models(self):
            return [{'id': 'test/free'}]

        async def complete(self, *args):
            raise ProviderError('O modelo retornou a fala vazia.', code='provider_empty_output', details={'attempts': 3})

    app = create_app(tmp_path / 'match.sqlite', llm=EmptyLLM())
    with TestClient(app) as client:
        mid = client.post('/api/matches', json={
            'question': 'Devemos adotar a semana de quatro dias?',
            'models': {role: 'test/free' for role in ROLES},
        }).json()['id']
        stream = client.get(f'/api/matches/{mid}/events').text
        match = client.get(f'/api/matches/{mid}').json()
    assert match['status'] == 'interrupted' and match['result'] is None
    assert 'provider_empty_output' in stream
    assert match['events'][-1]['data']['details']['attempts'] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('usage,allowed', [(0, True), (999, True), (999.5, False), (1000, False), (1500, False)])
async def test_tavily_null_paygo_limit_only_allows_confirmed_free_credit(tmp_path, usage, allowed):
    requests = []
    def handler(request):
        requests.append(request.method)
        if request.method == 'POST':
            assert json.loads(request.content)['search_depth'] == 'basic'
            return httpx.Response(200, json={'results': [{'title': 'Fonte', 'url': 'https://example.org', 'content': 'Evidência.'}]})
        return httpx.Response(200, json={'account': {'current_plan': 'Researcher',
            'paygo_limit': None, 'paygo_usage': 0, 'plan_usage': usage, 'plan_limit': 1500}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tavily = Tavily('TEST_TOKEN', Store(tmp_path / 'db.sqlite'), client=client)
        if allowed:
            assert (await tavily.search('consulta'))[0]['url'] == 'https://example.org'
            assert requests == ['GET', 'POST']
        else:
            with pytest.raises(SearchUnavailable) as error:
                await tavily.search('consulta')
            assert error.value.code == 'search_quota_exhausted'
            assert requests == ['GET']


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('plan_usage', None), ('plan_limit', None), ('paygo_usage', None),
    ('plan_usage', 'NaN'), ('plan_limit', 'Infinity'), ('plan_usage', -1), ('paygo_usage', 1), ('paygo_limit', 10)])
async def test_tavily_unknown_or_paid_billing_never_searches(tmp_path, field, value):
    account = {'current_plan': 'Researcher', 'plan_usage': 0, 'plan_limit': 1500, 'paygo_usage': 0, 'paygo_limit': None}
    account[field] = value
    requests = []
    def handler(request):
        requests.append(request.method)
        return httpx.Response(200, json={'account': account})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SearchUnavailable):
            await Tavily('TEST_TOKEN', Store(tmp_path / 'db.sqlite'), client=client).search('consulta')
    assert requests == ['GET']


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [(401, 'search_auth_error'), (429, 'search_rate_limit'), (503, 'search_usage_unavailable')])
async def test_tavily_usage_http_errors_are_identified(tmp_path, status, code):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status))) as client:
        with pytest.raises(SearchUnavailable) as error:
            await Tavily('TEST_TOKEN', Store(tmp_path / 'db.sqlite'), client=client).search('consulta')
    assert error.value.code == code


def test_app_construction_does_not_interrupt_another_running_server(tmp_path):
    path = tmp_path / 'db.sqlite'
    store = Store(path)
    mid = store.create('Pergunta que deve continuar em execução?', {})
    app = create_app(path)
    assert store.get(mid)['status'] == 'running'
    with TestClient(app):
        assert store.get(mid)['status'] == 'interrupted'


@pytest.mark.asyncio
async def test_openrouter_limits_exposes_only_daily_counter():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        'data': {'label': 'PRIVATE_KEY_NAME', 'limit_remaining': 100, 'free_model_daily_requests': {'used': 59, 'limit': 50, 'remaining': 0}}
    }))) as client:
        quota = await OpenRouter('TEST_TOKEN', client).limits()
    assert quota['daily'] == {'used': 59, 'limit': 50, 'remaining': 0}
    assert quota['reset_at'].endswith('00:00:00+00:00')
    assert 'PRIVATE_KEY_NAME' not in json.dumps(quota) and 'limit_remaining' not in quota


def test_daily_quota_preflight_does_not_start_or_save_a_failed_match(tmp_path):
    class ExhaustedRouter:
        async def limits(self):
            return {'daily': {'used': 50, 'limit': 50, 'remaining': 0}, 'reset_at': None}
        async def models(self):
            raise AssertionError('Não deve avançar após franquia esgotada.')
    app = create_app(tmp_path / 'db.sqlite', llm=ExhaustedRouter(), demo_delay=0)
    with TestClient(app) as client:
        assert client.get('/api/limits').json()['daily']['remaining'] == 0
        response = client.post('/api/matches', json={'question': 'Uma pergunta para o tribunal?', 'models': {role: 'test/free' for role in ROLES}})
        assert response.status_code == 429
        assert client.get('/api/matches').json() == []
        assert client.post('/api/demo').status_code == 201


@pytest.mark.asyncio
async def test_daily_request_limit_is_not_reported_as_model_capacity():
    def handler(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id':'test/free','name':'Teste','pricing':{'prompt':'0','completion':'0'}}]})
        return httpx.Response(429, json={'error': {'message': 'Rate limit exceeded: free-models-per-day',
            'metadata': {'limit_source': 'openrouter_free_tier_daily'}}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as error:
            await OpenRouter('TEST_TOKEN', client).complete('test/free', 'Teste', {}, Speech)
    assert error.value.code == 'provider_daily_limit'
    assert 'trocar de modelo não renova' in str(error.value)
