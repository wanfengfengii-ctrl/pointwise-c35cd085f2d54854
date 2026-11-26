from control.orders import has_pending_orders
from endpoint.store import write_transaction
from review.close_report import create_close_report
from review.report_store import load_report, save_report
from session.status import mark_closed, require_open
from topology.ports import BusinessError, require_name


def close_session(db, session, close_id):
    session = require_name(session, 'session')
    close_id = require_name(close_id, 'close_id')
    with write_transaction(db):
        report = load_report(db, session, close_id)
        if report is not None:
            return report
        require_open(db, session)
        if has_pending_orders(db, session):
            raise BusinessError('PENDING_ORDERS', 'Resolve pending changes before closing', 409)
        report = create_close_report(db, session, close_id)
        save_report(db, session, close_id, report)
        mark_closed(db, session)
        return report
