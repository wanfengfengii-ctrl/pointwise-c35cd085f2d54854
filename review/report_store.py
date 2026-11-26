import json


def initialize_reports(db):
    db.execute('''CREATE TABLE IF NOT EXISTS reports (
        session TEXT NOT NULL REFERENCES sessions (session),
        close_id TEXT NOT NULL,
        content TEXT NOT NULL,
        PRIMARY KEY (session, close_id),
        UNIQUE (session)
    )''')


def save_report(db, session, close_id, report):
    db.execute('INSERT INTO reports VALUES (?, ?, ?)', (session, close_id, json.dumps(report)))


def load_report(db, session, close_id):
    row = db.execute('SELECT content FROM reports WHERE session = ? AND close_id = ?',
                     (session, close_id)).fetchone()
    return json.loads(row['content']) if row is not None else None
