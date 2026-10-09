import asyncio
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from .domain import MatchRequest, TERMINAL
from .storage import Store, encode
from .providers import OpenRouter, Tavily, ProviderError
from .engine import Tribunal
from .demo import fixture, replay
from .report import report

BASE = Path(__file__).resolve().parents[1]
logger = logging.getLogger('tribunal')
load_dotenv(BASE / '.env')

def create_app(db_path=None, llm=None, search=None, demo_delay=0.9):
    store = Store(db_path or BASE / os.getenv('TRIBUNAL_DB', 'data/tribunal.sqlite3'))
    router = llm or OpenRouter(os.getenv('OPENROUTER_API_KEY', ''))
    researcher = search or Tavily(os.getenv('TAVILY_API_KEY', ''), store, int(os.getenv('TAVILY_MONTHLY_BUDGET', '1000')))
    tasks = {}

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        for provider in (router, researcher):
            if hasattr(provider, 'client'):
                await provider.client.aclose()

    app = FastAPI(title='Tribunal dos LLMs', lifespan=lifespan)
    app.state.store, app.state.tasks = store, tasks
    app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'], allow_methods=['GET', 'POST'], allow_headers=['Content-Type', 'Last-Event-ID'])

    def require(mid):
        match = store.get(mid)
        if not match:
            raise HTTPException(404, 'Partida não encontrada.')
        return match

    async def execute(mid, demo=False):
        try:
            if demo:
                await replay(mid, store, demo_delay)
            else:
                await Tribunal(mid, store, router, researcher).run()
        except asyncio.CancelledError:
            if store.get(mid)['status'] == 'running':
                store.update(mid, 'cancelled')
                store.event(mid, 'cancelled', {'message': 'Partida cancelada. O progresso foi preservado.'})
            raise
        except ProviderError as exc:
            store.update(mid, 'interrupted')
            store.event(mid, 'interrupted', {'message': str(exc), 'code': exc.code, 'details': exc.details})
        except Exception as exc:
            # Não expõe respostas externas, cabeçalhos ou segredos em erros.
            logger.error('Falha inesperada partida=%s tipo=%s', mid, type(exc).__name__)
            store.update(mid, 'interrupted')
            store.event(mid, 'interrupted', {'message': 'Falha inesperada na execução. Progresso preservado; nenhum resultado foi fabricado.',
                                          'code': 'unexpected_error', 'details': {'exception_type': type(exc).__name__}})

    def launch(mid, demo=False):
        task = asyncio.create_task(execute(mid, demo))
        tasks[mid] = task
        task.add_done_callback(lambda _: tasks.pop(mid, None))

    @app.get('/api/health')
    async def health():
        return {'ok': True, 'openrouter_configured': bool(os.getenv('OPENROUTER_API_KEY')), 'tavily_configured': bool(os.getenv('TAVILY_API_KEY'))}

    @app.get('/api/models')
    async def models():
        try:
            return {'models': await router.models()}
        except ProviderError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get('/api/limits')
    async def limits():
        if not hasattr(router, 'limits'):
            return {'daily': None, 'reset_at': None}
        try:
            return await router.limits()
        except ProviderError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post('/api/matches', status_code=201)
    async def create(body: MatchRequest):
        if llm is None and not os.getenv('OPENROUTER_API_KEY'):
            raise HTTPException(503, 'Configure OPENROUTER_API_KEY no backend ou abra a demonstração.')
        try:
            if hasattr(router, 'limits'):
                quota = await router.limits()
                if quota['daily'] is not None and quota['daily']['remaining'] <= 0:
                    raise HTTPException(429, 'A franquia diária de requisições gratuitas do OpenRouter acabou. Aguarde a renovação diária ou abra a demonstração. Nenhuma partida foi iniciada.')
            free = {m['id'] for m in await router.models()}
        except ProviderError as exc:
            raise HTTPException(503, str(exc)) from exc
        if any(model not in free for model in body.models.values()):
            raise HTTPException(422, 'Somente modelos gratuitos do catálogo atual são permitidos.')
        mid = store.create(body.question, body.models)
        store.event(mid, 'started', {'message': 'Audiência iniciada.', 'demo': False})
        launch(mid)
        return store.get(mid)

    @app.post('/api/demo', status_code=201)
    async def demo():
        mid = store.create(fixture()['question'], {}, True)
        store.event(mid, 'started', {'message': 'Demonstração pré-gravada. Falas, classificação e notas ilustrativas; sem consumo de APIs.', 'demo': True})
        launch(mid, True)
        return store.get(mid)

    @app.get('/api/matches')
    async def history():
        return store.history()

    @app.get('/api/matches/{mid}')
    async def get(mid: str):
        return {**require(mid), 'events': store.events(mid)}

    @app.post('/api/matches/{mid}/cancel')
    async def cancel(mid: str):
        match = require(mid)
        if match['status'] == 'running':
            if mid in tasks:
                tasks[mid].cancel()
                await asyncio.gather(tasks[mid], return_exceptions=True)
            else:
                store.update(mid, 'cancelled')
                store.event(mid, 'cancelled', {'message': 'Partida cancelada. Progresso preservado.'})
        return store.get(mid)

    @app.get('/api/matches/{mid}/events')
    async def events(mid: str, request: Request, after: int = 0):
        require(mid)
        try:
            cursor = max(0, after, int(request.headers.get('last-event-id', '0')))
        except ValueError:
            raise HTTPException(400, 'Last-Event-ID inválido.')
        async def stream():
            nonlocal cursor
            heartbeat = 0
            while not await request.is_disconnected():
                batch = store.events(mid, cursor)
                for event in batch:
                    cursor = event['id']
                    yield f"id: {cursor}\ndata: {encode(event)}\n\n"
                if store.get(mid)['status'] in TERMINAL:
                    # Terminal é gravado antes do próximo polling; envia o restante antes de fechar.
                    for event in store.events(mid, cursor):
                        cursor = event['id']
                        yield f"id: {cursor}\ndata: {encode(event)}\n\n"
                    break
                heartbeat += 1
                if heartbeat % 40 == 0:
                    yield ': heartbeat\n\n'
                await asyncio.sleep(0.25)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.get('/api/matches/{mid}/report')
    async def export(mid: str):
        content = report(require(mid), store.events(mid))
        return Response(content, media_type='text/markdown; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="tribunal-{mid}.md"'})

    dist = BASE.parent / 'frontend' / 'dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    return app

app = create_app()
