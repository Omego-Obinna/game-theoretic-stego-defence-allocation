import unittest
from engine import Budget, Observation, ObservedTarget, run, LEGACY
from pilot import run_trace, KEY, SESSION, REPRESENTATIVE
from transport import emit, Config, POLICIES

SIZES = (68428, 67869, 262292)


class SensitivityTests(unittest.TestCase):
    def observations(self, policy, n=4, missing=()):
        return [Observation(t.epoch, t.channel, t.copy, t.send_ms, SIZES[t.channel-1])
                for t in emit(KEY, SESSION, [REPRESENTATIVE]*n, policy, Config(n)) if not (t.channel == 3 and t.epoch in missing)]

    def test_no_learning_at_copy_boundary(self):
        learner = ObservedTarget(Budget(1, 'objects', [True]*4, SIZES))
        for o in self.observations((1, 1, 0)):
            learner.decide(o)
            if o.send_ms <= 100:
                self.assertIsNone(learner.target)
        self.assertEqual(learner.learned, {1: 1, 2: 1, 3: 0})
        self.assertEqual(learner.target, 3)
        self.assertEqual(learner.learned_at_ms, 200)
        learner.budget.finish()

    def test_identical_prefix_same_decisions(self):
        histories = []
        for policy in ((0, 0, 0), (1, 1, 0)):
            learner = ObservedTarget(Budget(1, 'objects', [True]*4, SIZES))
            histories.append([(o, learner.decide(o), dict(learner.learned)) for o in self.observations(policy) if o.send_ms < 100])
        self.assertEqual(histories[0], histories[1])

    def test_missing_original_does_not_reveal_copy(self):
        learner = ObservedTarget(Budget(1, 'objects', [False, True, True, True], SIZES))
        for o in self.observations((0, 0, 1), missing=(0,)):
            learner.decide(o)
            if o.send_ms <= 200:
                self.assertIsNone(learner.target)
        self.assertEqual(learner.learned[3], 1)
        self.assertEqual(learner.learned_at_ms, 300)
        learner.budget.finish()

    def test_byte_target_uses_full_sizes(self):
        learner = ObservedTarget(Budget(1, 'bytes', [True]*4, SIZES))
        for o in self.observations((1, 1, 0)):
            learner.decide(o)
        self.assertEqual(learner.target, 2)  # Two C2 copies cost less than one C3.
        learner.budget.finish()

    def test_fixed_target_control_waits_and_commits(self):
        learner = ObservedTarget(Budget(1, 'objects', [True]*4, SIZES), 1)
        decisions = [(o, learner.decide(o)) for o in self.observations((1, 1, 0))]
        self.assertEqual(learner.target, 1)
        self.assertTrue(all(not decision for o, decision in decisions if o.epoch < 2))
        self.assertEqual(learner.budget.spent, 4)
        learner.budget.finish()

    def test_reservations_prevent_overspending(self):
        b = Budget('.01', 'objects', [True]*100, SIZES)  # Three units total.
        o = Observation(0, 1, 0, 0, SIZES[0])
        self.assertTrue(b.reserve_set(o, 2))
        self.assertTrue(b.consume(o))
        self.assertEqual((b.spent, b.reserved), (1, 1))
        self.assertFalse(b.reserve_set(Observation(1, 1, 0, 100, SIZES[0]), 2))
        self.assertTrue(b.consume(Observation(0, 1, 1, 100, SIZES[0])))
        self.assertTrue(b.charge(Observation(1, 2, 0, 100, SIZES[1])))
        self.assertFalse(b.charge(Observation(2, 2, 0, 200, SIZES[1])))
        b.finish()

    def test_copy_charged_to_logical_block(self):
        b = Budget('.01', 'objects', [True]*200, SIZES)
        o = Observation(99, 1, 0, 9900, SIZES[0])
        self.assertTrue(b.reserve_set(o, 2))
        b.consume(o)
        b.consume(Observation(99, 1, 1, 10000, SIZES[0]))
        self.assertEqual(b.block_spent, {0: 2, 1: 0})
        b.finish()

    def test_absent_image_not_charged_in_byte_baseline(self):
        a = Budget('.05', 'bytes', [True]*200, SIZES)
        b = Budget('.05', 'bytes', [False]+[True]*199, SIZES)
        self.assertEqual(a.cap, (sum(SIZES)*200)//20)
        self.assertEqual(b.cap, (sum(SIZES)*200-SIZES[2])//20)
        self.assertLess(b.block_caps[0], a.block_caps[0])

    def test_baseline_budget_does_not_depend_on_policy(self):
        caps = {run(p, 191001, 'E0', 'C1', .05, 'bytes', [True]*10, SIZES)['attack_cap'] for p in POLICIES}
        self.assertEqual(len(caps), 1)

    def test_outstanding_reservation_fails(self):
        b = Budget(1, 'objects', [True]*3, SIZES)
        o = Observation(0, 1, 0, 0, SIZES[0])
        b.reserve_set(o, 2)
        b.consume(o)
        with self.assertRaises(AssertionError):
            b.finish()

    def test_uncommitted_late_copy_not_suppressed(self):
        learner = ObservedTarget(Budget(1, 'objects', [True]*4, SIZES), 1)
        decisions = [(o, learner.decide(o)) for o in self.observations((1, 0, 0))]
        self.assertTrue(all(not decision for o, decision in decisions if o.copy == 1 and o.epoch < 2))

    def test_zero_budget_still_learns(self):
        r = run((0, 1, 1), 191001, 'E0', 'observe_best', 0, 'objects', [True]*5, SIZES)
        self.assertEqual(r['suppressed_objects'], 0)
        self.assertEqual(r['observed_target'], 1)
        self.assertEqual(len(r['completed_epochs']), 5)

    def test_invalid_observation_order_rejected(self):
        learner = ObservedTarget(Budget(1, 'objects', [True]*4, SIZES))
        o = Observation(0, 1, 0, 0, SIZES[0])
        learner.decide(o)
        with self.assertRaises(ValueError):
            learner.decide(o)

    def test_legacy_object_outcomes_exactly_match(self):
        for policy in POLICIES:
            for env in ('E1', 'E2'):
                for attack in LEGACY:
                    old = run_trace(policy, 191001, env, attack, .05, (3,), n=10)
                    new = run(policy, 191001, env, attack, .05, 'objects', [i != 3 for i in range(10)], SIZES)
                    for field in ('completed_epochs', 'latencies_ms', 'emitted_objects', 'natural_loss_objects', 'suppressed_objects', 'wasted_suppressions', 'event_counts', 'attack_cap'):
                        self.assertEqual(new[field], old[field])
                    self.assertEqual({k:v for k,v in new['attack_spent_per_block'].items() if v}, old['attack_spent_per_block'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
