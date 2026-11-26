from control.http_api import initialize_app
from tests.support import GuideHTTPCase, TARGET, independent_assessment


class ReviewTests(GuideHTTPCase):
    def test_close_and_reopen(self):
        self.open_guide()
        self.delivery.arm('after', step=1)
        code, pending = self.change()
        self.assertEqual((code, pending['status']), (202, 'pending'))
        self.assertEqual(independent_assessment(self.live()['edges']), ('unique', ['S', 'A', 'T']))
        self.assertEqual(len(self.timeline()['commits']), 1)
        close = {'session': 'morning', 'close_id': 'handoff-1'}
        code, error = self.request('/close', body=close)
        self.assertEqual((code, error['reason']), (409, 'PENDING_ORDERS'))
        self.assertEqual(self.request('/report', **close)[0], 404)
        self.assertEqual(self.request('/session', session='morning')[1]['state'], 'open')

        code, completed = self.change()
        self.assertEqual((code, completed['status']), (200, 'completed'))
        live = self.live()
        timeline = self.timeline()
        code, report = self.request('/close', body=close)
        self.assertEqual((code, report['status']), (200, 'closed'))
        self.assertEqual(report['live'], {**live, 'status': 'closed'})
        self.assertEqual(report['orders'], [completed])
        self.assertEqual(report['timeline'], timeline)
        entries = timeline['commits']
        self.assertEqual([(r['sequence'], r['owner'], r['edges']) for r in entries], self.delivery.observed)
        self.assertEqual([r['owner'] for r in entries], ['A', 'B', 'S', 'A', 'B'])
        expected_deltas = [
            ([['A', 'B']], []), ([], [['B', 'T']]), ([['S', 'A']], [['S', 'B']]),
            ([['A', 'T']], []), ([], [['B', 'A']]),
        ]
        self.assertEqual([(r['removed'], r['added']) for r in entries], expected_deltas)
        self.assertEqual([r['operation'] for r in entries], ['K'] * len(entries))
        self.assertEqual(self.request('/close', body=close), (200, report))

        self.reopen()
        initialize_app(self.db)
        self.assertEqual(self.request('/report', **close), (200, report))
        self.assertEqual(self.request('/order', session='morning', operation='K'), (200, completed))
        self.assertEqual(self.change(), (200, completed))
        self.assertEqual(self.timeline(), timeline)
        self.assertEqual(self.live(), report['live'])
        self.assertEqual(self.live()['edges'], TARGET)
        code, error = self.change(operation='after-close')
        self.assertEqual((code, error['reason']), (409, 'SESSION_NOT_OPEN'))
        self.assertEqual(self.request('/report', session='morning', close_id='unknown')[0], 404)
        self.assertEqual(self.request('/order', session='morning', operation='unknown')[0], 404)
