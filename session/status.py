from dataclasses import dataclass

from topology.ports import BusinessError


@dataclass(frozen=True)
class SessionStatus:
    session: str
    state: str
    reference: str | None = None
    input_port: str | None = None


def initialize_sessions(db):
    db.execute('''CREATE TABLE IF NOT EXISTS sessions (
        session TEXT PRIMARY KEY,
        state TEXT NOT NULL CHECK (state IN ('open', 'closed')),
        reference TEXT NOT NULL,
        input_port TEXT NOT NULL,
        FOREIGN KEY (session, reference) REFERENCES publications (session, reference)
    )''')


def load_session(db, session):
    row = db.execute('SELECT * FROM sessions WHERE session = ?', (session,)).fetchone()
    if row is None:
        return SessionStatus(session, 'unopened')
    return SessionStatus(**dict(row))


def require_open(db, session):
    status = load_session(db, session)
    if status.state != 'open':
        raise BusinessError('SESSION_NOT_OPEN', f'Session is {status.state}', 409)
    return status


def mark_open(db, session, reference, input_port):
    db.execute('INSERT INTO sessions VALUES (?, ?, ?, ?)',
               (session, 'open', reference, input_port))


def mark_closed(db, session):
    require_open(db, session)
    db.execute("UPDATE sessions SET state = 'closed' WHERE session = ?", (session,))
