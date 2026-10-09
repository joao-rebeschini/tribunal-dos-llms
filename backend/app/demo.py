"""Reprodução assíncrona de conteúdo editorial pré-gravado, sem consumir APIs."""

import asyncio
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / 'fixtures' / 'demo.json'

def fixture():
    """Carrega a demonstração em UTF-8 a partir do arquivo versionado."""
    return json.loads(FIXTURE.read_text(encoding='utf-8'))

async def replay(mid, store, delay=0.9):
    """Publica os eventos editoriais com atraso e cria etapas antes das falas."""
    for event in fixture()['events']:
        await asyncio.sleep(delay)
        if event['type'] == 'speech':
            d = event['data']
            store.event(mid, 'stage', {'role': d['role'], 'round': d['round'], 'phase': d['phase']})
        store.event(mid, event['type'], event['data'])
        if event['type'] == 'result':
            store.update(mid, 'completed', event['data'])
