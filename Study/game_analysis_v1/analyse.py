"""Fit both game-theoretic components to existing development payoffs."""
import collections
import hashlib
import json
from pathlib import Path
import statistics
import time
import unittest
import numpy as np
import scipy
from games import POLICIES, solve_zero_sum, cooperative, baselines, evaluate, TOL
import test_games

HERE = Path(__file__).resolve().parent
PILOT = HERE.parent / 'transport_pilot_v1'
ATTACKS = ['random', 'C1', 'C2', 'C3', 'burst']
CAPS = [0, .2, .5, .7, .85, 1]
ENDPOINTS = {'transport_completion': 'completion_rate', 'recorded_extraction_weighted': 'recorded_extraction_weighted_rate'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    start = time.perf_counter()
    tests = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(test_games))
    if not tests.wasSuccessful():
        raise RuntimeError('Unit test failure')
    raw = json.loads((PILOT / 'session_results.json').read_text())
    meta = json.loads((PILOT / 'metadata.json').read_text())
    assert sha(PILOT / 'pilot.py') == meta['pilot_code_sha256']
    assert sha(PILOT / 'PLAN.md') == meta['plan_sha256']
    grouped = collections.defaultdict(list)
    for row in raw:
        grouped[(row['payload_bpp'], row['environment'], row['beta'], row['attack'], row['policy'])].append(row)
    sizes = np.array(meta['object_sizes_bytes']) + 133
    channel_fractions = sizes / sizes.sum()
    costs = {p: sum(int(p[i]) * channel_fractions[i] for i in range(3)) for p in POLICIES}
    # Current development samples have no missing files. Preserve hard-session feasibility
    # and fail if a workload change makes representative costs inconsistent.
    for row in raw:
        assert abs(row['extra_fraction'] - costs[row['policy']]) < 1e-12
    results = []
    seed_evaluations = []
    for endpoint, field in ENDPOINTS.items():
        for payload in (.1, .2, .4):
            for env in ('E0', 'E1', 'E2'):
                for beta in (.01, .05):
                    full = np.array([[statistics.mean(r[field] for r in grouped[(payload, env, beta, attack, p)]) for attack in ATTACKS] for p in POLICIES])
                    for cap in CAPS:
                        policies = [p for p in POLICIES if costs[p] <= cap + 1e-12]
                        ix = [POLICIES.index(p) for p in policies]
                        matrix = full[ix]
                        resource = [costs[p] for p in policies]
                        solution = solve_zero_sum(matrix)
                        coop = cooperative(matrix, policies)
                        assert abs(solution['value'] - coop['absolute_value'][7]) < TOL
                        options = baselines(matrix, policies, resource, channel_fractions, coop['shapley'])
                        options['restricted_minimax'] = np.asarray(solution['x'])
                        comparisons = {name: evaluate(weights, matrix, resource) for name, weights in options.items()}
                        for name, row in comparisons.items():
                            assert row['worst_case'] <= solution['value'] + TOL
                            assert row['expected_extra_fraction'] <= cap + TOL
                            row['gap_to_minimax'] = solution['value'] - row['worst_case']
                        identity = {'endpoint': endpoint, 'payload_bpp': payload, 'environment': env, 'beta': beta, 'extra_byte_cap': cap}
                        for seed in meta['seed_list']:
                            seed_matrix = np.array([[next(r[field] for r in grouped[(payload, env, beta, attack, p)] if r['seed'] == seed) for attack in ATTACKS] for p in policies])
                            for name, weights in options.items():
                                value = evaluate(weights, seed_matrix, resource)
                                seed_evaluations.append({**identity, 'seed': seed, 'strategy': name, 'per_attack': value['per_attack'],
                                                         'worst_of_this_seed': value['worst_case'], 'evaluation_scope': 'in-fit development seed, not held out'})
                        control = [statistics.mean(r[field] for r in grouped[(payload, env, 0, 'none', p)]) for p in policies]
                        results.append({**identity, 'policies': policies, 'attacks': ATTACKS, 'payoff_matrix': matrix.tolist(),
                                        'no_attack_control_per_policy': control, 'extra_costs': resource,
                                        'noncooperative': solution, 'comparators': comparisons, 'cooperative': coop})
    assert len(results) == 216
    diagnostics = {'game_cells': len(results), 'coalition_subgames': len(results) * 8, 'unit_tests_passed': tests.testsRun,
        'maximum_restricted_exploitability': max(r['noncooperative']['checks']['restricted_exploitability'] for r in results),
        'maximum_coalition_exploitability': max(r['cooperative']['max_coalition_exploitability'] for r in results),
        'maximum_shapley_efficiency_error': max(r['cooperative']['efficiency_error'] for r in results),
        'empty_core_cells': sum(not r['cooperative']['core_nonempty'] for r in results),
        'shapley_outside_core_cells': sum(not r['cooperative']['shapley_in_core'] for r in results),
        'non_superadditive_cells': sum(not r['cooperative']['superadditive'] for r in results),
        'wall_seconds': time.perf_counter() - start,
        'scipy': scipy.__version__, 'numpy': np.__version__,
        'source_hashes': {name: sha(PILOT / name) for name in ('session_results.json', 'metadata.json', 'sampled_records.json', 'payoff_summary.json')},
        'analysis_hashes': {name: sha(HERE / name) for name in ('PLAN.md', 'games.py', 'test_games.py', 'analyse.py')},
        'fresh_transport_seeds_run': False}
    for name, data in [('game_results.json', results), ('in_fit_seed_evaluations.json', seed_evaluations), ('diagnostics.json', diagnostics)]:
        (HERE / name).write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(diagnostics, indent=2))
    for r in results:
        if r['endpoint'] == 'transport_completion' and r['payload_bpp'] == .2 and r['environment'] == 'E2' and r['beta'] == .05 and r['extra_byte_cap'] in (.7, .85):
            print(json.dumps({'cap': r['extra_byte_cap'], 'policies': r['policies'], 'strategy': r['noncooperative']['x'],
                              'values': {name: v['worst_case'] for name, v in r['comparators'].items()},
                              'shapley': r['cooperative']['shapley']}, indent=2))


if __name__ == '__main__':
    main()
