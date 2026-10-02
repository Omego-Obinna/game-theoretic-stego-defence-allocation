"""Read-only arithmetic checks plus one deterministic transport reproduction."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'transport_pilot_v1'))
from pilot import run_trace


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    metadata = json.loads((HERE / 'metadata.json').read_text())
    diagnostics = json.loads((HERE / 'evaluation_diagnostics.json').read_text())
    freeze = json.loads((HERE / 'frozen_strategies.json').read_text())
    samples = json.loads((HERE / 'sampled_records.json').read_text())
    previous = json.loads((HERE.parent / 'transport_pilot_v1/sampled_records.json').read_text())
    old = {r['image_id'] for s in previous.values() for r in s['0.1']}
    assert sha(HERE / 'frozen_strategies.json') == metadata['freeze_hash'] == diagnostics['freeze_hash_unchanged']
    assert sha(HERE / 'run_holdout.py') == metadata['runner_hash']
    assert sha(HERE / 'evaluate.py') == diagnostics['evaluator_hash']
    assert sha(HERE / 'evaluated_strategies.json') == diagnostics['results_hash']
    assert sha(HERE / 'session_results.json.gz') == metadata['raw_results_hash']
    assert sha(HERE / 'sampled_records.json') == metadata['sample_hash']
    for s in samples.values():
        assert {r['image_id'] for r in s['0.1']}.isdisjoint(old)
        assert [r['image_id'] for r in s['0.1']] == [r['image_id'] for r in s['0.2']] == [r['image_id'] for r in s['0.4']]
    with gzip.open(HERE / 'session_results.json.gz', 'rt') as stream:
        sessions = json.load(stream)
    identities = set()
    for r in sessions:
        key = tuple(r[k] for k in ('seed', 'payload_bpp', 'environment', 'beta', 'attack', 'policy'))
        assert key not in identities
        identities.add(key)
        rows = samples[str(r['seed'])][str(r['payload_bpp'])]
        completed = r['completed_epochs']
        assert len(set(completed)) == r['complete'] == len(r['latencies_ms'])
        assert all(0 <= e < 200 and rows[e]['available'] for e in completed)
        assert r['recorded_extraction_weighted_complete'] == sum(rows[e]['recorded_success'] for e in completed)
        assert sum(r['attack_spent_per_block'].values()) == r['suppressed_objects'] <= r['attack_cap']
        assert r['wasted_suppressions'] <= min(r['suppressed_objects'], r['natural_loss_objects'])
        sizes = metadata['object_sizes']
        base = sum(sizes[c] + 133 for row in rows for c in range(3) if c != 2 or row['available'])
        actual = sum((sizes[c] + 133) * (1 + int(r['policy'][c])) for row in rows for c in range(3) if c != 2 or row['available'])
        assert (base, actual) == (r['baseline_bytes'], r['emitted_bytes'])
    saved = next(r for r in sessions if r['payload_bpp'] == .2 and r['environment'] == 'E2' and r['beta'] == .05 and r['attack'] == 'C3' and r['policy'] == '111' and r['missing_source_images'] > 0)
    rows = samples[str(saved['seed'])]['0.2']
    missing = tuple(e for e, row in enumerate(rows) if not row['available'])
    replica = run_trace((1, 1, 1), saved['seed'], 'E2', 'C3', .05, missing)
    for k, v in replica.items():
        if k == 'attack_spent_per_block':
            v = {str(i): n for i, n in v.items()}
        assert saved[k] == v
    result = {'session_records_reconciled': len(sessions), 'source_ids_development_disjoint': True,
              'same_ordered_ids_across_payloads': True, 'freeze_and_execution_hashes_checked': True,
              'recorded_failure_weights_checked': True, 'bytes_and_attack_counters_reconciled': True,
              'deterministic_reproduction_with_missing_source_image': {'passed': True, 'seed': saved['seed'], 'missing_epochs': missing}}
    (HERE / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
