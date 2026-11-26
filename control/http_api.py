import argparse
import json
from contextlib import closing
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from control.dispatch import deliver_local, submit_change
from control.orders import initialize_orders
from control.preview import preview_change
from control.replacement import submit_replacement
from endpoint.reopen import reopen_endpoint
from endpoint.store import open_store, read_transaction, write_transaction
from review.close_report import query_close_report
from review.live_path import query_live_path
from review.order_lookup import query_order, query_orders
from review.report_store import initialize_reports
from review.timeline import read_timeline
from session.closing import close_session
from session.opening import open_session
from session.status import initialize_sessions, load_session
from topology.ports import BusinessError, require_name
from topology.publication import initialize_publications, publish_layout


def initialize_app(path):
    with closing(reopen_endpoint(path)) as db, write_transaction(db):
        initialize_publications(db)
        initialize_sessions(db)
        initialize_orders(db)
        initialize_reports(db)


def _get(db, route, query):
    def parameter(name):
        values = query.get(name, [])
        if len(values) != 1:
            raise BusinessError('INVALID_QUERY', f'Expected one {name} parameter', 400)
        return require_name(values[0], name)

    if route not in {'/session', '/live', '/timeline', '/orders', '/order', '/report'}:
        raise BusinessError('UNKNOWN_ROUTE', 'Unknown HTTP route', 404)
    session = parameter('session')
    if route == '/session':
        return asdict(load_session(db, session))
    if route == '/live':
        return query_live_path(db, session)
    if route == '/timeline':
        return read_timeline(db, session)
    if route == '/orders':
        return query_orders(db, session)
    if route == '/order':
        return query_order(db, session, parameter('operation'))
    return query_close_report(db, session, parameter('close_id'))


def _post(db, route, body, deliver):
    if route not in {'/publish', '/open', '/preview', '/change', '/close'}:
        raise BusinessError('UNKNOWN_ROUTE', 'Unknown HTTP route', 404)
    session = require_name(body.get('session'), 'session')
    if route == '/publish':
        publication = publish_layout(db, session, body.get('layout'))
        return 200, {'status': 'published', 'session': session,
                     'reference': publication.reference, 'path': publication.path}
    if route == '/open':
        return 200, open_session(db, session, body.get('reference'), body.get('input'))
    if route == '/preview':
        with read_transaction(db):
            return 200, preview_change(db, session, body.get('target')).as_response()
    if route == '/close':
        return 200, close_session(db, session, body.get('close_id'))

    operation = body.get('operation')
    target = body.get('target')
    replaces = body.get('replaces')
    if replaces is None:
        submit_change(db, session, operation, target, deliver)
    else:
        submit_replacement(db, session, operation, target, replaces, deliver)
    with read_transaction(db):
        result = query_order(db, session, operation)
    if result['status'] == 'pending':
        return 202, result
    if result['status'] == 'rejected':
        return (422 if result['reason'] == 'UNREACHABLE_TARGET' else 409), result
    return 200, result


def make_handler(path, deliver=deliver_local):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status, payload):
            data = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            lengths = self.headers.get_all('Content-Length', [])
            try:
                if len(lengths) != 1 or self.headers.get('Transfer-Encoding') is not None:
                    raise ValueError('expected one content length')
                length = int(lengths[0])
                if length <= 0:
                    raise ValueError('empty body')
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('incomplete body')
                body = json.loads(raw.decode('utf-8'))
                if not isinstance(body, dict):
                    raise ValueError('expected a JSON object')
            except (ValueError, RecursionError) as error:
                raise BusinessError('INVALID_JSON', 'Expected a complete UTF-8 JSON object', 400) from error
            return body

        def do_GET(self):
            self._serve(False)

        def do_POST(self):
            self._serve(True)

        def _serve(self, post):
            try:
                address = urlsplit(self.path)
                with closing(open_store(path)) as db:
                    if post:
                        status, result = _post(db, address.path, self._body(), deliver)
                    else:
                        with read_transaction(db):
                            result = _get(db, address.path, parse_qs(address.query, keep_blank_values=True))
                        status = 200
            except BusinessError as error:
                status = error.http_status
                result = {'status': 'rejected', 'reason': error.code, 'detail': str(error)}
            self._reply(status, result)

        def log_message(self, format, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description='Haiyu live guide routing service')
    parser.add_argument('--db', required=True, help='SQLite database path')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    initialize_app(args.db)
    with ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(args.db)) as server:
        print(f'Listening on 127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return


if __name__ == '__main__':
    main()
