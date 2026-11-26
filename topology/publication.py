import hashlib
import json
from dataclasses import dataclass

from endpoint.store import write_transaction
from topology.layout import Layout, build_layout
from topology.ports import BusinessError, require_name
from topology.reachability import assess_paths


@dataclass(frozen=True)
class Publication:
    reference: str
    layout: Layout
    path: tuple[str, ...]


def initialize_publications(db):
    db.execute('''CREATE TABLE IF NOT EXISTS publications (
        session TEXT NOT NULL,
        reference TEXT NOT NULL,
        definition TEXT NOT NULL,
        path TEXT NOT NULL,
        PRIMARY KEY (session, reference)
    )''')


def publish_layout(db, session, definition):
    session = require_name(session, 'session')
    layout = build_layout(definition)
    path = assess_paths(layout, layout.initial).require_unique()
    payload = json.dumps(layout.as_definition(), sort_keys=True, separators=(',', ':'))
    reference = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    with write_transaction(db):
        db.execute('''INSERT INTO publications VALUES (?, ?, ?, ?)
            ON CONFLICT (session, reference) DO NOTHING''',
                   (session, reference, payload, json.dumps(path)))
    return Publication(reference, layout, path)


def load_publication(db, session, reference):
    row = db.execute('SELECT * FROM publications WHERE session = ? AND reference = ?',
                     (session, reference)).fetchone()
    if row is None:
        raise BusinessError('UNKNOWN_PUBLICATION', 'No such publication for this session', 404)
    return Publication(reference, build_layout(json.loads(row['definition'])),
                       tuple(json.loads(row['path'])))
