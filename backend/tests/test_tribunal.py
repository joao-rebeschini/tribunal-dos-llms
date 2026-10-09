import asyncio
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app.domain import ROLES, Speech, Claims, Verification, Proposal, Acceptance, Confirmation, Verdict
from app.engine import Tribunal
from app.providers import OpenRouter, Tavily, free_model, ProviderError, SearchUnavailable
from app.storage import Store
from app.main import create_app
from app.report import report

class SimulatedLLM:
    def __init__(self, reject_until=0, answers=True, confirm=True, claims=False, fail=False, delay=0):
        self.reject_until, self.answers, self.confirm = reject_until, answers, confirm
        self.claims, self.fail, self.delay = claims, fail, delay
        self.contexts = []

    async def models(self):
        return [{'id': 'test/free', 'name': 'Modelo simulado'}]

    async def complete(self, model, system, context, schema):
        self.contexts.append((model, context))
        await asyncio.sleep(self.delay)
        if self.fail and context['transcript']:
            raise ProviderError('Cota gratuita esgotada.')
        if schema is Speech:
            data = {'text': 'Argumento fundamentado e legível em português.'}
        elif schema is Claims:
            data = {'claims': [{'text': 'Afirmação factual da defesa.', 'role': 'defesa', 'query': 'consulta factual'}] if self.claims else []}
        elif schema is Verification:
            data = {'status': 'contradita', 'explanation': 'A fonte contradiz a afirmação.', 'source_ids': [0]}
        elif schema is Proposal:
            data = {'text': 'Uma conclusão com condições.', 'conclusion': 'Conclusão compartilhada.', 'answers_question': self.answers}
        elif schema is Acceptance:
            # Defesa aceita sempre; uma única discordância (oposição) impede consenso.
            accepted = context['transcript'][-1]['role'] != 'defesa' or context['round'] > self.reject_until
            data = {'text': 'Aceito.' if accepted else 'Rejeito.', 'accepted': accepted, 'conclusion': 'Conclusão compartilhada.'}
        elif schema is Confirmation:
            data = {'text': 'Confirmo a resposta.', 'confirmed': self.confirm, 'conclusion': 'Conclusão compartilhada.'}
        elif schema is Verdict:
            data = {'text': 'Julgamento final.', 'conclusion': 'Conclusão compartilhada.', 'justification': 'Justificativa fundamentada.', 'divergences': [], 'scores': {r: {'evidencias': 6, 'coerencia': 9, 'refutacoes': 9, 'justification': 'Avaliação.'} for r in ['defesa','oposicao']}}
        else:
            raise AssertionError(schema)
        return schema.model_validate(data).model_dump(), model

class SimulatedSearch:
    def __init__(self, unavailable=False):
        self.unavailable = unavailable
        self.calls = 0
    async def search(self, query):
        self.calls += 1
        if self.unavailable:
            raise SearchUnavailable('Pesquisa indisponível.')
        return [{'id': 0, 'title': 'Fonte de teste', 'url': 'https://example.org/source', 'content': 'Dado contraditório.'}]

@pytest.mark.asyncio
@pytest.mark.parametrize('reject,answers,confirm,rounds,consensus', [(0,True,True,1,True),(2,True,True,3,True),(9,True,True,5,False),(0,False,True,5,False),(0,True,False,5,False)])
async def test_termination(tmp_path, reject, answers, confirm, rounds, consensus):
    store = Store(tmp_path/'db.sqlite')
    mid = store.create('Qual solução devemos escolher?', {r:'test/free' for r in ROLES})
    llm = SimulatedLLM(reject, answers, confirm)
    await Tribunal(mid, store, llm, SimulatedSearch()).run()
    result = store.get(mid)['result']
    assert result['rounds'] == rounds and result['consensus'] == consensus
    assert all(s['final'] == 8 for s in result['scores'].values())
    assert len([e for e in store.events(mid) if e['type']=='speech' and e['data']['role']=='defesa' and e['data']['phase']=='debate']) == rounds
    # Identidade do modelo não chega a nenhum contexto de avaliação.
    assert all('test/free' not in json.dumps(ctx) for _,ctx in llm.contexts)

@pytest.mark.asyncio
@pytest.mark.parametrize('unavailable', [False, True])
async def test_evidence_and_search_failure(tmp_path, unavailable):
    store = Store(tmp_path/'db.sqlite')
    mid = store.create('O que dizem as fontes?', {r:'test/free' for r in ROLES})
    await Tribunal(mid, store, SimulatedLLM(claims=True), SimulatedSearch(unavailable)).run()
    evidence = next(e['data'] for e in store.events(mid) if e['type']=='evidence')
    if unavailable:
        assert evidence['status']=='inconclusiva' and evidence['sources']==[]
        assert store.get(mid)['result']['contradicted']['defesa']==[]
    else:
        assert evidence['sources'][0]['url']=='https://example.org/source'
        assert len(store.get(mid)['result']['contradicted']['defesa'])==1

@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['confirmada', 'contradita', 'inconclusiva'])
async def test_real_search_path_preserves_each_verifier_classification(tmp_path, status):
    class ClassifiedLLM(SimulatedLLM):
        async def complete(self, model, system, context, schema):
            if schema is Verification:
                assert context['sources'][0]['url'] == 'https://example.org/source'
                return {'status': status, 'explanation': 'Classificação com fonte válida.', 'source_ids': [0]}, model
            return await super().complete(model, system, context, schema)
    store = Store(tmp_path / 'db.sqlite')
    mid = store.create('O que dizem as fontes verificadas?', {role: 'test/free' for role in ROLES})
    await Tribunal(mid, store, ClassifiedLLM(claims=True), SimulatedSearch()).run()
    evidence = next(event['data'] for event in store.events(mid) if event['type'] == 'evidence')
    assert evidence['status'] == status
    assert evidence['sources'][0]['url'] == 'https://example.org/source'


