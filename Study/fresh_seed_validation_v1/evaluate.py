"""Evaluate immutable strategies; no optimisation or holdout-informed selection."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strategy_statistics(seed_matrices, weights, indices):
    tensor = np.asarray(seed_matrices, dtype=float)
    weights = np.asarray(weights, dtype=float)
    assert tensor.ndim == 3 and weights.shape[1] == tensor.shape[1]
    per_seed = np.einsum('sij,ki->skj', tensor, weights)
    means = per_seed.mean(axis=0)
    bootstrap = per_seed[indices].mean(axis=1)
    return means, means.min(axis=1), bootstrap, bootstrap.min(axis=2), per_seed


def simple_tests():
    tensor = np.array([[[1, 0], [0, 1]], [[0, 1], [1, 0]]], float)
    indices = np.array([[0, 0], [0, 1], [1, 1]])
    means, worst, boot, bworst, seeds = strategy_statistics(tensor, [[1, 0], [.5, .5]], indices)
    np.testing.assert_allclose(worst, [.5, .5])
    assert seeds[:, 0].min(axis=1).mean() == 0  # Intentionally different statistic.
    np.testing.assert_allclose(bworst, [[0, .5], [.5, .5], [0, .5]])
    assert np.allclose(boot[1], means)
    np.testing.assert_allclose(bworst[:, 1] - bworst[:, 0], [.5, 0, .5])


def main():
    started = time.perf_counter()
    simple_tests()
    freeze = json.loads((HERE / 'frozen_strategies.json').read_text())
    meta = json.loads((HERE / 'metadata.json').read_text())
    assert sha(HERE / 'frozen_strategies.json') == meta['freeze_hash']
    assert sha(HERE / 'session_results.json.gz') == meta['raw_results_hash']
    assert sha(HERE / 'PLAN.md') == freeze['plan_hash']
    with gzip.open(HERE / 'session_results.json.gz', 'rt') as stream:
        sessions = json.load(stream)
    rows = {}
    for r in sessions:
        key = tuple(r[k] for k in ('payload_bpp', 'environment', 'beta', 'attack', 'seed', 'policy'))
        assert key not in rows
        rows[key] = r
    rng = np.random.default_rng(freeze['bootstrap_seed'])
    indices = rng.integers(0, len(freeze['seed_list']), size=(freeze['bootstrap_resamples'], len(freeze['seed_list'])))
    results = []
    for fitted in freeze['games']:
        p, env, beta, cap = (fitted[k] for k in ('payload_bpp', 'environment', 'beta', 'extra_byte_cap'))
        policies, attacks = fitted['policies'], fitted['attacks']
        field = 'completion_rate' if fitted['endpoint'] == 'transport_completion' else 'recorded_extraction_weighted_rate'
        tensor = np.array([[[rows[(p, env, beta, a, s, pol)][field] for a in attacks] for pol in policies] for s in freeze['seed_list']])
        # Costs do not depend on which suppression rule is applied, but can change
        # with source availability. Validate every supported pure policy per seed.
        cost_tensor = np.array([[rows[(p, env, beta, attacks[0], s, pol)]['extra_fraction'] for pol in policies] for s in freeze['seed_list']])
        names = list(fitted['strategies'])
        weights = np.array([fitted['strategies'][n]['weights'] for n in names])
        assert np.all(weights >= -1e-8) and np.allclose(weights.sum(axis=1), 1)
        for w in weights:
            assert np.all(cost_tensor[:, w > 1e-8] <= cap + 1e-8)
        mean, worst, boot, boot_worst, per_seed = strategy_statistics(tensor, weights, indices)
        minimax = names.index('restricted_minimax')
        strategy_results = {}
        for k, name in enumerate(names):
            delta = worst[minimax] - worst[k]
            boot_delta = boot_worst[:, minimax] - boot_worst[:, k]
            attack_deltas = mean[minimax] - mean[k]
            boot_attack_deltas = boot[:, minimax] - boot[:, k]
            cost = cost_tensor @ weights[k]
            strategy_results[name] = {'worst_of_attack_means': float(worst[k]),
                'per_attack_means': mean[k].tolist(),
                'worst_attack_set': [a for j, a in enumerate(attacks) if abs(mean[k, j] - worst[k]) < 1e-12],
                'descriptive_bootstrap_interval': np.quantile(boot_worst[:, k], [.025, .975]).tolist(),
                'fitted_worst_case': fitted['strategies'][name]['fitted_worst_case'],
                'difference_from_fit': float(worst[k] - fitted['strategies'][name]['fitted_worst_case']),
                'expected_extra_fraction_mean': float(cost.mean()), 'expected_extra_fraction_range': [float(cost.min()), float(cost.max())],
                'minimax_minus_this': float(delta),
                'minimax_minus_this_descriptive_interval': np.quantile(boot_delta, [.025, .975]).tolist(),
                'minimax_minus_this_per_attack': attack_deltas.tolist(),
                'minimax_minus_this_per_attack_intervals': np.quantile(boot_attack_deltas, [.025, .975], axis=0).T.tolist(),
                'per_seed_per_attack_expected_performance': per_seed[:, k].tolist()}
        coalition = {}
        for s, c in fitted['coalitions'].items():
            w = np.zeros(len(policies))
            for pol, value in zip(c['policies'], c['weights']):
                w[policies.index(pol)] = value
            assert np.all(cost_tensor[:, w > 1e-8] <= cap + 1e-8)
            performances = np.einsum('sij,i->sj', tensor, w)
            means = performances.mean(axis=0)
            value = float(means.min())
            coalition[s] = {'frozen_policy_worst_case': value, 'fitted_value': c['fitted_value'],
                            'difference_from_fit': value - c['fitted_value'], 'per_attack_means': means.tolist()}
        for s, c in coalition.items():
            c['baseline_centred_frozen_policy_value'] = c['frozen_policy_worst_case'] - coalition['0']['frozen_policy_worst_case']
        violations = []
        for a in range(8):
            for b in range(8):
                if a & ~b == 0 and coalition[str(a)]['frozen_policy_worst_case'] > coalition[str(b)]['frozen_policy_worst_case'] + 1e-8:
                    violations.append([a, b])
        assert abs(coalition['7']['frozen_policy_worst_case'] - worst[minimax]) < 1e-8
        results.append({k: fitted[k] for k in ('endpoint', 'payload_bpp', 'environment', 'beta', 'extra_byte_cap', 'policies', 'attacks')} |
                       {'strategies': strategy_results, 'frozen_coalition_evaluation': coalition,
                        'frozen_coalition_monotonicity_violations': violations,
                        'fitted_shapley_unchanged': fitted['fitted_shapley']})
    assert len(results) == 216
    (HERE / 'evaluated_strategies.json').write_text(json.dumps(results, indent=2) + '\n')
    diagnostics = {'frozen_game_cells_evaluated': len(results), 'strategies_per_game': len(results[0]['strategies']),
        'seed_n': len(freeze['seed_list']), 'bootstrap_resamples': freeze['bootstrap_resamples'],
        'bootstrap_seed': freeze['bootstrap_seed'], 'all_actual_workload_hard_caps_checked': True,
        'statistics_unit_checks_passed': True, 'no_refitting': True,
        'frozen_coalition_nonmonotone_cells': sum(bool(r['frozen_coalition_monotonicity_violations']) for r in results),
        'evaluation_wall_seconds': time.perf_counter() - started, 'evaluator_hash': sha(__file__),
        'freeze_hash_unchanged': sha(HERE / 'frozen_strategies.json'), 'results_hash': sha(HERE / 'evaluated_strategies.json')}
    (HERE / 'evaluation_diagnostics.json').write_text(json.dumps(diagnostics, indent=2) + '\n')
    print(json.dumps(diagnostics, indent=2))
    for r in results:
        if r['endpoint'] == 'transport_completion' and r['payload_bpp'] == .2 and r['environment'] == 'E2' and r['beta'] == .05 and r['extra_byte_cap'] in (.7, .85):
            print(json.dumps({'cap': r['extra_byte_cap'], 'values': {n: {'value': s['worst_of_attack_means'], 'minimax_minus': s['minimax_minus_this'], 'interval': s['minimax_minus_this_descriptive_interval']} for n, s in r['strategies'].items()}}, indent=2))


if __name__ == '__main__':
    main()
