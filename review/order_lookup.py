from control.orders import get_order, list_session_orders
from endpoint.commit_log import read_commits
from topology.ports import BusinessError


def _order_view(db, order):
    status = 'pending' if order.status == 'suspended' else order.status
    return {'session': order.session, 'operation': order.operation, 'status': status,
            'target': sorted(order.target), 'replaces': order.replaces, 'reason': order.reason,
            'final_edges': None if order.final_edges is None else sorted(order.final_edges),
            'commits': [entry.as_entry() for entry in read_commits(db, order.session, order.operation)]}


def query_order(db, session, operation):
    order = get_order(db, session, operation)
    if order is None:
        raise BusinessError('UNKNOWN_OPERATION', 'No such operation for this session', 404)
    return _order_view(db, order)


def query_orders(db, session):
    return {'session': session, 'orders': [_order_view(db, order)
                                           for order in list_session_orders(db, session)]}
