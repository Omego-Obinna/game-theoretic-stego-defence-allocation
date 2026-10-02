"""Run deterministic unit checks and bounded read-only archived-object integration."""
import csv
import hashlib
import io
import json
from pathlib import Path
import platform
import time
import unittest

from transport import Config, POLICIES, ENVELOPE_BYTES, costs, feasible, simulate
import test_transport

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE.parent
KEY = b'validation-only-not-a-deployment-key'
SESSION = b'validation000001'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class RecordedResults(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = []

    def addSuccess(self, test):
        self.passed.append(test.id())
        super().addSuccess(test)


def main():
    start = time.perf_counter()
    manifest_path = OUTPUTS / 'Existing_Evidence_Manifest_v1.json'
    manifest = json.loads(manifest_path.read_text())
    source = next(s for s in manifest['sources'] if s['id'] == 'E01')
    log = Path(source['path'])
    if sha(log) != source['sha256']:
        raise RuntimeError('Archive log differs from frozen evidence manifest')
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_transport)
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResults).run(suite)
    if not result.wasSuccessful():
        print(stream.getvalue())
        raise SystemExit('Validation failed; no successful report exported')

    selected = {}
    with log.open(newline='') as handle:
        reader = csv.reader(handle)
        header = next(reader)
        for cells in reader:
            if len(cells) != 153:
                continue
            row = dict(zip(header, cells))
            p = float(row['payload_bpp'])
            if row['run_id'] == manifest['embedding_run_id'] and p in manifest['allowed_payload_bpp'] and p not in selected:
                selected[p] = row
            if len(selected) == 3:
                break
    if set(selected) != {0.1, 0.2, 0.4}:
        raise RuntimeError('Missing eligible archived fixture')

    fixtures, integration = [], []
    for p, row in sorted(selected.items()):
        objects, files = [], []
        for path_field, hash_field in [('gamma1_path', 'gamma1_sha256'), ('gamma2_path', 'gamma2_sha256'), ('stego_path', 'stego_sha256')]:
            path = Path(row[path_field])
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != row[hash_field]:
                raise RuntimeError(f'Archived fixture hash mismatch: {path}')
            objects.append(data)
            files.append({'path': str(path), 'bytes': len(data), 'sha256': digest})
        sizes = tuple(map(len, objects))
        policy_rows = []
        for policy in POLICIES:
            expected = costs(sizes, policy)
            clean = simulate(KEY, SESSION, [tuple(objects)], policy, Config(1))
            if clean['outcomes'][0]['outcome'] != 'complete' or clean['emitted_bytes'] != expected['total_bytes']:
                raise RuntimeError('Archived-object integration or cost reconciliation failed')
            hashes = [f['sha256'] for f in files]
            if clean['outcomes'][0]['object_hashes'] != hashes:
                raise RuntimeError('Receiver object hashes differ from archived ground truth')
            policy_rows.append({'policy': policy, **expected,
                                'feasible_extra_caps': [cap for cap in (0, 0.5, 1, 2) if feasible(sizes, policy, cap)]})
            integration.append({'payload_bpp': p, 'policy': policy, 'case': 'clean_archive_objects', 'passed': True})
        # Real byte-object checks, not decoder calls or statistical experiments.
        for label, policy, drop, expected in [
            ('lost_C1_without_copy', (0, 0, 0), lambda t: t.channel == 1, 'expired'),
            ('lost_C1_original_with_copy', (1, 0, 0), lambda t: t.channel == 1 and t.copy == 0, 'complete'),
            ('lost_C1_all_copies', (1, 0, 0), lambda t: t.channel == 1, 'expired'),
        ]:
            run = simulate(KEY, SESSION, [tuple(objects)], policy, Config(1), natural_drop=drop)
            if run['outcomes'][0]['outcome'] != expected:
                raise RuntimeError(f'Archived-object loss check failed: {label}')
            integration.append({'payload_bpp': p, 'policy': policy, 'case': label, 'passed': True})
        fixtures.append({'payload_bpp': p, 'image_id': row['image_id'], 'run_id': row['run_id'],
                         'recorded_success_extract': int(row['success_extract']), 'files': files,
                         'policy_costs': policy_rows})

    elapsed = time.perf_counter() - start
    report = {'stage': 'Deterministic transport validation; NOT a payoff pilot',
              'date': '2026-09-19', 'python': platform.python_version(), 'platform': platform.platform(),
              'wall_seconds': elapsed, 'dependencies': 'Python standard library only',
              'manifest_sha256': sha(manifest_path), 'archive_log_sha256': source['sha256'],
              'unit_tests': {'run': result.testsRun, 'passed': result.passed, 'failures': [], 'errors': []},
              'archive_integration_cases': integration, 'fixtures': fixtures,
              'envelope_bytes_per_object': ENVELOPE_BYTES,
              'assumptions': ['Full gamma files and saved image transmitted every epoch, no cache or compression',
                              'Precomputed objects; synchronized simulation clock; no feedback',
                              'Eight repetition-only policies; no checkpoints or ECC',
                              'Application-object bytes, no packet/network framing',
                              'No claim of original-message decoding or traffic concealment'],
              'code_sha256': {name: sha(HERE / name) for name in ('transport.py', 'test_transport.py', 'run_validation.py')}}
    (HERE / 'validation_results.json').write_text(json.dumps(report, indent=2) + '\n')
    (HERE / 'validation_test_log.txt').write_text(stream.getvalue())
    first = fixtures[0]
    rows = '\n'.join('| ' + ''.join(map(str, item['policy'])) +
                     f" | {item['extra_bytes']:,} | {item['total_bytes']:,} | {100 * item['extra_fraction']:.2f}% |" for item in first['policy_costs'])
    summary = f'''# Transport validation and cost accounting — v1

19 September 2026 · Game-Theoretic Defence Allocation for Reliable Multichannel Steganography

## Outcome

Implemented and checked a separate CPU-only application-object transport model. **{result.testsRun} unit tests and {len(integration)} archived-object integration cases passed.** This is implementation validation, not a statistical reliability experiment or a game-theoretic performance result.

No embedding, extraction, detector inference or training was performed. Existing archive files were read only. The unit suite uses tiny synthetic byte objects. Integration uses one existing image per eligible payload (0.1, 0.2 and 0.4 bpp), together with its two existing gamma files. These three fixtures are not a representative performance sample.

## What was validated

- Authenticated contents and session/epoch/channel/configuration binding; complete three-object transcript consistency.
- Rejection of modified objects, wrong context, missing components and cross-epoch substitutions.
- Exact-deadline acceptance, late rejection, explicit outcomes for wholly lost epochs and a clock-driven receive window.
- At most one completion per epoch; valid proactive copies may replace lost originals, but cannot repair an archived extraction failure.
- Arrival-spread limits and full payload preservation, including objects longer than a hash digest.
- Actual serialized byte counts for all eight repetition policies, including lost and duplicate transmissions.
- Hard defender byte-cap checks and object-priced attacker budgets with session/block caps, separate copy charges and no natural-loss refund.

Passing finite tests is not a security proof or evidence of original-message recovery. The receiver verifies object contents without access to sender ground truth; the integration harness separately compares received object hashes with archived hashes.

## Cost finding

The archived embedder reads entire gamma files. The checked fixtures contain:

| Channel | Object | Raw bytes | Serialized bytes |
|---|---|---:|---:|
| C1 | First complete gamma file | {first['files'][0]['bytes']:,} | {first['files'][0]['bytes'] + ENVELOPE_BYTES:,} |
| C2 | Second complete gamma file | {first['files'][1]['bytes']:,} | {first['files'][1]['bytes'] + ENVELOPE_BYTES:,} |
| C3 | Existing stego-image | {first['files'][2]['bytes']:,} | {first['files'][2]['bytes'] + ENVELOPE_BYTES:,} |

The validation envelope adds **{ENVELOPE_BYTES} bytes per transmitted object**, including its 32-byte authentication tag. The baseline is **{first['policy_costs'][0]['base_bytes']:,} application bytes per epoch**. All three checked payload fixtures have the same object sizes. This is not an assertion that every archived image has been size-checked.

The following costs assume **full-file transmission on every epoch, without caching or compression**. This is the explicit reference model for validation, not evidence that the submitted manuscript used this wire format. The old average-text-line cost cannot be substituted for these full-file sizes.

| Repeated channels (C1 C2 C3) | Extra bytes | Total bytes | Extra fraction of baseline |
|---|---:|---:|---:|
{rows}

A 1 means one additional copy on that channel; 0 means only the original. At 0%, 50%, 100% and 200% extra-byte caps, the feasible-policy counts are respectively **1, 4, 8 and 8**. With only one optional copy per channel, the 200% cap adds no policies beyond the 100% cap and need not be a separate pilot condition.

Costs exclude packet headers, retransmissions below this model, encryption, key establishment and additional metadata needed by any future full-message decoder. Thus these are exact costs of this validation envelope, not a complete deployment bandwidth estimate. Authentication framing is a new common baseline for future policy comparisons; it is not inherited unchanged from the archived transport script.

## Scope and remaining decision

Checkpoint and ECC actions are deliberately absent. Timing uses precomputed objects, synchronized clocks, 100-ms epoch spacing, a 500-ms deadline, a 300-ms maximum component-arrival spread and a 100-ms copy offset. No online image-generation throughput is inferred. Attacks in the validation harness are deterministic causal suppression rules, not optimised or learned strategies.

The next stage can be a small payoff pilot after agreeing the transport contract, particularly **full gamma files per epoch versus a separately specified cached/session-level alternative**. Full-file transmission is the currently implemented reference. A cached alternative would change what must arrive each epoch and therefore the scientific game; it must not be introduced merely to reduce costs. The current HMAC envelope also does not establish traffic concealment.

No broad pilot, payoff matrix, equilibrium solver, policy ranking or manuscript structure has been produced in this step. Fresh-seed evaluation, uncertainty estimates and byte-priced attacker sensitivity remain future work.

## Reproducibility and files

The implementation requires only Python's standard library. Run instructions, the wire contract and limitations are in the [implementation README]({HERE}/README.md). The [machine-readable validation record]({HERE}/validation_results.json) lists all passed tests, integration cases, archived fixture paths/hashes, policy costs and code hashes. The selected source log was checked against the frozen step-1 manifest before loading fixtures.

Validation and archive checks took {elapsed:.3f} seconds on this run; this is not a deployment throughput benchmark. Code is staged in the writable task output folder because the intended Cover_Parameter_Stego folder remains inaccessible for writes. No archive or folder permissions were modified.
'''
    (OUTPUTS / 'Transport_Validation_and_Cost_Report_v1.md').write_text(summary)
    print(f'{result.testsRun} unit tests; {len(integration)} archived-object integration cases passed; {elapsed:.3f}s.')
    print(f'Baseline application bytes per epoch: {first["policy_costs"][0]["base_bytes"]}')


if __name__ == '__main__':
    main()
