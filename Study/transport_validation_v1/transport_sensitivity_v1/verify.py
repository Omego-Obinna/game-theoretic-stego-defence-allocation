"""Independent saved-outcome arithmetic and accounting; no simulation or fitting."""
from fractions import Fraction
import gzip
import hashlib
import json
from math import fsum
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'fresh_seed_validation_v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    meta = json.loads((HERE / 'metadata.json').read_text())
    diagnostics = json.loads((HERE / 'evaluation_diagnostics.json').read_text())
    frozen = json.loads((PRIOR / 'frozen_strategies.json').read_text())
    samples = json.loads((PRIOR / 'sampled_records.json').read_text())
    results = json.loads((HERE / 'evaluated_strategies.json').read_text())
    for path, expected in (
        (PRIOR / 'frozen_strategies.json', meta['freeze_hash']),
        (PRIOR / 'sampled_records.json', meta['sample_hash']),
        (PRIOR / 'session_results.json.gz', meta['prior_raw_hash']),
        (HERE / 'session_results.json.gz', meta['raw_hash']),
        (HERE / 'PLAN.md', meta['plan_hash']),
        (HERE / 'engine.py', meta['engine_hash']),
        (HERE / 'test_engine.py', meta['tests_hash']),
        (HERE / 'run_sensitivity.py', meta['runner_hash']),
        (HERE / 'evaluate.py', diagnostics['evaluator_hash']),
        (HERE / 'evaluated_strategies.json', diagnostics['results_hash']),
        (HERE.parent / 'transport_pilot_v1/pilot.py', frozen['pilot_code_hash']),
        (HERE.parent / 'transport_validation_v1/transport.py', frozen['transport_code_hash']),
    ):
        assert sha(path) == expected, str(path)
    with gzip.open(HERE / 'session_results.json.gz', 'rt') as stream:
        raw = json.load(stream)
    with gzip.open(PRIOR / 'session_results.json.gz', 'rt') as stream:
        prior = json.load(stream)
    source_key = lambda r: tuple(r[k] for k in ('seed', 'payload_bpp', 'environment', 'beta', 'attack', 'policy'))
    previous = {source_key(r): r for r in prior}
    lookup = {(r['pricing'], *source_key(r)): r for r in raw}
    assert len(lookup) == len(raw) == 34560
    sizes = [s + 133 for s in meta['object_sizes']]
    legacy_count = 0
    inferred = 0
    targets = set()
    for r in raw:
        source = samples[str(r['seed'])][str(r['payload_bpp'])]
        assert len(source) == r['offered_epochs'] == 200
        policy = [int(bit) for bit in r['policy']]
        available = [s['available'] for s in source]
        missing = available.count(False)
        base_by_epoch = [sum(sizes[:2]) + sizes[2] * a for a in available]
        base = sum(base_by_epoch)
        emitted_bytes = sum(size * (1 + bit) * (200 if ch < 2 else 200 - missing)
                            for ch, (size, bit) in enumerate(zip(sizes, policy)))
        assert r['missing_source_images'] == missing
        assert r['baseline_bytes'] == base and r['emitted_bytes'] == emitted_bytes
        assert abs(r['extra_fraction'] - (emitted_bytes - base) / base) < 1e-12
        assert r['emitted_objects'] == 200 * sum(1 + b for b in policy) - missing * (1 + policy[2])
        completed = r['completed_epochs']
        assert len(completed) == len(set(completed)) == r['complete']
        assert all(0 <= e < 200 and available[e] for e in completed)
        assert len(r['latencies_ms']) == r['complete']
        assert all(0 <= latency <= 500 for latency in r['latencies_ms'])
        weighted = sum(source[e]['recorded_success'] for e in completed)
        assert r['recorded_extraction_weighted_complete'] == weighted
        assert r['completion_rate'] == len(completed) / 200
        assert r['recorded_extraction_weighted_rate'] == weighted / 200
        beta = Fraction(str(r['beta']))
        units = [3] * 200 if r['pricing'] == 'objects' else base_by_epoch
        assert r['attack_cap'] == int(beta * sum(units))
        assert r['attack_cap_per_block'] == {str(b): int(beta * sum(units[b*100:(b+1)*100])) for b in range(2)}
        assert r['attack_spent'] == sum(r['attack_spent_per_block'].values())
        assert 0 <= r['attack_spent'] <= r['attack_cap'] and r['final_reserved'] == 0
        assert all(0 <= amount <= r['attack_cap_per_block'][b] for b, amount in r['attack_spent_per_block'].items())
        assert r['attack_spent'] == r['suppressed_objects' if r['pricing'] == 'objects' else 'suppressed_serialized_bytes']
        assert 0 <= r['wasted_suppressions'] <= min(r['suppressed_objects'], r['natural_loss_objects'])
        if r['attack'].startswith('observe_'):
            assert r['inferred_repetitions'] == {str(ch+1): bit for ch, bit in enumerate(policy)}
            assert r['learning_time_ms'] == 200
            if r['attack'] == 'observe_best':
                target = min(range(3), key=lambda ch: ((1+policy[ch]) * (1 if r['pricing'] == 'objects' else sizes[ch]), ch)) + 1
                if r['pricing'] == 'bytes':
                    targets.add(target)
            else:
                target = int(r['attack'][-1])
            assert r['observed_target'] == target
            assert r['suppressed_serialized_bytes'] == sizes[target-1] * r['suppressed_objects']
            assert r['suppressed_objects'] % (1+policy[target-1]) == 0
            inferred += 1
        if r['pricing'] == 'objects' and r['attack'] in meta['attack_catalogue'][:5]:
            old = previous[source_key(r)]
            for key in ('complete', 'completed_epochs', 'latencies_ms', 'emitted_objects', 'natural_loss_objects',
                        'suppressed_objects', 'wasted_suppressions', 'event_counts', 'attack_cap', 'completion_rate',
                        'recorded_extraction_weighted_rate', 'baseline_bytes', 'emitted_bytes'):
                assert r[key] == old[key], key
            assert {k:v for k,v in r['attack_spent_per_block'].items() if v} == old['attack_spent_per_block']
            legacy_count += 1
    assert legacy_count == 9600 and inferred == 15360 and targets <= {1, 2}

    game_key = lambda r: tuple(r[k] for k in ('endpoint', 'payload_bpp', 'environment', 'beta', 'extra_byte_cap'))
    games = {game_key(g): g for g in frozen['games']}
    max_error = 0.0
    n_strategies = 0
    nonmonotone, grand_reversals = [], []

    def compare(actual, expected):
        nonlocal max_error
        error = abs(actual - expected)
        max_error = max(max_error, error)
        assert error < 1e-12, (actual, expected)

    for r in results:
        game = games[game_key(r)]
        field = 'completion_rate' if r['endpoint'] == 'transport_completion' else 'recorded_extraction_weighted_rate'
        seeds, attacks, policies = frozen['seed_list'], r['attacks'], r['policies']
        def outcome(seed, attack, pol):
            return lookup[(r['pricing'], seed, r['payload_bpp'], r['environment'], r['beta'], attack, pol)]
        def weighted(w, pols):
            per_seed = [[fsum(weight * outcome(seed, attack, pol)[field] for pol, weight in zip(pols, w))
                         for attack in attacks] for seed in seeds]
            means = [fsum(row[j] for row in per_seed) / len(seeds) for j in range(len(attacks))]
            return per_seed, means
        assert r['fitted_shapley_unchanged'] == game['fitted_shapley']
        for name, s in r['strategies'].items():
            weights = game['strategies'][name]['weights']
            assert s['frozen_weights'] == weights
            compare(fsum(weights), 1)
            for seed in seeds:
                for pol, w in zip(policies, weights):
                    if w > 1e-8:
                        assert outcome(seed, attacks[0], pol)['extra_fraction'] <= r['extra_byte_cap'] + 1e-8
            per_seed, means = weighted(weights, policies)
            for actual, expected in zip(s['per_attack_means'], means):
                compare(actual, expected)
            for saved, calculated in zip(s['per_seed_per_attack_expected_performance'], per_seed):
                for actual, expected in zip(saved, calculated):
                    compare(actual, expected)
            for key, expected in (
                ('legacy_catalogue_worst', min(means[:5])), ('matched_fixed_reservation_worst', min(means[5:8])),
                ('adaptive_only', means[8]), ('augmented_catalogue_worst', min(means)),
                ('legacy_to_augmented_drop', min(means[:5]) - min(means)),
                ('matched_fixed_minus_adaptive', min(means[5:8]) - means[8]),
                ('minimax_minus_this_augmented', r['strategies']['restricted_minimax']['augmented_catalogue_worst'] - min(means)),
            ):
                compare(s[key], expected)
            compare(s['expected_extra_fraction'], fsum(
                w * outcome(seed, attacks[0], pol)['extra_fraction'] for seed in seeds for pol, w in zip(policies, weights)) / len(seeds))
            assert s['augmented_worst_attacks'] == [a for a, value in zip(attacks, means) if abs(value-min(means)) < 1e-12]
            n_strategies += 1
        worths = {}
        for coalition, c in game['coalitions'].items():
            _, means = weighted(c['weights'], c['policies'])
            worths[int(coalition)] = min(means)
            saved = r['frozen_coalition_values'][coalition]
            compare(saved['legacy_value'], min(means[:5]))
            compare(saved['adaptive_only'], means[8])
            compare(saved['augmented_value'], min(means))
        for coalition, worth in worths.items():
            compare(r['frozen_coalition_values'][str(coalition)]['baseline_centred_augmented_value'], worth-worths[0])
        bad = [(small, large) for small in worths for large in worths
               if small != large and small & large == small and worths[small] > worths[large] + 1e-12]
        identity = dict(zip(('endpoint','payload_bpp','environment','beta','extra_byte_cap'), game_key(r))) | {'pricing': r['pricing']}
        if bad:
            nonmonotone.append(identity | {'reversals': bad})
        if any(worths[s] > worths[7] + 1e-12 for s in range(7)):
            grand_reversals.append(identity)
    assert n_strategies == 2304 and len(results) == 288
    report = {'passed': True, 'raw_records_verified': len(raw), 'legacy_records_exactly_reproduced': legacy_count,
              'observation_records_verified': inferred, 'byte_adaptive_targets': sorted(targets),
              'strategy_point_evaluations_recomputed': n_strategies, 'coalition_evaluations_recomputed': 8*len(results),
              'max_absolute_point_error': max_error, 'all_hashes_unchanged': True,
              'all_workload_costs_and_budget_caps_recomputed': True,
              'frozen_coalition_nonmonotone_configurations': len(nonmonotone),
              'frozen_grand_below_a_subcoalition_configurations': len(grand_reversals),
              'nonmonotone_details': nonmonotone, 'grand_reversal_details': grand_reversals,
              'scope': 'Saved-outcome verification; no refitting and no fresh simulation. Bootstrap intervals not certified by this verifier.',
              'verification_code_hash': sha(__file__)}
    (HERE / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if not k.endswith('_details')}, indent=2))


if __name__ == '__main__':
    main()
