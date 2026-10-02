"""Restricted zero-sum optimisation and budget-conditioned capability attribution."""
import itertools
import math
import numpy as np
from scipy.optimize import linprog

TOL = 1e-8
POLICIES = tuple(''.join(map(str, p)) for p in itertools.product((0, 1), repeat=3))
COALITIONS = tuple(range(8))  # bit i represents capability Ri+1


def support_mask(policy):
    return sum((1 << i) for i, ch in enumerate(policy) if ch == '1')


def subset_indices(policies, coalition):
    return [i for i, p in enumerate(policies) if support_mask(p) & ~coalition == 0]


def checked_lp(**kwargs):
    result = linprog(method='highs', options={'dual_feasibility_tolerance': 1e-9, 'primal_feasibility_tolerance': 1e-9}, **kwargs)
    if not result.success:
        raise RuntimeError(result.message)
    return result


def solve_zero_sum(matrix):
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or min(matrix.shape) < 1 or not np.isfinite(matrix).all():
        raise ValueError('Finite nonempty matrix required')
    m, n = matrix.shape
    primal = checked_lp(c=np.r_[np.zeros(m), -1],
        A_ub=np.c_[-matrix.T, np.ones(n)], b_ub=np.zeros(n),
        A_eq=np.array([np.r_[np.ones(m), 0]]), b_eq=[1], bounds=[(0, None)] * m + [(None, None)])
    dual = checked_lp(c=np.r_[np.zeros(n), 1],
        A_ub=np.c_[matrix, -np.ones(m)], b_ub=np.zeros(m),
        A_eq=np.array([np.r_[np.ones(n), 0]]), b_eq=[1], bounds=[(0, None)] * n + [(None, None)])
    x, y = primal.x[:-1], dual.x[:-1]
    lower, upper = float(np.min(x @ matrix)), float(np.max(matrix @ y))
    check = {'duality_gap': float(dual.fun + primal.fun), 'restricted_exploitability': upper - lower,
             'simplex_error': float(max(abs(x.sum() - 1), abs(y.sum() - 1))),
             'min_probability': float(min(x.min(), y.min())),
             'primal_constraint_violation': max(0., float(primal.x[-1] - lower)),
             'dual_constraint_violation': max(0., float(upper - dual.x[-1]))}
    if (abs(check['duality_gap']) > TOL or not -TOL <= upper - lower <= TOL or
        check['simplex_error'] > TOL or check['min_probability'] < -TOL or
        max(check['primal_constraint_violation'], check['dual_constraint_violation']) > TOL):
        raise RuntimeError(f'Invalid game solution: {check}')
    return {'x': x.tolist(), 'y': y.tolist(), 'value': lower, 'upper_value': upper, 'checks': check}


def shapley(values):
    if set(values) != set(COALITIONS) or abs(values[0]) > TOL:
        raise ValueError('Eight coalition values with v(empty)=0 required')
    answer = np.zeros(3)
    for i in range(3):
        for coalition in COALITIONS:
            if coalition & (1 << i):
                continue
            s = coalition.bit_count()
            weight = math.factorial(s) * math.factorial(2 - s) / math.factorial(3)
            answer[i] += weight * (values[coalition | (1 << i)] - values[coalition])
    # Independent expression: average marginal contribution over all player orders.
    orders = np.zeros(3)
    for order in itertools.permutations(range(3)):
        coalition = 0
        for i in order:
            expanded = coalition | (1 << i)
            orders[i] += (values[expanded] - values[coalition]) / 6
            coalition = expanded
    if np.max(np.abs(answer - orders)) > TOL or abs(answer.sum() - values[7]) > TOL:
        raise RuntimeError('Shapley efficiency/permutation check failed')
    return answer


