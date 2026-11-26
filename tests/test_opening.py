from tests.support import GuideHTTPCase, INITIAL, sample_publication


class OpeningTests(GuideHTTPCase):
    def test_open_published_route(self):
        reference = self.publish()
        self.assertEqual(self.publish(), reference)
        body = {'session': 'morning', 'reference': reference, 'input': 'A'}
        code, error = self.request('/open', body=body)
        self.assertEqual((code, error['reason']), (422, 'INPUT_MISMATCH'))
        self.assertEqual(self.request('/session', session='morning')[1]['state'], 'unopened')
        self.assertEqual(self.request('/live', session='morning')[0], 409)

        body['input'] = 'S'
        code, opened = self.request('/open', body=body)
        self.assertEqual(code, 200, opened)
        self.assertEqual(opened['status'], 'open')
        self.assertEqual(opened['input'], 'S')
        self.assertEqual(opened['path'], ['S', 'A', 'T'])
        self.assertEqual(opened['edges'], INITIAL)
        self.assertEqual(self.live(), opened)
        self.assertEqual(self.timeline()['commits'], [])

    def test_reject_feedback(self):
        for name, extra_ports, rules, initial, reason in [
            ('listener feedback', [], [['T', 'A', 'A']],
             [['S', 'A'], ['A', 'T'], ['T', 'A']], 'FEEDBACK_LOOP'),
            ('silent feedback', ['U', 'V'], [['U', 'V', 'X'], ['V', 'U', 'X']],
             [['S', 'A'], ['A', 'T'], ['U', 'V'], ['V', 'U']], 'FEEDBACK_LOOP'),
            ('unknown port', [], [['S', 'Z', 'S']], [['S', 'A'], ['A', 'T']], 'UNKNOWN_PORT'),
            ('silence', [], [], [['S', 'A']], 'NO_LIVE_PATH'),
            ('duplicate sound', [], [], INITIAL + [['B', 'T']], 'DUPLICATE_LIVE_PATH'),
            ('no ownership rule', [], [], [['S', 'T']], 'UNALLOWED_EDGE'),
            ('two owners', [], [['S', 'A', 'B']], INITIAL, 'DUPLICATE_EDGE_RULE'),
        ]:
            with self.subTest(name=name):
                request = sample_publication()
                request['session'] = name
                request['layout']['ports'].extend(extra_ports)
                request['layout']['allowed'].extend(rules)
                request['layout']['initial'] = initial
                code, rejected = self.request('/publish', body=request)
                self.assertEqual((code, rejected['reason']), (422, reason))
                self.assertNotIn('reference', rejected)
                opened, error = self.request('/open', body={'session': name, 'reference': 'unpublished', 'input': 'S'})
                self.assertEqual((opened, error['reason']), (404, 'UNKNOWN_PUBLICATION'))
                self.assertEqual(self.request('/session', session=name)[1]['state'], 'unopened')
