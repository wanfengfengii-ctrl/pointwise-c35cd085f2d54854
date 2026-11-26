import json
from dataclasses import dataclass

from topology.edge_rules import EdgeSet, canonical_edges


@dataclass(frozen=True)
class WiringCommit:
    session: str
    sequence: int
    operation: str
    step: int
    owner: str
    removed: EdgeSet
    added: EdgeSet

    def as_entry(self):
        return {'sequence': self.sequence, 'operation': self.operation, 'step': self.step,
                'owner': self.owner, 'removed': sorted(self.removed), 'added': sorted(self.added)}


def initialize_commit_log(db):
    db.execute('''CREATE TABLE IF NOT EXISTS wiring_commits (
        session TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        operation TEXT NOT NULL,
        step INTEGER NOT NULL,
        owner TEXT NOT NULL,
        removed TEXT NOT NULL,
        added TEXT NOT NULL,
        PRIMARY KEY (session, sequence),
        UNIQUE (session, operation, step),
        FOREIGN KEY (session, operation, step) REFERENCES commands (session, operation, step)
    )''')


def append_commit(db, command, removed, added):
    sequence = db.execute('''SELECT COALESCE(MAX(sequence), 0) + 1
        FROM wiring_commits WHERE session = ?''', (command.session,)).fetchone()[0]
    db.execute('INSERT INTO wiring_commits VALUES (?, ?, ?, ?, ?, ?, ?)',
               (command.session, sequence, command.operation, command.step, command.owner,
                json.dumps(sorted(removed)), json.dumps(sorted(added))))
    return sequence


def read_commits(db, session, operation=None):
    sql = 'SELECT * FROM wiring_commits WHERE session = ?'
    parameters = (session,)
    if operation is not None:
        sql += ' AND operation = ?'
        parameters += (operation,)
    rows = db.execute(sql + ' ORDER BY sequence', parameters)
    return [WiringCommit(row['session'], row['sequence'], row['operation'], row['step'], row['owner'],
                         canonical_edges(json.loads(row['removed'])),
                         canonical_edges(json.loads(row['added']))) for row in rows]
