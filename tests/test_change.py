from itertools import combinations

from tests.support import GuideHTTPCase, INITIAL, TARGET, independent_assessment


class ChangeTests(GuideHTTPCase):
    def test_live_change(self):
        self.open_guide()
        before = (self.live(), self.timeline(), self.request('/orders', session='morning'))
        code, preview = self.request('/preview', body={'session': 'morning', 'target': TARGET})
        self.assertEqual(code, 200, preview)
        self.assertEqual(preview['path'], ['S', 'B', 'T'])
        self.assertGreater(len(preview['steps']), 1)
        self.assertEqual((self.live(), self.timeline(), self.request('/orders', session='morning')), before)

        self.delivery.arm('after', owner='B')
        code, pending = self.change()
        for _, _, edges in self.delivery.observed:
            marker, _ = independent_assessment(edges)
            self.assertEqual(marker, 'unique', marker)
        self.assertIsNotNone(self.delivery.held)
        self.assertEqual((code, pending['status']), (202, 'pending'))
        self.assertEqual(self.request('/order', session='morning', operation='K'), (200, pending))

        code, order = self.change(target=list(reversed(TARGET)))
        self.assertEqual((code, order['status']), (200, 'completed'))
        self.assertEqual(order['final_edges'], TARGET)
        self.assertEqual(self.live()['edges'], TARGET)
        self.assertEqual(self.live()['path'], ['S', 'B', 'T'])
        commits = self.timeline()['commits']
        self.assertEqual(len(commits), len(preview['steps']))
        self.assertEqual(self.delivery.observed,
                         [(entry['sequence'], entry['owner'], entry['edges']) for entry in commits])
        previous = {tuple(edge) for edge in INITIAL}
        for number, entry in enumerate(commits, 1):
            marker, path = independent_assessment(entry['edges'])
            self.assertEqual(marker, 'unique', marker)
            self.assertEqual(entry['path'], path)
            self.assertEqual((entry['sequence'], entry['operation']), (number, 'K'))
            edges = {tuple(edge) for edge in entry['edges']}
            self.assertEqual(entry['removed'], [list(edge) for edge in sorted(previous - edges)])
            self.assertEqual(entry['added'], [list(edge) for edge in sorted(edges - previous)])
            self.assertNotEqual(previous, edges)
            previous = edges

    def test_no_safe_transition(self):
        x = [['S', 'A'], ['A', 'B'], ['B', 'T']]
        y = [['S', 'B'], ['B', 'A'], ['A', 'T']]
        self.assertEqual(independent_assessment(x), ('unique', ['S', 'A', 'B', 'T']))
        self.assertEqual(independent_assessment(y), ('unique', ['S', 'B', 'A', 'T']))
        for count in range(3):
            for subset in combinations(x, count):
                self.assertEqual(independent_assessment(subset)[0], 'NO_LIVE_PATH')
        for count in range(1, 4):
            for subset in combinations(y, count):
                self.assertIn(independent_assessment(x + list(subset))[0],
                              ('DUPLICATE_LIVE_PATH', 'FEEDBACK_LOOP'))

        self.open_guide({'session': 'crossed', 'layout': {
            'ports': ['S', 'A', 'B', 'T'], 'start': 'S', 'listener': 'T', 'initial': x,
            'allowed': [[*edge, 'X'] for edge in x] + [[*edge, 'Y'] for edge in y],
        }})
        before = self.live('crossed')
        timeline = self.timeline('crossed')
        code, preview = self.request('/preview', body={'session': 'crossed', 'target': y})
        self.assertEqual((code, preview['reason']), (422, 'UNREACHABLE_TARGET'))
        code, change = self.change(y, session='crossed')
        self.assertEqual((code, change['reason']), (422, 'UNREACHABLE_TARGET'))
        self.assertEqual(self.request('/order', session='crossed', operation='K')[0], 404)
        self.assertEqual(self.live('crossed'), before)
        self.assertEqual(self.timeline('crossed'), timeline)

        code, preview = self.request('/preview', body={'session': 'crossed', 'target': x})
        self.assertEqual((code, preview['steps']), (200, []))
        code, change = self.change(x, session='crossed')
        self.assertEqual((code, change['status'], change['commits']), (200, 'completed', []))
        self.assertEqual(self.live('crossed'), before)
        self.assertEqual(self.timeline('crossed'), timeline)
