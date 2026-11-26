"""Exercise both lost-reply windows through the guide service."""
import unittest

from tests.support import GuideHTTPCase, INITIAL, independent_assessment


class Incident(GuideHTTPCase):
    def test_single_new_outlet(self):
        self.open_guide()
        target = [['A', 'B'], ['B', 'T'], ['S', 'A']]
        code, preview = self.request('/preview', body={'session': 'morning', 'target': target})
        self.assertEqual((code, preview['path']), (200, ['S', 'A', 'B', 'T']))
        self.delivery.arm('after', owner='B')
        code, pending = self.change(target)
        self.assertEqual((code, pending['status']), (202, 'pending'))
        held = self.delivery.held
        self.assertIsNotNone(held)
        rows = self.timeline()['commits']
        self.assertTrue(rows)
        self.assertEqual(self.live()['edges'], rows[-1]['edges'])
        for row in rows:
            self.assertEqual(independent_assessment(row['edges'])[0], 'unique')
        committed = next(row for row in rows if row['step'] == held.step)

        self.reopen()
        code, done = self.change(INITIAL, 'N', 'K')
        self.assertEqual((code, done['status']), (200, 'completed'))
        self.assertEqual(self.live()['edges'], INITIAL)
        before = self.timeline()
        replay = self.replay(held)
        self.assertEqual((replay.state, replay.sequence), ('applied', committed['sequence']))
        self.reopen()
        self.assertEqual(self.timeline(), before)
        for row in before['commits']:
            self.assertEqual(independent_assessment(row['edges'])[0], 'unique')
        self.assertEqual(self.change(INITIAL, 'N', 'K'), (200, done))

    def test_delayed_return_line(self):
        self.open_guide()
        self.delivery.arm('before', step=1)
        self.assertEqual(self.change()[0], 202)
        held = self.delivery.held
        self.assertIsNotNone(held)
        self.assertEqual(self.live()['edges'], INITIAL)
        self.assertEqual(self.timeline()['commits'], [])
        self.reopen()
        code, order = self.change(INITIAL, 'N', 'K')
        if code == 202:
            self.replay(held)
            code, order = self.change(INITIAL, 'N', 'K')
        self.assertEqual((code, order['status']), (200, 'completed'))
        before = self.timeline()
        self.replay(held)
        self.reopen()
        self.assertEqual(self.live()['edges'], INITIAL, 'LATE_OLD_STEP_CHANGED_WIRING')
        self.assertEqual(self.timeline(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
