from endpoint.commit_log import read_commits
from session.status import load_session
from topology.ports import BusinessError
from topology.publication import load_publication
from topology.reachability import assess_paths


def read_timeline(db, session):
    status = load_session(db, session)
    if status.reference is None:
        raise BusinessError('SESSION_NOT_OPEN', 'Session has no installed wiring', 409)
    layout = load_publication(db, session, status.reference).layout
    actual = layout.initial
    entries = []
    for commit in read_commits(db, session):
        actual = (actual - commit.removed) | commit.added
        assessment = assess_paths(layout, actual)
        entries.append({**commit.as_entry(), 'edges': sorted(actual),
                        'assessment': assessment.state, 'path': assessment.path})
    return {'session': session, 'initial': sorted(layout.initial), 'commits': entries}
