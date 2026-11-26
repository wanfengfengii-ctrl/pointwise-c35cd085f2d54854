from dataclasses import dataclass


@dataclass(frozen=True)
class StepOutcome:
    session: str
    operation: str
    step: int
    owner: str
    state: str
    sequence: int | None = None
    reason: str | None = None


def read_commit_outcome(db, session, operation, step):
    row = db.execute('''SELECT owner, sequence FROM wiring_commits
        WHERE session = ? AND operation = ? AND step = ?''', (session, operation, step)).fetchone()
    if row is None:
        return None
    return StepOutcome(session, operation, step, row['owner'], 'applied', row['sequence'])
