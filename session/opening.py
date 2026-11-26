from endpoint.local_wiring import install_initial_wiring
from endpoint.store import write_transaction
from review.live_path import query_live_path
from session.input_binding import resolve_input_binding
from session.status import load_session, mark_open
from topology.ports import BusinessError, require_name
from topology.publication import load_publication


def open_session(db, session, reference, requested_input):
    session = require_name(session, 'session')
    reference = require_name(reference, 'reference')
    with write_transaction(db):
        publication = load_publication(db, session, reference)
        input_port = resolve_input_binding(publication.layout, requested_input)
        status = load_session(db, session)
        if status.state == 'unopened':
            mark_open(db, session, reference, input_port)
            install_initial_wiring(db, session, publication.layout)
        elif (status.state, status.reference, status.input_port) != ('open', reference, input_port):
            raise BusinessError('SESSION_ALREADY_BOUND', 'Session already has an opening', 409)
        return query_live_path(db, session)
