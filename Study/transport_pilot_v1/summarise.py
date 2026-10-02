"""Reconcile executed pilot records and produce a scoped development report."""
import collections
import hashlib
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pilot import run_trace


def main():
    metadata = json.loads((HERE / 'metadata.json').read_text())
    sessions = json.loads((HERE / 'session_results.json').read_text())
    summary = json.loads((HERE / 'payoff_summary.json').read_text())
    samples = json.loads((HERE / 'sampled_records.json').read_text())
    assert hashlib.sha256((HERE / 'PLAN.md').read_bytes()).hexdigest() == metadata['plan_sha256']
    assert hashlib.sha256((HERE / 'pilot.py').read_bytes()).hexdigest() == metadata['pilot_code_sha256']
    assert hashlib.sha256((HERE.parent / 'transport_validation_v1/transport.py').read_bytes()).hexdigest() == metadata['transport_code_sha256']
    identities = set()
    for row in sessions:
        identity = tuple(row[k] for k in ('seed', 'environment', 'attack', 'beta', 'policy', 'payload_bpp'))
        assert identity not in identities
        identities.add(identity)
        complete = row['completed_epochs']
        assert row['complete'] == len(set(complete)) == len(row['latencies_ms'])
        assert all(0 <= e < 200 for e in complete)
        assert all(0 <= latency <= 500 for latency in row['latencies_ms'])
        source = samples[str(row['seed'])][str(row['payload_bpp'])]
        assert row['recorded_extraction_weighted_complete'] == sum(source[e]['recorded_success'] for e in complete)
        assert all(source[e]['available'] for e in complete)
        assert row['suppressed_objects'] <= row['attack_cap']
        assert row['emitted_bytes'] >= row['baseline_bytes']
        assert row['wasted_suppressions'] <= min(row['natural_loss_objects'], row['suppressed_objects'])
        assert sum(row['attack_spent_per_block'].values()) == row['suppressed_objects']
        sizes = metadata['object_sizes_bytes']
        p = tuple(map(int, row['policy']))
        b0 = sum(sizes[ch] + 133 for item in source for ch in range(3) if ch != 2 or item['available'])
        actual = sum((sizes[ch] + 133) * (1 + p[ch]) for item in source for ch in range(3) if ch != 2 or item['available'])
        assert (b0, actual) == (row['baseline_bytes'], row['emitted_bytes'])
    for row in summary:
        selected = [r for r in sessions if all(r[k] == row[k] for k in ('payload_bpp', 'environment', 'attack', 'beta', 'policy'))]
        assert len(selected) == 5
        assert abs(statistics.mean(r['completion_rate'] for r in selected) - row['mean_completion']) < 1e-12
    # Independently rerun one complete 200-epoch nontrivial saved condition.
    saved = next(r for r in sessions if r['seed'] == 190903 and r['environment'] == 'E2' and r['attack'] == 'C3' and r['beta'] == .05 and r['policy'] == '111' and r['payload_bpp'] == .2)
    rerun = run_trace((1, 1, 1), 190903, 'E2', 'C3', .05)
    assert all(saved[k] == v for k, v in rerun.items() if k != 'attack_spent_per_block')
    assert saved['attack_spent_per_block'] == {str(k): v for k, v in rerun['attack_spent_per_block'].items()}
    source_failure_counts = {p: sum(not r['recorded_success'] for v in samples.values() for r in v[p]) for p in ('0.1', '0.2', '0.4')}
    missing_counts = {p: sum(not r['available'] for v in samples.values() for r in v[p]) for p in ('0.1', '0.2', '0.4')}
    seed_unique_ids = len({r['image_id'] for v in samples.values() for r in v['0.1']})
    policy_costs = {r['policy']: r['extra_fraction'] for r in sessions}
    feasibility = {str(cap): [p for p, c in sorted(policy_costs.items()) if c <= cap + 1e-12] for cap in (0, .2, .5, .7, .85, 1)}
    lookup = {(r['environment'], r['attack'], r['beta'], r['policy']): r for r in summary if r['payload_bpp'] == .2}
    dominance = {}
    for cap, dominant in ((.5, '110'), (1, '111')):
        eligible = feasibility[str(cap)]
        dominance[str(cap)] = all(lookup[(env, attack, beta, dominant)]['mean_completion'] + 1e-12 >= r['mean_completion']
                                 for (env, attack, beta, p), r in lookup.items() if p in eligible)
    table = []
    for env in ('E0', 'E1', 'E2'):
        for p in ('000', '110', '111'):
            control = lookup[(env, 'none', 0, p)]
            worst = min((r for (e, a, b, pol), r in lookup.items() if e == env and b == .05 and pol == p), key=lambda r: r['mean_completion'])
            table.append(f"| {env} | {p} | {100*control['mean_completion']:.1f}% | {100*worst['mean_completion']:.1f}% | {worst['attack']} | {100*worst['sd_completion']:.2f} pp |")
    paired = []
    for env in ('E1', 'E2'):
        for p in ('110', '111'):
            diffs = []
            for seed in metadata['seed_list']:
                a = next(r for r in sessions if r['payload_bpp'] == .2 and r['seed'] == seed and r['environment'] == env and r['attack'] == 'C3' and r['beta'] == .05 and r['policy'] == p)
                b = next(r for r in sessions if r['payload_bpp'] == .2 and r['seed'] == seed and r['environment'] == env and r['attack'] == 'C3' and r['beta'] == .05 and r['policy'] == '000')
                diffs.append(a['completion_rate'] - b['completion_rate'])
            paired.append({'environment': env, 'policy_vs_000': p, 'attack': 'C3', 'beta': .05,
                           'mean_difference_pp': 100*statistics.mean(diffs), 'sd_difference_pp': 100*statistics.stdev(diffs), 'seed_differences': diffs})
    checks = {'session_count': len(sessions), 'unique_session_ids': len(identities), 'summary_cells_reconciled': len(summary),
              'deterministic_rerun_passed': True, 'distinct_cover_ids': seed_unique_ids,
              'sampled_failure_occurrences': source_failure_counts, 'sampled_missing_image_occurrences': missing_counts,
              'post_pilot_cap_feasibility': feasibility, 'observed_mean_payoff_dominance': dominance,
              'paired_seed_comparisons': paired, 'maximum_completion_latency_ms': max(max(r['latencies_ms'], default=0) for r in sessions)}
    (HERE / 'reconciliation.json').write_text(json.dumps(checks, indent=2) + '\n')
    report = f'''# No-caching transport pilot — development results

**19 September 2026 · Game-Theoretic Defence Allocation for Reliable Multichannel Steganography**

## Outcome

The first bounded CPU pilot is complete. Both full gamma files are charged and sent for every offered message; no session caching is assumed. No embedding, extraction or detector jobs were run. The existing research archive was not modified.

The pilot produced **3,960 session records**, each offering 200 epochs, across eight repetition policies, three environments, eleven attack conditions, five development seeds and three eligible payload strata. These are **792,000 simulated offered epochs, not new embedding trials or independent observations**. The execution took {metadata['wall_seconds']:.2f} seconds, excluding subsequent report/reconciliation work.

The principal finding is that repetition helps in these synthetic conditions, but the original budget grid offers weak evidence for a game-theoretic allocation contribution. A more informative budget comparison can be obtained by reusing this payoff table, without another simulation sweep.

## Design and evidence reuse

The [frozen pilot plan]({HERE}/PLAN.md) records the model before execution. Policies 000–111 use one optional extra copy on C1, C2 and C3 respectively. E0 has no natural loss; E1 has 1% independent object loss; E2 adds three-interval common outages to 1% independent loss. E2 is not labelled 1% total loss. Attack conditions comprise no attack, and five causal suppression rules at each of 1% and 5% nominal object budgets. At 200 offered epochs, the latter budgets allow 6 or 30 suppression actions, subject to non-carrying 100-epoch block caps.

The baseline application cost for the sampled complete files is **398,589 bytes per offered message**, including the new authenticated envelopes. Repeating both gamma objects (110) costs **34.19%** extra; repeating the image alone (001) costs **65.81%** extra; repeating all objects (111) costs **100%** extra. These are different expenditures, not equal-budget competitors. When a policy is under a common cap, report its actual expenditure as well as the cap.

Five seed-specific samples contain 1,000 cover-ID occurrences and **{seed_unique_ids} distinct covers**. The same selected IDs and random impairment streams are used across payloads for paired comparison. The samples include {source_failure_counts['0.1']} archived extraction-failure occurrence at 0.1 bpp, and {source_failure_counts['0.2']} / {source_failure_counts['0.4']} at 0.2 / 0.4 bpp. None of the nine missing saved images happened to be sampled. Their failures remain in the full source summary (1, 4 and 4 missing images respectively), and missing-image logic was checked separately. Sampling did not filter on success.

All 29,991 existing eligible image files had their sizes checked and were 262,159 bytes. The gamma files are 68,295 and 67,736 bytes. The source log and gamma hashes were checked. This is not a fresh content-hash audit of all 29,991 images.

## Representative results

Values below use the 0.2-bpp stratum. Transport results match the other two strata because their sampled object availability, sizes and paired impairments match; these are not three independent confirmations. The recorded-extraction-weighted endpoint differs where an archived extraction failure occurs.

“Worst tested attack” is the minimum of the five attack-specific **five-seed mean completion rates** at a 5% object attack budget. It is not a globally optimal adversary or a mean of per-seed minima. SD is the sample standard deviation across the five session seeds for that selected attack. Ties are represented by one tied attack. All percentages use every offered epoch in the denominator.

| Environment | Policy | No-attack completion | Worst tested attack completion | Representative worst attack | Across-seed SD |
|---|---|---:|---:|---|---:|
{chr(10).join(table)}

This table demonstrates the behaviour of fixed policies. It does **not** demonstrate a mixed-strategy equilibrium, strategic superiority, original-message decoding, or new concealment evidence. No confidence interval treats epochs, payload variants or overlapping cover samples as independent replications. Five development seeds are insufficient for final performance claims.

## Why the budget grid needs refinement

At the original 50% extra-byte cap, policies 000, 010, 100 and 110 are feasible, but repeating the image is not. At the 100% cap all eight policies fit. In the observed mean payoff table, 110 is at least as good as each alternative under the 50% cap, and 111 is at least as good as every alternative under the 100% cap. Both comparisons were checked across every tested environment and attack condition. This is an empirical check over this restricted pilot, not a universal dominance theorem.

Consequently, solving only those capped games could select the largest feasible protection policy without demonstrating an interesting strategic trade-off. Reporting such a result as proof that game theory itself improves reliability would overstate the evidence.

The following **post-pilot design refinement**, not a preregistered result, uses the existing policy costs:

| Extra-byte cap | Feasible policies | Allocation issue |
|---|---|---|
| 20% | {', '.join(feasibility['0.2'])} | Either gamma channel can be repeated, but C3 remains unprotected; useful low-budget bottleneck control |
| 70% | {', '.join(feasibility['0.7'])} | Repeat the image, or both smaller gamma objects; their combination does not fit |
| 85% | {', '.join(feasibility['0.85'])} | Any two channels can be repeated, but all three cannot |

**Recommendation:** use 70% and 85% as the primary trade-off caps in the next allocation analysis, retaining 0%, 20%, 50% and 100% as controls. Feasibility can be recomputed from these results; no new embedding, detector or transport sweep is needed for that analysis. Any strategy chosen using this pilot must then be evaluated on fresh seeds.

## Validation and limitations

- The preceding 35 unit tests passed before execution. Thirty-two full-byte versus representative-object replay cases produced identical transport outcomes and counters. A saved nontrivial 200-epoch condition was rerun and reproduced exactly.
- All 3,960 session identities, 792 summary cells, offered/completed counts, recorded extraction weights, actual byte sums and attack accounting were reconciled after execution.
- Representative short authenticated objects are used for inexpensive event replay; full-file byte sizes determine costs. Identical transport schedules are reused computationally across payloads when their missing-object pattern matches. This is computation reuse, not gamma caching in the protocol.
- The primary endpoint is arrival of all valid required objects by the deadline. The secondary endpoint combines completion with an existing masked-bit extraction flag. Neither is independent original-message recovery.
- The model assumes atomic application objects, precomputed images, synchronized clocks and size-independent delay/loss. It omits serialization delay, bandwidth constraints, queues and packetisation. A 262-kB image is not physically instantaneous on a real link; these results cannot establish achievable network throughput.
- Maximum observed completion latency was {checks['maximum_completion_latency_ms']} ms against a 500-ms deadline. The timing range is not a demanding deadline test. Later sensitivity should include tighter deadlines or longer delays, without changing the present development results.
- Attacks are the five declared budgeted suppression rules, not adaptive best responses. Natural and attacked-loss counters can overlap. Object-priced attacks must not be described as byte-priced interference; the latter remains a sensitivity check before practical claims.
- No checkpoint, ECC, caching, traffic detector, concealment constraint, game solver or held-out strategy evaluation is included. In particular, added headers/repetition may be detectable despite reuse of the old image-level AUCs.

## Deliverables and next step

The [pilot package]({HERE}/README.md) explains how to reproduce the run. [Payoff summaries]({HERE}/payoff_summary.json), [session results]({HERE}/session_results.json), [sampled source records]({HERE}/sampled_records.json), [run metadata]({HERE}/metadata.json), and [reconciliation checks]({HERE}/reconciliation.json) preserve the evidence and its boundaries.

The next step is **restricted game optimisation and fair baseline comparison using this existing payoff table**, prioritising the 70% and 85% resource caps, followed by separate fresh-seed evaluation. Detailed manuscript structure should remain provisional until that strategic comparison is available.
'''
    (HERE.parent / 'No_Caching_Transport_Pilot_Report_v1.md').write_text(report)
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    main()
