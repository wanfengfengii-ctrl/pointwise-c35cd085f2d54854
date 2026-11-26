import json

from endpoint.commands import get_command
from endpoint.commit_log import append_commit
from endpoint.outcomes import StepOutcome, read_commit_outcome
from endpoint.store import write_transaction
from topology.layout import build_layout
from topology.ports import BusinessError
from topology.reachability import assess_paths


def initialize_wiring(db):
    db.execute('''CREATE TABLE IF NOT EXISTS wiring (
        session TEXT NOT NULL REFERENCES sessions (session),
        owner TEXT NOT NULL,
        source TEXT NOT NULL,
        destination TEXT NOT NULL,
        PRIMARY KEY (session, source, destination)
    )''')


def install_initial_wiring(db, session, layout):
    owners = {rule.edge: rule.owner for rule in layout.rules}
    _add_edges(db, session, ((owners[edge], *edge) for edge in sorted(layout.initial)))


def _add_edges(db, session, owned_edges):
    db.executemany('INSERT INTO wiring VALUES (?, ?, ?, ?)',
                   ((session, *entry) for entry in owned_edges))


def read_actual_wiring(db, session):
    rows = db.execute('SELECT source, destination FROM wiring WHERE session = ?', (session,))
    return frozenset(tuple(row) for row in rows)


def apply_local_command(db, session, operation, step):
    with write_transaction(db):
        command = get_command(db, session, operation, step)
        if command is None:
            raise BusinessError('UNKNOWN_STEP', 'Endpoint has no such step', 404)
        previous = read_commit_outcome(db, session, operation, step)
        if previous is not None:
            # A real commit is the permanent endpoint receipt: redelivery always
            # reclaims the original outcome and sequence, even after later
            # replacement wiring has moved the live edges elsewhere.
            return previous
        order = db.execute('''SELECT status, reason FROM orders
            WHERE session = ? AND operation = ?''', (session, operation)).fetchone()
        if order is not None and order['status'] in ('completed', 'rejected'):
            # The case is already settled (e.g. rejected/SUPERSEDED by an
            # explicit replacement). A late step that was never actually
            # committed must not move live wiring any more.
            reason = order['reason'] or 'SETTLED_OPERATION'
            return StepOutcome(session, operation, step, command.owner, 'rejected', reason=reason)
        actual = read_actual_wiring(db, session)
        if actual != command.expected:
            return StepOutcome(session, operation, step, command.owner, 'rejected', reason='STALE_WIRING')
        candidate = (actual - command.removed) | command.added
        rejection = _unsafe_candidate_reason(db, session, candidate)
        if rejection is not None:
            return StepOutcome(session, operation, step, command.owner, 'rejected', reason=rejection)
        for source, destination in sorted(command.removed):
            deleted = db.execute('''DELETE FROM wiring WHERE session = ? AND owner = ?
                AND source = ? AND destination = ?''', (session, command.owner, source, destination))
            if deleted.rowcount != 1:
                raise RuntimeError('Persisted wiring contradicts command ownership')
        _add_edges(db, session, ((command.owner, *edge) for edge in sorted(command.added)))
        sequence = None
        if command.removed or command.added:
            sequence = append_commit(db, command, command.removed, command.added)
        return StepOutcome(session, operation, step, command.owner, 'applied', sequence)


def _unsafe_candidate_reason(db, session, candidate):
    """Defence in depth for the every-commit unique-sound/no-feedback rule."""
    row = db.execute('SELECT reference FROM sessions WHERE session = ?', (session,)).fetchone()
    if row is None or row['reference'] is None:
        return None
    stored = db.execute('SELECT definition FROM publications WHERE session = ? AND reference = ?',
                       (session, row['reference'])).fetchone()
    if stored is None:
        return None
    layout = build_layout(json.loads(stored['definition']))
    state = assess_paths(layout, candidate).state
    return {'feedback': 'FEEDBACK_LOOP', 'silent': 'NO_LIVE_PATH',
            'duplicate': 'DUPLICATE_LIVE_PATH'}.get(state)
