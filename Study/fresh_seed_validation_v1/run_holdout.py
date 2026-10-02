"""Fresh seeds with immutable fitted policies; no game fitting or image processing."""
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(OUT / 'transport_pilot_v1'))
from pilot import run_trace, CONDITIONS, POLICIES, costs
import test_transport


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    started = time.perf_counter()
    if (HERE / 'session_results.json.gz').exists():
        raise RuntimeError('Holdout already executed; do not overwrite or retune')
    frozen = json.loads((HERE / 'frozen_strategies.json').read_text())
    for path, name in [(HERE / 'PLAN.md', 'plan_hash'), (OUT / 'game_analysis_v1/game_results.json', 'source_game_hash'),
                       (OUT / 'transport_pilot_v1/pilot.py', 'pilot_code_hash'), (OUT / 'transport_validation_v1/transport.py', 'transport_code_hash')]:
        assert sha(path) == frozen[name]
    freeze_hash = sha(HERE / 'frozen_strategies.json')
    tests = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(test_transport))
    assert tests.wasSuccessful()
    previous = json.loads((OUT / 'transport_pilot_v1/sampled_records.json').read_text())
    old_ids = {r['image_id'] for samples in previous.values() for r in samples['0.1']}
    assert len(old_ids) == 962
    evidence = json.loads((OUT / 'Existing_Evidence_Manifest_v1.json').read_text())
    log = next(s for s in evidence['sources'] if s['id'] == 'E01')
    assert sha(log['path']) == log['sha256']
    records = {p: {} for p in (.1, .2, .4)}
    gamma = set()
    with Path(log['path']).open(newline='') as stream:
        reader = csv.reader(stream)
        header = next(reader)
        for fields in reader:
            if len(fields) != 153:
                continue
            row = dict(zip(header, fields))
            p = float(row['payload_bpp'])
            if p not in records or row['run_id'] != evidence['embedding_run_id']:
                continue
            path = Path(row['stego_path'])
            available = path.is_file()
            if available:
                assert path.stat().st_size == 262159
            gamma.add((row['gamma1_path'], row['gamma2_path'], row['gamma1_sha256'], row['gamma2_sha256']))
            image_id = int(row['image_id'])
            assert image_id not in records[p]
            records[p][image_id] = {'image_id': image_id, 'available': available,
                'recorded_success': int(row['success_extract']), 'payload_bits': int(row['payload_length_L'])}
    assert all(len(v) == 10000 for v in records.values()) and len(gamma) == 1
    g1, g2, h1, h2 = next(iter(gamma))
    assert sha(g1) == h1 and sha(g2) == h2
    sizes = (Path(g1).stat().st_size, Path(g2).stat().st_size, 262159)
    pool = sorted(set(records[.1]) - old_ids)
    assert len(pool) == 9038
    assert not set(frozen['seed_list']).intersection(range(190900, 190906))
    samples = {str(seed): {str(p): [records[p][i] for i in random.Random(seed).sample(pool, 200)] for p in records} for seed in frozen['seed_list']}
    for sample in samples.values():
        assert {r['image_id'] for r in sample['0.1']}.isdisjoint(old_ids)
        assert len({r['image_id'] for r in sample['0.1']}) == 200
    (HERE / 'sampled_records.json').write_text(json.dumps(samples, indent=2) + '\n')
    execution = {'freeze_hash': freeze_hash, 'runner_hash': sha(__file__), 'source_log_hash': log['sha256'],
                 'sample_hash': sha(HERE / 'sampled_records.json'), 'plan_hash': frozen['plan_hash'],
                 'seed_list': frozen['seed_list'], 'development_ids_excluded': len(old_ids),
                 'validation_pool_size': len(pool), 'prior_transport_tests_passed': tests.testsRun}
    (HERE / 'execution_manifest.json').write_text(json.dumps(execution, indent=2) + '\n')
    print('Freeze, source hashes, disjoint cover samples and 35 transport tests verified.', flush=True)
    sessions, cache = [], {}
    for seed in frozen['seed_list']:
        for env in ('E0', 'E1', 'E2'):
            for attack, beta in CONDITIONS:
                for policy in POLICIES:
                    for p in records:
                        rows = samples[str(seed)][str(p)]
                        missing = tuple(e for e, r in enumerate(rows) if not r['available'])
                        key = (seed, env, attack, beta, policy, missing)
                        if key not in cache:
                            cache[key] = run_trace(policy, seed, env, attack, beta, missing)
                        trace = cache[key]
                        c = costs(sizes, policy)
                        baseline = 200 * c['base_bytes'] - len(missing) * c['per_channel_bytes'][2]
                        emitted = 200 * c['total_bytes'] - len(missing) * c['per_channel_bytes'][2] * (1 + policy[2])
                        complete = trace['completed_epochs']
                        weighted = sum(rows[e]['recorded_success'] for e in complete)
                        assert 0 <= weighted <= len(complete) <= 200 - len(missing)
                        if env == 'E0' and attack == 'none':
                            assert len(complete) == 200 - len(missing)
                        assert trace['emitted_objects'] == 200 * (3 + sum(policy)) - len(missing) * (1 + policy[2])
                        sessions.append({'seed': seed, 'environment': env, 'attack': attack, 'beta': beta,
                            'policy': ''.join(map(str, policy)), 'payload_bpp': p, 'offered_epochs': 200,
                            'missing_source_images': len(missing), 'complete': len(complete),
                            'completion_rate': len(complete) / 200, 'recorded_extraction_weighted_complete': weighted,
                            'recorded_extraction_weighted_rate': weighted / 200,
                            'recorded_extraction_weighted_bit_fraction': sum(rows[e]['payload_bits'] * rows[e]['recorded_success'] for e in complete) / sum(r['payload_bits'] for r in rows),
                            'baseline_bytes': baseline, 'emitted_bytes': emitted,
                            'extra_fraction': (emitted - baseline) / baseline, **trace})
        print(f'Fresh seed {seed} complete ({len(sessions)} session records).', flush=True)
    assert len(sessions) == 15840
    assert sha(HERE / 'frozen_strategies.json') == freeze_hash
    with gzip.open(HERE / 'session_results.json.gz', 'wt', encoding='utf8') as stream:
        json.dump(sessions, stream, separators=(',', ':'))
    metadata = {**execution, 'object_sizes': sizes, 'sessions': len(sessions), 'offered_simulated_epochs': len(sessions) * 200,
        'distinct_transport_replays': len(cache), 'wall_seconds': time.perf_counter() - started,
        'source_overlap_with_development': 0,
        'unique_validation_cover_ids': len({r['image_id'] for s in samples.values() for r in s['0.1']}),
        'sampled_missing_occurrences': {str(p): sum(not r['available'] for s in samples.values() for r in s[str(p)]) for p in records},
        'sampled_extraction_failure_occurrences': {str(p): sum(not r['recorded_success'] for s in samples.values() for r in s[str(p)]) for p in records},
        'raw_results_hash': sha(HERE / 'session_results.json.gz'), 'no_refitting': True}
    (HERE / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == '__main__':
    main()
