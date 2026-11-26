import json
from dataclasses import dataclass

from session.status import require_open
from topology.edge_rules import EdgeSet, canonical_edges
from topology.ports import BusinessError, require_name


@dataclass(frozen=True)
class Order:
    session: str
    operation: str
    target: EdgeSet
    replaces: str | None
    status: str
    progress: int
    waiting_step: int | None
    reason: str | None
    final_edges: EdgeSet | None


def initialize_orders(db):
    db.execute('''CREATE TABLE IF NOT EXISTS orders (
        session TEXT NOT NULL REFERENCES sessions (session),
        operation TEXT NOT NULL,
        target TEXT NOT NULL,
        replaces TEXT,
        status TEXT NOT NULL CHECK (status IN ('pending', 'suspended', 'completed', 'rejected')),
        progress INTEGER NOT NULL DEFAULT 0,
        waiting_step INTEGER,
        reason TEXT,
        final_edges TEXT,
        PRIMARY KEY (session, operation),
        FOREIGN KEY (session, replaces) REFERENCES orders (session, operation)
    )''')
    db.execute('''CREATE UNIQUE INDEX IF NOT EXISTS orders_one_active
        ON orders (session) WHERE status = 'pending' ''')


def _decode_order(row):
    data = dict(row)
    data['target'] = canonical_edges(json.loads(data['target']))
    if data['final_edges'] is not None:
        data['final_edges'] = canonical_edges(json.loads(data['final_edges']))
    return Order(**data)


def get_order(db, session, operation):
    row = db.execute('SELECT * FROM orders WHERE session = ? AND operation = ?',
                     (session, operation)).fetchone()
    return _decode_order(row) if row is not None else None


def matching_order(db, session, operation, target, replaces):
    order = get_order(db, session, operation)
    if order is not None and (order.target, order.replaces) != (target, replaces):
        raise BusinessError('OPERATION_CONFLICT', 'Operation already has different parameters', 409)
    return order


def admit_order(db, session, operation, target, replaces=None):
    operation = require_name(operation, 'operation')
    target = canonical_edges(target)
    existing = matching_order(db, session, operation, target, replaces)
    if existing is not None:
        return existing
    require_open(db, session)
    if replaces is not None:
        old = get_order(db, session, replaces)
        if old is None:
            raise BusinessError('UNKNOWN_OPERATION', 'No such operation to replace', 404)
        if old.status != 'pending':
            raise BusinessError('REPLACEMENT_NOT_PENDING', 'Replacement requires the active order', 409)
        db.execute("UPDATE orders SET status = 'suspended' WHERE session = ? AND operation = ?",
                   (session, replaces))
    elif has_pending_orders(db, session):
        raise BusinessError('CHANGE_IN_PROGRESS', 'Resume or replace the active operation', 409)
    db.execute('''INSERT INTO orders (session, operation, target, replaces, status)
        VALUES (?, ?, ?, ?, 'pending')''', (session, operation, json.dumps(sorted(target)), replaces))
    return get_order(db, session, operation)


def update_order_progress(db, order, progress, waiting_step):
    db.execute('''UPDATE orders SET progress = ?, waiting_step = ?
        WHERE session = ? AND operation = ? AND status = 'pending' ''',
               (progress, waiting_step, order.session, order.operation))


def finish_order(db, order, status, actual, reason=None):
    db.execute('''UPDATE orders SET status = ?, reason = ?, waiting_step = NULL, final_edges = ?
        WHERE session = ? AND operation = ? AND status IN ('pending', 'suspended')''',
               (status, reason, json.dumps(sorted(actual)), order.session, order.operation))


def has_pending_orders(db, session):
    return db.execute('''SELECT 1 FROM orders WHERE session = ?
        AND status IN ('pending', 'suspended') LIMIT 1''', (session,)).fetchone() is not None


def list_session_orders(db, session):
    rows = db.execute('SELECT * FROM orders WHERE session = ? ORDER BY rowid', (session,))
    return [_decode_order(row) for row in rows]
