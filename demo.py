import http.client
import json
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from control.http_api import initialize_app, make_handler


def request(port, route, body=None, **query):
    if query:
        route += '?' + urlencode(query)
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        method = 'GET' if body is None else 'POST'
        payload = None if body is None else json.dumps(body)
        connection.request(method, route, payload, {'Content-Type': 'application/json'})
        response = connection.getresponse()
        result = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError(f'{method} {route} returned {response.status}: {result}')
        return result
    finally:
        connection.close()


def run_day(port, scenario):
    publication = request(port, '/publish', scenario['publish'])
    session = publication['session']
    opened = request(port, '/open', {'session': session, 'reference': publication['reference'],
                                     'input': scenario['input']})
    if opened['path'] != ['S', 'A', 'T']:
        raise RuntimeError(f'Unexpected opening path: {opened}')
    target = scenario['change']['target']
    preview = request(port, '/preview', {'session': session, 'target': target})
    order = request(port, '/change', scenario['change'])
    live = request(port, '/live', session=session)
    sealed = request(port, '/close', scenario['close'])
    report = request(port, '/report', **scenario['close'])
    if report != sealed or report['orders'] != [order] or order['status'] != 'completed':
        raise RuntimeError('The claimed order and sealed shift report differ')

    expected = {'path': ['S', 'B', 'T'], 'edges': [['B', 'A'], ['B', 'T'], ['S', 'B']]}
    actual = {'path': live['path'], 'edges': live['edges']}
    downstream_expected = {
        'path': ['S', 'B', 'T'],
        'paths_after_commits': [['S', 'A', 'T']] * 2 + [['S', 'B', 'T']] * 3,
        'edges_after_commits': [
            [['A', 'T'], ['S', 'A']],
            [['A', 'T'], ['B', 'T'], ['S', 'A']],
            [['A', 'T'], ['B', 'T'], ['S', 'B']],
            [['B', 'T'], ['S', 'B']],
            [['B', 'A'], ['B', 'T'], ['S', 'B']],
        ],
    }
    commits = report['timeline']['commits']
    downstream_actual = {'path': report['live']['path'], 'paths_after_commits': [r['path'] for r in commits],
                         'edges_after_commits': [r['edges'] for r in commits]}
    if actual != expected or downstream_actual != downstream_expected or preview['path'] != expected['path']:
        raise RuntimeError(f'Unexpected route or commit timeline: {actual}, {downstream_actual}')
    evidence = {'case_id': 'v3', 'input': {'initial': scenario['publish']['layout']['initial'], 'target': target},
                'expected': expected, 'actual': actual, 'downstream_expected': downstream_expected,
                'downstream_actual': downstream_actual,
                'code_paths': ['control/route_search.py', 'control/dispatch.py', 'endpoint/local_wiring.py',
                               'review/timeline.py', 'review/close_report.py'],
                'oracle': 'Hand-trace the allowed edges after removing A-B, adding B-T, moving S, removing A-T and adding B-A.'}
    print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False, separators=(',', ':')))


def main():
    sample = Path(__file__).resolve().parent / 'examples' / 'day.json'
    scenario = json.loads(sample.read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / 'guide.sqlite3'
        initialize_app(db)
        with ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db)) as server:
            thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01})
            thread.start()
            try:
                run_day(server.server_port, scenario)
            finally:
                server.shutdown()
                thread.join()


if __name__ == '__main__':
    main()
