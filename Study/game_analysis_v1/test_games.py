import unittest
import numpy as np
from games import solve_zero_sum, shapley, cooperative, baselines, evaluate, POLICIES, subset_indices


class GameTests(unittest.TestCase):
    def test_matching_pennies(self):
        r = solve_zero_sum([[1, -1], [-1, 1]])
        np.testing.assert_allclose(r['x'], [.5, .5], atol=1e-9)
        self.assertAlmostEqual(r['value'], 0)

    def test_rock_paper_scissors(self):
        r = solve_zero_sum([[0, -1, 1], [1, 0, -1], [-1, 1, 0]])
        np.testing.assert_allclose(r['x'], [1/3]*3, atol=1e-9)
        self.assertAlmostEqual(r['checks']['restricted_exploitability'], 0)

    def test_pure_saddle(self):
        r = solve_zero_sum([[.2, .3], [.7, .8]])
        self.assertAlmostEqual(r['value'], .7)
        np.testing.assert_allclose(r['x'], [0, 1])

    def test_one_by_one_and_translation(self):
        self.assertAlmostEqual(solve_zero_sum([[.42]])['value'], .42)
        r = solve_zero_sum([[10, 11], [11, 10]])
        self.assertAlmostEqual(r['value'], 10.5)

    def test_additive_shapley(self):
        v = {s: sum([.1, .2, .3][i] for i in range(3) if s & (1 << i)) for s in range(8)}
        np.testing.assert_allclose(shapley(v), [.1, .2, .3])

    def test_symmetric_unanimity(self):
        np.testing.assert_allclose(shapley({s: float(s == 7) for s in range(8)}), [1/3]*3)

    def test_dummy_player(self):
        np.testing.assert_allclose(shapley({s: float(s & 1 != 0) for s in range(8)}), [1, 0, 0])

    def test_coalitions_keep_base_policy(self):
        for s in range(8):
            self.assertIn(POLICIES.index('000'), subset_indices(POLICIES, s))

    def test_zero_budget_zero_contributions(self):
        r = cooperative(np.array([[.8, .9]]), ['000'])
        np.testing.assert_allclose(r['shapley'], [0, 0, 0])
        self.assertTrue(r['core_nonempty'])

    def test_empty_core_detected(self):
        # Each pair contributes one but grand worth stays one: balancedness fails.
        matrix = [[float(p.count('1') >= 2)] for p in POLICIES]
        r = cooperative(matrix, list(POLICIES))
        self.assertFalse(r['core_nonempty'])
        self.assertFalse(r['shapley_in_core'])

    def test_uniform_and_equal_spending(self):
        matrix = np.array([[.8, .8], [.9, .8], [.8, .9]])
        policies = ['000', '100', '001']
        b = baselines(matrix, policies, [0, .2, .6], [.2, .2, .6], [.1, 0, .1])
        np.testing.assert_allclose(b['uniform_feasible'], [1/3]*3)
        np.testing.assert_allclose(b['equal_expected_channel_bytes'], [1, 0, 0])

    def test_evaluation_cost_and_worst_case(self):
        r = evaluate([.5, .5], [[.8, 1], [1, .6]], [0, 1])
        self.assertAlmostEqual(r['worst_case'], .8)
        self.assertAlmostEqual(r['expected_extra_fraction'], .5)

    def test_invalid_matrix(self):
        with self.assertRaises(ValueError):
            solve_zero_sum([[float('nan')]])

    def test_balanced_seventy_percent_cap(self):
        policies = ['000', '001', '010', '100', '110']
        fractions = [.17, .17, .66]
        extra = [sum(int(p[i]) * fractions[i] for i in range(3)) for p in policies]
        r = baselines(np.ones((5, 2)), policies, extra, fractions, [.1]*3)
        np.testing.assert_allclose(r['balanced_equal_repetition_probability'], [0, .5, 0, 0, .5])

    def test_balanced_eighty_five_percent_cap(self):
        policies = list(POLICIES[:-1])
        fractions = [.17, .17, .66]
        extra = [sum(int(p[i]) * fractions[i] for i in range(3)) for p in policies]
        r = baselines(np.ones((7, 2)), policies, extra, fractions, [.1]*3)
        expected = [1/3 if p in ('011', '101', '110') else 0 for p in policies]
        np.testing.assert_allclose(r['balanced_equal_repetition_probability'], expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