def test_price_and_output_validation():
    assert free_model({'pricing': {'prompt':'0','completion':'0','request':'0'}})
    for pricing in [{'prompt':'1','completion':'0'}, {'prompt':'0','completion':'0','web_search':'0.01'}, {'prompt':'bad','completion':'0'}, {}]:
        assert not free_model({'pricing': pricing})
    with pytest.raises(ValueError):
        Speech(text='palavra '*181)
    with pytest.raises(ValueError):
        Claims(claims=[{'text':'Fato','role':'defesa','query':'consulta'}]*4)

@pytest.mark.asyncio
async def test_openrouter_rejects_paid_and_quota():
    posts = []
    def handler(request):
        if request.method=='GET':
            return httpx.Response(200,json={'data':[{'id':'free','name':'Free','pricing':{'prompt':'0','completion':'0'}},{'id':'paid','name':'Paid','pricing':{'prompt':'1','completion':'1'}}]})
        posts.append(json.loads(request.content))
        return httpx.Response(429,json={'error': {'message':'SENSITIVE_PROVIDER_MESSAGE'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        router = OpenRouter('SECRET_TEST_TOKEN',client)
        with pytest.raises(ProviderError): await router.complete('paid','system',{},Speech)
        assert posts==[]
        with pytest.raises(ProviderError, match='limite de requisições') as error: await router.complete('free','system',{},Speech)
        assert error.value.code == 'provider_rate_limit'
        assert len(posts)==1 and posts[0]['provider']['max_price']['prompt']==0
        assert 'models' not in posts[0] and posts[0]['provider']['allow_fallbacks'] is False

@pytest.mark.asyncio
@pytest.mark.parametrize('plan,paygo,usage,allowed', [('free',0,0,True),('free',1,0,False),('paid',0,0,False),('free',0,1000,False)])
async def test_tavily_free_guard_and_cache(tmp_path, plan, paygo, usage, allowed):
    store = Store(tmp_path/'db.sqlite')
    calls=[]
    def handler(request):
        calls.append(request.method)
        if request.method=='GET':
            return httpx.Response(200,json={'account':{'current_plan':plan,'paygo_limit':paygo,'paygo_usage':0,'plan_usage':usage,'plan_limit':1000}})
        data=json.loads(request.content)
        assert data['search_depth']=='basic' and data['auto_parameters'] is False
        return httpx.Response(200,json={'results':[{'title':'Fonte','url':'https://example.org','content':'Fonte real do teste.'}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tavily=Tavily('SECRET_TEST_TOKEN',store,client=client)
        if allowed:
            await tavily.search('Consulta'); await tavily.search('consulta')
            assert calls==['GET','POST']
        else:
            with pytest.raises(SearchUnavailable): await tavily.search('consulta')
            assert calls==['GET']

def test_sse_reconnection_history_export_and_cancel(tmp_path):
    app=create_app(tmp_path/'db.sqlite',SimulatedLLM(delay=.1),SimulatedSearch(),demo_delay=.01)
    with TestClient(app) as client:
        mid=client.post('/api/demo').json()['id']
        with client.stream('GET',f'/api/matches/{mid}/events') as stream:
            data=[json.loads(line[6:]) for line in stream.iter_lines() if line.startswith('data: ')]
        assert any(e['type']=='result' for e in data)
        assert [e['id'] for e in data]==list(range(1,len(data)+1))
        cutoff=data[len(data)//2]['id']
        replay=client.get(f'/api/matches/{mid}/events',headers={'Last-Event-ID':str(cutoff)}).text
        resumed=[json.loads(l[6:]) for l in replay.splitlines() if l.startswith('data: ')]
        assert all(e['id']>cutoff for e in resumed)
        assert len(resumed)==len(data)-cutoff
        assert client.get('/api/matches').json()[0]['id']==mid
        exported=client.get(f'/api/matches/{mid}/report')
        assert 'Demonstração pré-gravada' in exported.text and 'SECRET_TEST_TOKEN' not in exported.text
        assert client.get('/api/matches/not-found').status_code==404
        assert client.get(f'/api/matches/{mid}/events',headers={'Last-Event-ID':'bad'}).status_code==400
        live=client.post('/api/matches',json={'question':'Pergunta de teste para cancelar?', 'models':{r:'test/free' for r in ROLES}}).json()['id']
        assert client.post(f'/api/matches/{live}/cancel').json()['status']=='cancelled'
        assert client.get(f'/api/matches/{live}').json()['result'] is None
        assert client.post('/api/matches',json={'question':'Pergunta de teste para modelo pago?', 'models':{r:'paid' for r in ROLES}}).status_code==422

def test_quota_preserves_progress_without_verdict(tmp_path):
    app=create_app(tmp_path/'db.sqlite',SimulatedLLM(fail=True),SimulatedSearch())
    with TestClient(app) as client:
        mid=client.post('/api/matches',json={'question':'Pergunta de teste com cota?', 'models':{r:'test/free' for r in ROLES}}).json()['id']
        data=client.get(f'/api/matches/{mid}/events').text
        match=client.get(f'/api/matches/{mid}').json()
        assert match['status']=='interrupted' and match['result'] is None
        assert 'Argumento fundamentado' in data and 'Cota gratuita' in data

def test_restart_and_budget(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    mid=store.create('Pergunta preservada?',{})
    store.event(mid,'speech',{'text':'Progresso já salvo.'})
    Store(tmp_path/'db.sqlite').recover()
    assert store.get(mid)['status']=='interrupted' and len(store.events(mid))==2
    assert store.reserve_search(1) and not store.reserve_search(1)
