"""Paired scenario sensitivity with immutable defender/coalition strategies."""
import gzip
import hashlib
import json
from pathlib import Path
import time
import unittest
from engine import run, LEGACY, OBSERVATION, ATTACKS
from transport import POLICIES, costs
import test_engine
import test_transport

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'fresh_seed_validation_v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    started = time.perf_counter()
    if (HERE / 'session_results.json.gz').exists():
        raise RuntimeError('Sensitivity outcomes already exist; do not overwrite')
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_engine, test_transport)])
    tests = unittest.TextTestRunner(verbosity=0).run(suite)
    assert tests.wasSuccessful()
    metadata = json.loads((PRIOR / 'metadata.json').read_text())
    freeze = json.loads((PRIOR / 'frozen_strategies.json').read_text())
    samples = json.loads((PRIOR / 'sampled_records.json').read_text())
    assert sha(PRIOR / 'frozen_strategies.json') == metadata['freeze_hash']
    assert sha(PRIOR / 'sampled_records.json') == metadata['sample_hash']
    assert sha(PRIOR / 'session_results.json.gz') == metadata['raw_results_hash']
    assert sha(HERE.parent / 'transport_pilot_v1/pilot.py') == freeze['pilot_code_hash']
    assert sha(HERE.parent / 'transport_validation_v1/transport.py') == freeze['transport_code_hash']
    with gzip.open(PRIOR / 'session_results.json.gz', 'rt') as stream:
        legacy_records = {tuple(r[k] for k in ('seed', 'payload_bpp', 'environment', 'beta', 'attack', 'policy')): r for r in json.load(stream)}
    execution = {'design_scope': 'paired sensitivity on reused validation scenarios, not fresh holdout',
        'plan_hash': sha(HERE / 'PLAN.md'), 'engine_hash': sha(HERE / 'engine.py'), 'tests_hash': sha(HERE / 'test_engine.py'),
        'runner_hash': sha(__file__), 'freeze_hash': sha(PRIOR / 'frozen_strategies.json'),
        'sample_hash': sha(PRIOR / 'sampled_records.json'), 'prior_raw_hash': metadata['raw_results_hash'],
        'seeds': freeze['seed_list'], 'tests_passed': tests.testsRun}
    (HERE / 'execution_manifest.json').write_text(json.dumps(execution, indent=2) + '\n')
    sizes = metadata['object_sizes']
    serialized = [s + 133 for s in sizes]
    records, cache = [], {}
    legacy_checked = 0
    for seed in freeze['seed_list']:
        for env in ('E1', 'E2'):
            for beta in (.01, .05):
                for attack in ATTACKS:
                    for pricing in ('objects', 'bytes'):
                        for policy in POLICIES:
                            for payload in (.1, .2, .4):
                                source = samples[str(seed)][str(payload)]
                                available = tuple(r['available'] for r in source)
                                key = (seed, env, beta, attack, pricing, policy, available)
                                if key not in cache:
                                    cache[key] = run(policy, seed, env, attack, beta, pricing, available, serialized)
                                trace = cache[key]
                                policy_name = ''.join(map(str, policy))
                                c = costs(sizes, policy)
                                missing_n = sum(not value for value in available)
                                base = 200*c['base_bytes'] - missing_n*c['per_channel_bytes'][2]
                                actual = 200*c['total_bytes'] - missing_n*c['per_channel_bytes'][2]*(1+policy[2])
                                complete = trace['completed_epochs']
                                weighted = sum(source[e]['recorded_success'] for e in complete)
                                row = {'seed': seed, 'payload_bpp': payload, 'environment': env, 'beta': beta,
                                    'attack': attack, 'pricing': pricing, 'policy': policy_name,
                                    'offered_epochs': 200, 'missing_source_images': missing_n,
                                    'complete': len(complete), 'completion_rate': len(complete)/200,
                                    'recorded_extraction_weighted_complete': weighted, 'recorded_extraction_weighted_rate': weighted/200,
                                    'baseline_bytes': base, 'emitted_bytes': actual, 'extra_fraction': (actual-base)/base,
                                    'provenance': 'new_sensitivity', **trace}
                                if pricing == 'objects' and attack in LEGACY:
                                    old = legacy_records[(seed, payload, env, beta, attack, policy_name)]
                                    for field in ('complete', 'completed_epochs', 'latencies_ms', 'emitted_objects', 'natural_loss_objects', 'suppressed_objects', 'wasted_suppressions',
                                                  'event_counts', 'attack_cap', 'completion_rate', 'recorded_extraction_weighted_rate', 'baseline_bytes', 'emitted_bytes'):
                                        assert row[field] == old[field], (key[:6], field)
                                    assert {str(k):v for k,v in trace['attack_spent_per_block'].items() if v} == old['attack_spent_per_block']
                                    row['provenance'] = 'legacy_object_result_exactly_reproduced'
                                    legacy_checked += 1
                                assert trace['final_reserved'] == 0
                                records.append(row)
        print(f'Sensitivity seed {seed} complete ({len(records)} records).', flush=True)
    assert len(records) == 34560 and legacy_checked == 9600
    assert sha(PRIOR / 'frozen_strategies.json') == execution['freeze_hash']
    assert sha(HERE / 'PLAN.md') == execution['plan_hash']
    with gzip.open(HERE / 'session_results.json.gz', 'wt', encoding='utf8') as stream:
        json.dump(records, stream, separators=(',', ':'))
    metadata_out = {**execution, 'records': len(records), 'offered_simulated_epochs': 200*len(records),
        'legacy_records_exactly_reproduced': legacy_checked, 'new_sensitivity_records': len(records)-legacy_checked,
        'unique_transport_replays_including_compatibility_checks': len(cache), 'object_sizes': sizes,
        'pricing_regimes': ['objects', 'bytes'], 'attack_catalogue': list(ATTACKS),
        'wall_seconds': time.perf_counter()-started, 'raw_hash': sha(HERE/'session_results.json.gz'), 'defences_refitted': False}
    (HERE / 'metadata.json').write_text(json.dumps(metadata_out, indent=2) + '\n')
    print(json.dumps(metadata_out, indent=2), flush=True)


if __name__ == '__main__':
    main()