def cooperative(matrix, policies):
    solutions = {}
    for coalition in COALITIONS:
        ix = subset_indices(policies, coalition)
        solutions[coalition] = solve_zero_sum(np.asarray(matrix)[ix])
    base = solutions[0]['value']
    values = {s: sol['value'] - base for s, sol in solutions.items()}
    for a in COALITIONS:
        for b in COALITIONS:
            if a & ~b == 0 and values[a] > values[b] + TOL:
                raise RuntimeError('Capability set monotonicity failed')
    phi = shapley(values)
    dividends = {}
    for coalition in sorted(COALITIONS, key=lambda s: s.bit_count()):
        dividends[coalition] = values[coalition] - sum(v for s, v in dividends.items() if s != coalition and s & ~coalition == 0)
    slacks = {s: float(sum(phi[i] for i in range(3) if s & (1 << i)) - values[s]) for s in COALITIONS}
    core = linprog(c=np.zeros(3), A_ub=[[-int(bool(s & (1 << i))) for i in range(3)] for s in range(1, 8)],
                   b_ub=[-values[s] for s in range(1, 8)], A_eq=[[1, 1, 1]], b_eq=[values[7]],
                   bounds=[(None, None)] * 3, method='highs')
    if core.status not in (0, 2):
        raise RuntimeError(f'Core solver error: {core.message}')
    superadditive = all(values[a | b] + TOL >= values[a] + values[b]
                        for a in COALITIONS for b in COALITIONS if a & b == 0)
    return {'baseline_value': base, 'coalition_value': values, 'absolute_value': {s: r['value'] for s, r in solutions.items()},
            'coalition_policies': {s: [policies[i] for i in subset_indices(policies, s)] for s in COALITIONS},
            'shapley': phi.tolist(), 'efficiency_error': float(abs(phi.sum() - values[7])),
            'interaction_dividends': dividends, 'superadditive': superadditive,
            'core_nonempty': bool(core.success), 'core_example': core.x.tolist() if core.success else None,
            'shapley_in_core': min(slacks.values()) >= -TOL, 'shapley_core_slacks': slacks,
            'max_coalition_exploitability': max(s['checks']['restricted_exploitability'] for s in solutions.values())}


def pure(index, n):
    weights = np.zeros(n)
    weights[index] = 1
    return weights


def baselines(matrix, policies, extra_costs, channel_fractions, phi):
    matrix = np.asarray(matrix)
    n = len(policies)
    extra_costs = np.asarray(extra_costs)
    worst = np.min(matrix, axis=1)
    baseline = policies.index('000')
    best = min(range(n), key=lambda i: (-round(float(worst[i]), 12), extra_costs[i], policies[i]))
    current = baseline
    while True:
        candidates = []
        for i, p in enumerate(policies):
            if (support_mask(p).bit_count() == support_mask(policies[current]).bit_count() + 1 and
                support_mask(policies[current]) & ~support_mask(p) == 0):
                gain = worst[i] - worst[current]
                if gain > TOL:
                    candidates.append((gain / (extra_costs[i] - extra_costs[current]), i))
        if not candidates:
            break
        _, current = min(candidates, key=lambda x: (-round(float(x[0]), 12), extra_costs[x[1]], policies[x[1]]))
    spending = np.array([[int(p[i]) * channel_fractions[i] for p in policies] for i in range(3)])
    eq = checked_lp(c=np.r_[np.zeros(n), -1.], A_eq=np.vstack([np.r_[np.ones(n), 0], np.c_[spending, -np.ones(3)]]),
                    b_eq=[1, 0, 0, 0], bounds=[(0, None)] * (n + 1))
    coverage = np.array([[int(p[i]) for p in policies] for i in range(3)])
    balanced = checked_lp(c=np.r_[np.zeros(n), -1.], A_eq=np.vstack([np.r_[np.ones(n), 0], np.c_[coverage, -np.ones(3)]]),
                          b_eq=[1, 0, 0, 0], bounds=[(0, None)] * (n + 1))
    scores = [sum(phi[i] for i, bit in enumerate(p) if bit == '1') for p in policies]
    shapley_pick = min(range(n), key=lambda i: (-round(float(scores[i]), 12), extra_costs[i], policies[i]))
    return {'no_extra': pure(baseline, n), 'best_fixed_maximin': pure(best, n),
            'uniform_feasible': np.ones(n) / n, 'equal_expected_channel_bytes': eq.x[:-1],
            'balanced_equal_repetition_probability': balanced.x[:-1],
            'greedy_marginal_per_byte': pure(current, n), 'shapley_knapsack': pure(shapley_pick, n)}


def evaluate(weights, matrix, costs):
    weights, matrix = np.asarray(weights), np.asarray(matrix)
    if weights.min() < -TOL or abs(weights.sum() - 1) > TOL:
        raise ValueError('Invalid mixture')
    payoffs = weights @ matrix
    return {'weights': weights.tolist(), 'per_attack': payoffs.tolist(), 'worst_case': float(payoffs.min()),
            'expected_extra_fraction': float(weights @ np.asarray(costs))}
