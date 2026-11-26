from control.dispatch import advance_order, deliver_local, resume_order
from control.orders import admit_order, finish_order, get_order, matching_order
from control.preview import open_layout
from endpoint.local_wiring import read_actual_wiring
from endpoint.store import write_transaction
from topology.edge_rules import canonical_edges, validate_edge_set
from topology.ports import require_name
from topology.reachability import assess_paths


def submit_replacement(db, session, operation, target, replaces, deliver=deliver_local):
    session = require_name(session, 'session')
    operation = require_name(operation, 'operation')
    replaces = require_name(replaces, 'replaces')
    target = canonical_edges(target)
    with write_transaction(db):
        if matching_order(db, session, operation, target, replaces) is None:
            layout = open_layout(db, session)
            validate_edge_set(target, layout.rules)
            assess_paths(layout, target).require_unique()
            admit_order(db, session, operation, target, replaces)
    return resume_order(db, session, operation, deliver)


def _suspended_predecessors(db, order):
    predecessors = []
    while order.replaces is not None:
        order = get_order(db, order.session, order.replaces)
        if order.status != 'suspended':
            break
        predecessors.append(order)
    return predecessors


def advance_replacement(db, session, operation, deliver=deliver_local):
    with write_transaction(db):
        new_order = get_order(db, session, operation)
        if new_order.status != 'pending':
            return new_order
        predecessors = _suspended_predecessors(db, new_order)
        actual = read_actual_wiring(db, session)
        for old_order in predecessors:
            finish_order(db, old_order, 'rejected', actual, 'SUPERSEDED')

    return advance_order(db, session, operation, deliver)
