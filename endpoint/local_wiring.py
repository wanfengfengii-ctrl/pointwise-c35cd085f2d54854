from endpoint.commands import get_command
from endpoint.commit_log import append_commit
from endpoint.outcomes import StepOutcome, read_commit_outcome
from endpoint.store import write_transaction
from topology.ports import BusinessError


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
        actual = read_actual_wiring(db, session)
        previous = read_commit_outcome(db, session, operation, step)
        expected_after = (command.expected - command.removed) | command.added
        if previous is not None and actual == expected_after:
            return previous
        if previous is not None or actual != command.expected:
            return StepOutcome(session, operation, step, command.owner, 'rejected', reason='STALE_WIRING')
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
