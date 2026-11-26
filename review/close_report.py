from review.live_path import query_live_path
from review.order_lookup import query_orders
from review.report_store import load_report
from review.timeline import read_timeline
from topology.ports import BusinessError


def create_close_report(db, session, close_id):
    live = query_live_path(db, session)
    timeline = read_timeline(db, session)
    commits = timeline['commits']
    last_edges = commits[-1]['edges'] if commits else timeline['initial']
    if live['assessment'] != 'unique' or last_edges != live['edges']:
        raise BusinessError('UNVERIFIED_WIRING', 'Actual wiring could not be reconciled for closing', 409)
    return {'session': session, 'close_id': close_id, 'status': 'closed',
            'live': {**live, 'status': 'closed'}, 'timeline': timeline,
            'orders': query_orders(db, session)['orders']}


def query_close_report(db, session, close_id):
    report = load_report(db, session, close_id)
    if report is None:
        raise BusinessError('UNKNOWN_REPORT', 'No such close report for this session', 404)
    return report
