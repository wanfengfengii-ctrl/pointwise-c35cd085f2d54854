import copy
import http.client
import json
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from control.dispatch import deliver_local
from control.http_api import initialize_app, make_handler
from endpoint.local_wiring import apply_local_command
from endpoint.store import open_store


_SAMPLE_PATH = Path(__file__).resolve().parents[1] / 'examples' / 'day.json'
_SAMPLE = json.loads(_SAMPLE_PATH.read_text(encoding='utf-8'))
INITIAL = [['A', 'B'], ['A', 'T'], ['S', 'A']]
TARGET = [['B', 'A'], ['B', 'T'], ['S', 'B']]
AFTER_DETACH = [['A', 'T'], ['S', 'A']]


def sample_publication():
    return copy.deepcopy(_SAMPLE['publish'])


def independent_assessment(edges, start='S', listener='T'):
    links = [tuple(edge) for edge in edges]
    nodes = {start, listener} | {node for edge in links for node in edge}

    def walk(node, visits, stop_at_listener):
        if node in visits:
            raise ValueError('repeated vertex')
        visits = (*visits, node)
        if stop_at_listener and node == listener:
            return [visits]
        found = []
        for source, target in links:
            if source == node:
                found.extend(walk(target, visits, stop_at_listener))
        return found

    try:
        for node in nodes:
            walk(node, (), False)
    except ValueError:
        return 'FEEDBACK_LOOP', []
    paths = walk(start, (), True)
    if not paths:
        return 'NO_LIVE_PATH', []
    if len(paths) > 1:
        return 'DUPLICATE_LIVE_PATH', []
    return 'unique', list(paths[0])


class EndpointDelivery:
    def __init__(self, observe):
        self.observe = observe
        self.interrupt = None
        self.held = None
        self.observed = []

    def arm(self, when, *, owner=None, step=None):
        self.interrupt = (when, owner, step)
        self.held = None

    def __call__(self, db, command):
        when = None
        if self.interrupt is not None:
            mode, owner, step = self.interrupt
            if (owner is None or owner == command.owner) and (step is None or step == command.step):
                when = mode
                self.interrupt = None
                self.held = command
        if when == 'before':
            return None
        outcome = deliver_local(db, command)
        if outcome.sequence is not None:
            live = self.observe(command.session)
            self.observed.append((outcome.sequence, command.owner, live['edges']))
        return None if when == 'after' else outcome


class GuideHTTPCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Path(directory.name) / 'guide.sqlite3'
        self.delivery = EndpointDelivery(self.live)
        initialize_app(self.db)
        self.server = None
        self.start_server()
        self.addCleanup(self.stop_server)

    def start_server(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db, self.delivery))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.thread.start()

    def stop_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join()
            self.server.server_close()
            self.server = None

    def reopen(self):
        self.stop_server()
        initialize_app(self.db)
        self.start_server()

    def request(self, route, *, body=None, **query):
        method = 'GET' if body is None else 'POST'
        if query:
            route += '?' + urlencode(query)
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            payload = None if body is None else json.dumps(body)
            conn.request(method, route, payload, {'Content-Type': 'application/json'})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def publish(self, body=None):
        code, publication = self.request('/publish', body=sample_publication() if body is None else body)
        self.assertEqual(code, 200, publication)
        return publication['reference']

    def open_guide(self, body=None):
        body = sample_publication() if body is None else body
        reference = self.publish(body)
        code, live = self.request('/open', body={'session': body['session'], 'reference': reference,
                                                 'input': body['layout']['start']})
        self.assertEqual(code, 200, live)
        return live

    def live(self, session='morning'):
        code, body = self.request('/live', session=session)
        self.assertEqual(code, 200, body)
        return body

    def timeline(self, session='morning'):
        code, body = self.request('/timeline', session=session)
        self.assertEqual(code, 200, body)
        return body

    def change(self, target=TARGET, operation='K', replaces=None, session='morning'):
        body = {'session': session, 'operation': operation, 'target': target}
        if replaces is not None:
            body['replaces'] = replaces
        return self.request('/change', body=body)

    def replay(self, command):
        with closing(open_store(self.db)) as db:
            return apply_local_command(db, command.session, command.operation, command.step)
