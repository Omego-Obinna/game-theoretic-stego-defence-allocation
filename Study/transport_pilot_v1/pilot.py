"""Bounded development pilot; no image generation, decoding or ML imports."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(OUT / 'transport_validation_v1'))
from transport import Config, POLICIES, Receiver, SuppressionBudget, emit, costs, feasible
import test_transport

KEY = b'validation-only-not-a-deployment-key'
SESSION = b'pilot-reference1'
REPRESENTATIVE = (b'full-gamma1-representative', b'full-gamma2-representative', b'image-representative')
SEEDS = list(range(190901, 190906))
CONDITIONS = [('none', 0)] + [(a, b) for b in (0.01, 0.05) for a in ('random', 'C1', 'C2', 'C3', 'burst')]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def draw(*parts):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, parts)).encode()).digest()[:8], 'big') / 2**64


def run_trace(policy, seed, environment, attack, beta, missing=(), n=200, objects=REPRESENTATIVE):
    config = Config(n)
    frames = [t for t in emit(KEY, SESSION, [objects] * n, policy, config)
              if not (t.epoch in missing and t.channel == 3)]
    ledger = SuppressionBudget(n, beta)
    outages = set()
    if environment == 'E2':
        end = -1
        for boundary in range(n + 1):
            if boundary >= end and draw(seed, environment, 'outage', boundary) < 0.005:
                end = boundary + 3
                outages.update(range(boundary, end))
    receiver, events = Receiver(KEY, SESSION, config), []
    natural = attacked = wasted = 0
    for t in frames:
        block = t.epoch // 100
        start = block * 100 + int(draw(seed, 'attack-burst-start', block) * 100)
        selected = (attack.startswith('C') and t.channel == int(attack[1])) or (
            attack == 'random' and draw(seed, 'attack-random', t.epoch, t.channel, t.copy) < 0.25) or (
            attack == 'burst' and t.epoch >= start)
        suppressed = ledger.decide(t) if selected else False
        # Draw/evaluate natural loss only after the causal suppression decision.
        independent_loss = environment != 'E0' and draw(seed, environment, 'loss', t.epoch, t.channel, t.copy) < 0.01
        lost = independent_loss or t.send_ms // 100 in outages
        natural += int(lost)
        attacked += int(suppressed)
        wasted += int(lost and suppressed)
        jitter = {'E0': 0, 'E1': 50, 'E2': 100}[environment]
        delay = 20 + int(draw(seed, environment, 'base-delay', t.epoch, t.channel, t.copy) * 51)
        if jitter:
            delay += int(draw(seed, environment, 'jitter', t.epoch, t.channel, t.copy) * (jitter + 1))
        if not lost and not suppressed:
            events.append((t.send_ms + delay, t))
    for now, t in sorted(events, key=lambda x: (x[0], x[1].epoch, x[1].channel, x[1].copy)):
        receiver.receive(now, t.wire)
    result = receiver.finalize()
    completed = [e for e, row in result.items() if row['outcome'] == 'complete']
    assert len(result) == n and not set(completed).intersection(missing)
    assert ledger.spent <= ledger.cap
    assert all(spent <= int(ledger.beta * 3 * min(100, n - block * 100)) for block, spent in ledger.blocks.items())
    return {'completed_epochs': completed, 'latencies_ms': [result[e]['latency_ms'] for e in completed],
            'emitted_objects': len(frames), 'natural_loss_objects': natural,
            'suppressed_objects': attacked, 'wasted_suppressions': wasted,
            'attack_cap': ledger.cap, 'attack_spent_per_block': ledger.blocks,
            'event_counts': receiver.counts}


def equivalence_check():
    saved = json.loads((OUT / 'transport_validation_v1/validation_results.json').read_text())
    fixture = saved['fixtures'][0]
    objects = tuple(Path(f['path']).read_bytes() for f in fixture['files'])
    assert all(hashlib.sha256(obj).hexdigest() == f['sha256'] for obj, f in zip(objects, fixture['files']))
    checks = 0
    for policy in POLICIES:
        for env, attack, beta, missing in [('E0', 'none', 0, ()), ('E1', 'C3', 0.05, ()), ('E2', 'random', 0.05, ()), ('E2', 'burst', 0.05, (2,))]:
            # 10 epochs permits a nonzero 5% suppression budget and bounded file traffic.
            small = run_trace(policy, 190900, env, attack, beta, missing, n=10)
            full = run_trace(policy, 190900, env, attack, beta, missing, n=10, objects=objects)
            assert small == full, (policy, env, attack)
            checks += 1
    # Determinism and missing-image handling beyond a naturally lost interval.
    assert run_trace((1, 1, 1), 190901, 'E2', 'burst', .05) == run_trace((1, 1, 1), 190901, 'E2', 'burst', .05)
    missing = run_trace((1, 1, 1), 190901, 'E0', 'none', 0, (2,), n=10)
    assert missing['completed_epochs'] == [i for i in range(10) if i != 2]
    assert missing['emitted_objects'] == 58
    return checks


def main():
    started = time.perf_counter()
    plan_hash = digest(HERE / 'PLAN.md')
    frozen = json.loads((OUT / 'Existing_Evidence_Manifest_v1.json').read_text())
    log = next(s for s in frozen['sources'] if s['id'] == 'E01')
    assert digest(log['path']) == log['sha256']
    tests = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(test_transport))
    assert tests.wasSuccessful()
    equivalence_n = equivalence_check()
    print(f'Gates passed: {tests.testsRun} prior tests, {equivalence_n} full-byte equivalence cases.', flush=True)
    records = {p: {} for p in (0.1, 0.2, 0.4)}
    size_counts, gamma_pairs = collections.Counter(), set()
    with Path(log['path']).open(newline='') as handle:
        reader = csv.reader(handle)
        header = next(reader)
        for fields in reader:
            if len(fields) != 153:
                continue
            row = dict(zip(header, fields))
            p = float(row['payload_bpp'])
            if row['run_id'] != frozen['embedding_run_id'] or p not in records:
                continue
            path = Path(row['stego_path'])
            exists = path.is_file()
            size = path.stat().st_size if exists else None
            if exists:
                size_counts[size] += 1
            gamma_pairs.add((row['gamma1_path'], row['gamma2_path'], row['gamma1_sha256'], row['gamma2_sha256']))
            image_id = int(row['image_id'])
            assert image_id not in records[p]
            records[p][image_id] = {'image_id': image_id, 'available': exists, 'image_bytes': size,
                                     'recorded_success': int(row['success_extract']), 'payload_bits': int(row['payload_length_L'])}
    assert all(len(v) == 10000 for v in records.values()) and len(gamma_pairs) == 1
    assert dict(size_counts) == {262159: 29991}
    g1, g2, h1, h2 = next(iter(gamma_pairs))
    assert digest(g1) == h1 and digest(g2) == h2
    sizes = (Path(g1).stat().st_size, Path(g2).stat().st_size, 262159)
    source_summary = {str(p): {'attempts': len(rows), 'missing_images': sum(not r['available'] for r in rows.values()),
                             'extraction_failures_including_missing': sum(not r['recorded_success'] for r in rows.values())} for p, rows in records.items()}
    assert [source_summary[str(p)]['missing_images'] for p in records] == [1, 4, 4]
    samples, sessions, cache = {}, [], {}
    for seed in SEEDS:
        ids = random.Random(seed).sample(sorted(records[0.1]), 200)
        samples[str(seed)] = {str(p): [records[p][i] for i in ids] for p in records}
        for env in ('E0', 'E1', 'E2'):
            for attack, beta in CONDITIONS:
                for policy in POLICIES:
                    for p in records:
                        rows = samples[str(seed)][str(p)]
                        missing = tuple(e for e, row in enumerate(rows) if not row['available'])
                        cache_key = (seed, env, attack, beta, policy, missing)
                        if cache_key not in cache:
                            cache[cache_key] = run_trace(policy, seed, env, attack, beta, missing)
                        trace = cache[cache_key]
                        c = costs(sizes, policy)
                        baseline = 200 * c['base_bytes'] - len(missing) * c['per_channel_bytes'][2]
                        emitted = 200 * c['total_bytes'] - len(missing) * c['per_channel_bytes'][2] * (1 + policy[2])
                        assert emitted >= baseline and trace['emitted_objects'] == 200 * (3 + sum(policy)) - len(missing) * (1 + policy[2])
                        completed = trace['completed_epochs']
                        weighted = sum(rows[e]['recorded_success'] for e in completed)
                        bits = sum(rows[e]['payload_bits'] * rows[e]['recorded_success'] for e in completed)
                        assert 0 <= weighted <= len(completed) <= 200
                        if env == 'E0' and attack == 'none':
                            assert len(completed) == 200 - len(missing)
                        sessions.append({'seed': seed, 'environment': env, 'attack': attack, 'beta': beta,
                            'policy': ''.join(map(str, policy)), 'payload_bpp': p, 'offered_epochs': 200,
                            'missing_source_images': len(missing), 'complete': len(completed),
                            'completion_rate': len(completed) / 200, 'recorded_extraction_weighted_complete': weighted,
                            'recorded_extraction_weighted_rate': weighted / 200,
                            'recorded_extraction_weighted_bit_fraction': bits / sum(r['payload_bits'] for r in rows),
                            'baseline_bytes': baseline, 'emitted_bytes': emitted,
                            'extra_fraction': (emitted - baseline) / baseline,
                            'feasible_caps': [cap for cap in (0, .5, 1) if emitted - baseline <= cap * baseline],
                            **trace})
        print(f'Seed {seed} finished; {len(sessions)} session records.', flush=True)

    groups = collections.defaultdict(list)
    for row in sessions:
        groups[(row['payload_bpp'], row['environment'], row['attack'], row['beta'], row['policy'])].append(row)
    summary = []
    for key, rows in sorted(groups.items()):
        assert len(rows) == 5
        rates = [r['completion_rate'] for r in rows]
        summary.append(dict(zip(('payload_bpp', 'environment', 'attack', 'beta', 'policy'), key),
                            seed_n=5, mean_completion=statistics.mean(rates), sd_completion=statistics.stdev(rates),
                            mean_extraction_weighted=statistics.mean(r['recorded_extraction_weighted_rate'] for r in rows),
                            mean_attack_spent=statistics.mean(r['suppressed_objects'] for r in rows),
                            mean_natural_loss_fraction=statistics.mean(r['natural_loss_objects'] / r['emitted_objects'] for r in rows)))
    assert len(sessions) == 3960 and len(summary) == 792
    metadata = {'date': '2026-09-19', 'stage': 'development pilot, not confirmatory or game-optimisation results',
        'full_gamma_files_every_message': True, 'plan_sha256': plan_hash, 'pilot_code_sha256': digest(__file__),
        'transport_code_sha256': digest(OUT / 'transport_validation_v1/transport.py'),
        'source_log_sha256': log['sha256'], 'prior_tests_passed': tests.testsRun,
        'full_byte_equivalence_cases_passed': equivalence_n, 'seed_list': SEEDS,
        'sessions': len(sessions), 'offered_simulated_epochs': len(sessions) * 200,
        'distinct_transport_replays': len(cache), 'source_summary': source_summary,
        'object_sizes_bytes': sizes, 'archive_image_size_counts': dict(size_counts),
        'wall_seconds': time.perf_counter() - started}
    assert digest(HERE / 'PLAN.md') == plan_hash
    for name, value in [('metadata.json', metadata), ('sampled_records.json', samples), ('session_results.json', sessions), ('payoff_summary.json', summary)]:
        (HERE / name).write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == '__main__':
    main()
