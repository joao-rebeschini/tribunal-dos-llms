import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

def encode(value):
    return json.dumps(value, ensure_ascii=False)

class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS matches (
                    id TEXT PRIMARY KEY, question TEXT, models TEXT,
                    status TEXT, demo INTEGER, created_at TEXT, result TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    match_id TEXT, seq INTEGER, type TEXT, payload TEXT,
                    PRIMARY KEY(match_id, seq)
                );
                CREATE TABLE IF NOT EXISTS search_cache (
                    query TEXT PRIMARY KEY, results TEXT, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS budget (
                    month TEXT PRIMARY KEY, searches INTEGER NOT NULL
                );
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def create(self, question, models, demo=False):
        mid = str(uuid.uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO matches VALUES (?,?,?,?,?,?,?)',
                       (mid, question, encode(models), 'running', int(demo),
                        datetime.now(timezone.utc).isoformat(), None))
        return mid

    def update(self, mid, status, result=None):
        with self.connect() as db:
            db.execute('UPDATE matches SET status=?, result=? WHERE id=?',
                       (status, encode(result) if result is not None else None, mid))

    def event(self, mid, kind, data):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            seq = db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE match_id=?', (mid,)).fetchone()[0]
            db.execute('INSERT INTO events VALUES (?,?,?,?)', (mid, seq, kind, encode(data)))
        return {'id': seq, 'type': kind, 'data': data}

    def events(self, mid, after=0):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM events WHERE match_id=? AND seq>? ORDER BY seq', (mid, after)).fetchall()
        return [{'id': r['seq'], 'type': r['type'], 'data': json.loads(r['payload'])} for r in rows]

    def get(self, mid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM matches WHERE id=?', (mid,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data['models'] = json.loads(data['models'])
        data['result'] = json.loads(data['result']) if data['result'] else None
        data['demo'] = bool(data['demo'])
        return data

    def history(self):
        with self.connect() as db:
            ids = db.execute('SELECT id FROM matches ORDER BY created_at DESC LIMIT 100').fetchall()
        return [self.get(r['id']) for r in ids]

    def recover(self):
        with self.connect() as db:
            matches = db.execute("SELECT id FROM matches WHERE status='running'").fetchall()
        for match in matches:
            self.update(match['id'], 'interrupted')
            self.event(match['id'], 'interrupted', {'message': 'O servidor foi reiniciado. Progresso preservado; inicie outra partida para continuar.'})

    def cached(self, query):
        with self.connect() as db:
            row = db.execute('SELECT results, created_at FROM search_cache WHERE query=?', (query,)).fetchone()
        if row and (datetime.now(timezone.utc) - datetime.fromisoformat(row['created_at'])).total_seconds() < 86400:
            return json.loads(row['results'])
        return None

    def cache(self, query, results):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO search_cache VALUES (?,?,?)',
                       (query, encode(results), datetime.now(timezone.utc).isoformat()))

    def reserve_search(self, limit):
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT searches FROM budget WHERE month=?', (month,)).fetchone()
            used = row[0] if row else 0
            if used >= limit:
                return False
            db.execute('INSERT OR REPLACE INTO budget VALUES (?,?)', (month, used + 1))
        return True
