from endpoint.local_wiring import read_actual_wiring
from session.status import load_session
from topology.ports import BusinessError
from topology.publication import load_publication
from topology.reachability import assess_paths


def query_live_path(db, session):
    status = load_session(db, session)
    if status.reference is None:
        raise BusinessError('SESSION_NOT_OPEN', 'Session has no installed wiring', 409)
    layout = load_publication(db, session, status.reference).layout
    actual = read_actual_wiring(db, session)
    assessment = assess_paths(layout, actual)
    return {'session': session, 'status': status.state, 'reference': status.reference,
            'input': status.input_port, 'assessment': assessment.state,
            'path': assessment.path, 'edges': sorted(actual)}
