import json
from dataclasses import dataclass

from topology.edge_rules import EdgeSet, canonical_edges, owned_edge_delta, validate_edge_set
from topology.ports import BusinessError


@dataclass(frozen=True)
class WiringCommand:
    session: str
    operation: str
    step: int
    owner: str
    expected: EdgeSet
    removed: EdgeSet
    added: EdgeSet


def initialize_commands(db):
    db.execute('''CREATE TABLE IF NOT EXISTS commands (
        session TEXT NOT NULL,
        operation TEXT NOT NULL,
        step INTEGER NOT NULL CHECK (step > 0),
        owner TEXT NOT NULL,
        expected TEXT NOT NULL,
        removed TEXT NOT NULL,
        added TEXT NOT NULL,
        PRIMARY KEY (session, operation, step),
        FOREIGN KEY (session, operation) REFERENCES orders (session, operation)
    )''')


def get_command(db, session, operation, step):
    row = db.execute('SELECT * FROM commands WHERE session = ? AND operation = ? AND step = ?',
                     (session, operation, step)).fetchone()
    if row is None:
        return None
    return WiringCommand(session, operation, step, row['owner'],
                         canonical_edges(json.loads(row['expected'])),
                         canonical_edges(json.loads(row['removed'])),
                         canonical_edges(json.loads(row['added'])))


def accept_command(db, layout, command):
    key = (command.session, command.operation, command.step)
    existing = get_command(db, *key)
    if existing is not None:
        if (existing.owner, existing.expected, existing.removed, existing.added) != (
                command.owner, command.expected, command.removed, command.added):
            raise BusinessError('STEP_CONFLICT', 'Step identity already has a different action', 409)
        return existing
    before = validate_edge_set(command.expected, layout.rules)
    after = validate_edge_set((before - command.removed) | command.added, layout.rules)
    delta = owned_edge_delta(layout.rules, command.owner, before, after)
    if delta != (command.removed, command.added):
        raise BusinessError('INVALID_STEP_DELTA', 'Step does not describe its expected change')
    db.execute('INSERT INTO commands VALUES (?, ?, ?, ?, ?, ?, ?)',
               (*key, command.owner, json.dumps(sorted(before)),
                json.dumps(sorted(command.removed)), json.dumps(sorted(command.added))))
    return command
