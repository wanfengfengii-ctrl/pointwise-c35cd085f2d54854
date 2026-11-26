from tests.support import AFTER_DETACH, GuideHTTPCase, INITIAL, TARGET, independent_assessment


class ReplacementTests(GuideHTTPCase):
    def test_resume_after_lost_ack(self):
        self.open_guide()
        self.delivery.arm('after', step=1)
        code, pending = self.change()
        self.assertEqual((code, pending['status']), (202, 'pending'))
        first, = self.timeline()['commits']
        self.assertEqual((first['sequence'], first['operation']), (1, 'K'))
        self.assertEqual(first['edges'], AFTER_DETACH)
        held = self.delivery.held
        self.reopen()
        self.assertEqual(self.request('/order', session='morning', operation='K'), (200, pending))
        replay = self.replay(held)
        self.assertEqual((replay.state, replay.sequence, replay.step, replay.operation), ('applied', 1, held.step, 'K'))
        self.assertEqual(self.timeline()['commits'], [first])
        code, done = self.change()
        self.assertEqual((code, done['status']), (200, 'completed'))
        self.assertEqual(self.live()['edges'], TARGET)
        self.assertEqual(self.request('/order', session='morning', operation='K'), (200, done))
        self.assertEqual(self.change(), (200, done))
        self.assertEqual(self.replay(held), replay)
        self.assertEqual(sum(entry['step'] == held.step for entry in done['commits']), 1)

    def test_late_step_after_replace(self):
        self.open_guide()
        self.delivery.arm('before', step=1)
        code, pending = self.change()
        self.assertEqual((code, pending['status']), (202, 'pending'))
        held = self.delivery.held
        self.assertEqual(held.removed, frozenset({('A', 'B')}))
        self.assertEqual(self.live()['edges'], INITIAL)
        self.assertEqual(self.timeline()['commits'], [])
        self.reopen()
        code, replacement = self.change(INITIAL, 'N', 'K')
        if code == 202:
            self.replay(held)
            code, replacement = self.change(INITIAL, 'N', 'K')
        self.assertEqual((code, replacement['status']), (200, 'completed'))
        self.assertEqual(self.live()['edges'], INITIAL)
        completed_timeline = self.timeline()
        self.replay(held)
        self.reopen()
        self.assertEqual(self.live()['edges'], INITIAL, 'LATE_OLD_STEP_CHANGED_WIRING')
        self.assertEqual(self.timeline(), completed_timeline)
        if completed_timeline['commits']:
            self.assert_replacement_commits(completed_timeline['commits'])
        self.assertEqual(self.change(INITIAL, 'N', 'K'), (200, replacement))
        self.assertEqual(self.request('/order', session='morning', operation='N'), (200, replacement))
        old_code, old = self.request('/order', session='morning', operation='K')
        self.assertEqual(old_code, 200)
        self.assertEqual((old['status'], old['reason']), ('rejected', 'SUPERSEDED'))
        self.assertEqual(self.change(), (409, old))

    def test_replace_after_old_commit(self):
        self.open_guide()
        self.delivery.arm('after', step=1)
        code, pending = self.change()
        self.assertEqual((code, pending['status']), (202, 'pending'))
        first, = self.timeline()['commits']
        held = self.delivery.held
        self.assertEqual(self.live()['edges'], AFTER_DETACH)
        self.reopen()
        code, replacement = self.change(INITIAL, 'N', 'K')
        self.assertEqual((code, replacement['status']), (200, 'completed'))
        self.assertEqual(self.live()['edges'], INITIAL)
        timeline = self.timeline()
        self.assertEqual(timeline['commits'][0], first)
        self.assert_replacement_commits(timeline['commits'])
        self.assertEqual(self.replay(held).sequence, first['sequence'])
        self.reopen()
        self.assertEqual(self.timeline(), timeline)
        self.assertEqual(self.live()['edges'], INITIAL)
        old = self.request('/order', session='morning', operation='K')[1]
        self.assertEqual(old['reason'], 'SUPERSEDED')
        self.assertEqual([(entry['sequence'], entry['operation']) for entry in old['commits']], [(1, 'K')])
        self.assertEqual(self.request('/order', session='morning', operation='N'), (200, replacement))
        self.assertEqual(self.change(INITIAL, 'N', 'K'), (200, replacement))

    def assert_replacement_commits(self, commits):
        self.assertEqual([(row['sequence'], row['operation'], row['owner'], row['removed'], row['added'])
                          for row in commits],
                         [(1, 'K', 'A', [['A', 'B']], []), (2, 'N', 'A', [], [['A', 'B']])])
        for row in commits:
            self.assertEqual(independent_assessment(row['edges']), ('unique', ['S', 'A', 'T']))

    def test_conflicting_operation_reuse(self):
        self.open_guide()
        code, done = self.change()
        self.assertEqual((code, done['status']), (200, 'completed'))
        before = (self.live(), self.timeline())
        for changed_target, replaces in [(INITIAL, None), (TARGET[1:], None), (TARGET, 'other')]:
            with self.subTest(target=changed_target, replaces=replaces):
                code, error = self.change(changed_target, replaces=replaces)
                self.assertEqual((code, error['reason']), (409, 'OPERATION_CONFLICT'))
                self.assertEqual(self.request('/order', session='morning', operation='K'), (200, done))
                self.assertEqual((self.live(), self.timeline()), before)
        self.assertEqual(self.change(list(reversed(TARGET))), (200, done))
