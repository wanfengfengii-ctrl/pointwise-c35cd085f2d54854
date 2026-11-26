"""Regression cases for the two live-routing incident windows.

These lock the root causes behind incident.py:

* a single new T outlet must not be installed make-before-break while the old
  direct outlet still feeds the listener (duplicate live path);
* an already committed old step keeps its original receipt/sequence forever;
* a late old step that never committed is fenced once its order is settled.
"""
from contextlib import closing

from control.orders import admit_order
from control.preview import open_layout
from endpoint.commands import WiringCommand, accept_command
from endpoint.local_wiring import apply_local_command
from endpoint.store import open_store, write_transaction
from topology.edge_rules import canonical_edges
from tests.support import INITIAL, TARGET, GuideHTTPCase, independent_assessment


SINGLE_T_OUTLET = [['A', 'B'], ['B', 'T'], ['S', 'A']]


class SingleOutletSwapTests(GuideHTTPCase):
    def test_preview_uses_safe_detour_instead_of_adding_bt_first(self):
        self.open_guide()
        code, preview = self.request('/preview', body={'session': 'morning', 'target': SINGLE_T_OUTLET})
        self.assertEqual(code, 200, preview)
        self.assertEqual(preview['path'], ['S', 'A', 'B', 'T'])
        # Minimum legal detour: detach A-B, connect B-T while A-T still carries
        # the unique path, then atomically swap A's outlet A-T -> A-B.
        self.assertEqual(
            [(step['owner'], step['removed'], step['added']) for step in preview['steps']],
            [('A', [['A', 'B']], []),
             ('B', [], [['B', 'T']]),
             ('A', [['A', 'T']], [['A', 'B']])])

    def test_every_commit_stays_unique_and_ack_loss_keeps_receipt(self):
        self.open_guide()
        self.delivery.arm('after', owner='B')
        code, pending = self.change(SINGLE_T_OUTLET, 'K')
        self.assertEqual((code, pending['status']), (202, 'pending'))
        held = self.delivery.held
        self.assertIsNotNone(held)

        rows = self.timeline()['commits']
        self.assertTrue(rows)
        self.assertEqual(self.live()['edges'], rows[-1]['edges'])
        for row in rows:
            self.assertEqual(independent_assessment(row['edges'])[0], 'unique')
        committed = next(row for row in rows if row['step'] == held.step)
        # The first real commit must detach the A->B return feed; connecting
        # B->T on top of the untouched opening would leave T hearing both ways.
        first = rows[0]
        self.assertEqual((first['owner'], first['removed'], first['added']),
                         ('A', [['A', 'B']], []))
        unsafe_double_feed = {('A', 'B'), ('A', 'T'), ('B', 'T'), ('S', 'A')}
        for row in rows:
            self.assertNotEqual({tuple(edge) for edge in row['edges']}, unsafe_double_feed)

        self.reopen()
        code, done = self.change(INITIAL, 'N', 'K')
        self.assertEqual((code, done['status']), (200, 'completed'))
        self.assertEqual(self.live()['edges'], INITIAL)

        replay = self.replay(held)
        self.assertEqual((replay.state, replay.sequence), ('applied', committed['sequence']))
        # Reclaiming the old receipt after another reopen changes nothing.
        before = self.timeline()
        self.reopen()
        self.assertEqual(self.replay(held), replay)
        self.assertEqual(self.timeline(), before)
        self.assertEqual(self.change(INITIAL, 'N', 'K'), (200, done))


