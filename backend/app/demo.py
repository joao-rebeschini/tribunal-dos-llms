import asyncio
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / 'fixtures' / 'demo.json'

def fixture():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))

async def replay(mid, store, delay=0.9):
    for event in fixture()['events']:
        await asyncio.sleep(delay)
        if event['type'] == 'speech':
            d = event['data']
            store.event(mid, 'stage', {'role': d['role'], 'round': d['round'], 'phase': d['phase']})
        store.event(mid, event['type'], event['data'])
        if event['type'] == 'result':
            store.update(mid, 'completed', event['data'])