class LateCommandFenceTests(GuideHTTPCase):
    def test_late_unsent_step_after_supersede_is_rejected_and_stable(self):
        self.open_guide()
        self.delivery.arm('before', step=1)
        code, pending = self.change()
        self.assertEqual((code, pending['status']), (202, 'pending'))
        held = self.delivery.held
        self.assertEqual(self.live()['edges'], INITIAL)
        self.assertEqual(self.timeline()['commits'], [])

        self.reopen()
        code, replacement = self.change(INITIAL, 'N', 'K')
        self.assertEqual((code, replacement['status']), (200, 'completed'))
        self.assertEqual(self.live()['edges'], INITIAL)

        late = self.replay(held)
        self.assertEqual((late.state, late.sequence, late.reason),
                         ('rejected', None, 'SUPERSEDED'))
        self.assertEqual(self.replay(held), late)
        timeline = self.timeline()

        self.reopen()
        self.assertEqual(self.replay(held), late)
        self.assertEqual(self.live()['edges'], INITIAL, 'LATE_OLD_STEP_CHANGED_WIRING')
        self.assertEqual(self.timeline(), timeline)
        code, old = self.request('/order', session='morning', operation='K')
        self.assertEqual((code, old['status'], old['reason']), (200, 'rejected', 'SUPERSEDED'))

    def test_applied_old_step_keeps_original_receipt_after_supersede(self):
        self.open_guide()
        self.delivery.arm('after', step=1)
        code, pending = self.change()
        self.assertEqual((code, pending['status']), (202, 'pending'))
        held = self.delivery.held
        first, = self.timeline()['commits']

        self.reopen()
        code, replacement = self.change(INITIAL, 'N', 'K')
        self.assertEqual((code, replacement['status']), (200, 'completed'))

        receipt = self.replay(held)
        self.assertEqual((receipt.state, receipt.sequence), ('applied', first['sequence']))
        self.assertEqual(self.replay(held), receipt)
        self.reopen()
        self.assertEqual(self.replay(held), receipt)
        self.assertEqual(self.live()['edges'], INITIAL)
        old = self.request('/order', session='morning', operation='K')[1]
        self.assertEqual([(c['sequence'], c['operation']) for c in old['commits']],
                         [(first['sequence'], 'K')])


class EndpointSafetyGuardTests(GuideHTTPCase):
    def test_endpoint_will_not_commit_a_duplicate_path_state(self):
        self.open_guide()
        initial_edges = canonical_edges(INITIAL)
        unsafe_add = frozenset({('B', 'T')})
        with closing(open_store(self.db)) as db, write_transaction(db):
            layout = open_layout(db, 'morning')
            admit_order(db, 'morning', 'Z', initial_edges | unsafe_add)
            command = WiringCommand(
                'morning', 'Z', 1, 'B', initial_edges, frozenset(), unsafe_add)
            accept_command(db, layout, command)

        with closing(open_store(self.db)) as db:
            outcome = apply_local_command(db, 'morning', 'Z', 1)
        self.assertEqual((outcome.state, outcome.sequence, outcome.reason),
                         ('rejected', None, 'DUPLICATE_LIVE_PATH'))
        self.assertEqual(self.live()['edges'], INITIAL)
        self.assertEqual(self.timeline()['commits'], [])
        # The refused attempt is deterministic and still changes nothing.
        with closing(open_store(self.db)) as db:
            again = apply_local_command(db, 'morning', 'Z', 1)
        self.assertEqual(again, outcome)
        self.assertEqual(self.live()['edges'], INITIAL)


class ResumeAndCloseAfterIncidentTests(GuideHTTPCase):
    def test_before_window_same_operation_resumes_over_http(self):
        self.open_guide()
        self.delivery.arm('before', step=1)
        code, pending = self.change()
        self.assertEqual((code, pending['status']), (202, 'pending'))
        # Redelivering the same number and parameters resumes the held step.
        code, done = self.change()
        self.assertEqual((code, done['status']), (200, 'completed'))
        self.assertEqual(self.live()['edges'], TARGET)
        for row in self.timeline()['commits']:
            self.assertEqual(independent_assessment(row['edges'])[0], 'unique')

    def test_close_after_supersede_archives_both_orders(self):
        self.open_guide()
        self.delivery.arm('after', owner='B')
        code, pending = self.change(SINGLE_T_OUTLET, 'K')
        self.assertEqual((code, pending['status']), (202, 'pending'))

        code, restored = self.change(INITIAL, 'N', 'K')
        self.assertEqual((code, restored['status']), (200, 'completed'))
        close = {'session': 'morning', 'close_id': 'handoff-late'}
        code, report = self.request('/close', body=close)
        self.assertEqual(code, 200, report)
        self.assertEqual(report['status'], 'closed')
        states = {order['operation']: (order['status'], order['reason'])
                  for order in report['orders']}
        self.assertEqual(states['K'], ('rejected', 'SUPERSEDED'))
        self.assertEqual(states['N'], ('completed', None))
        self.assertEqual(report['live']['edges'], INITIAL)
        self.assertEqual(self.request('/report', session='morning', close_id='handoff-late'),
                         (200, report))
        self.reopen()
        self.assertEqual(self.request('/report', session='morning', close_id='handoff-late'),
                         (200, report))
