# Frozen-defence transport sensitivity v1

Design recorded before the new sensitivity outcomes. Scope: adaptive targeting and byte-priced interference only. Both complete gamma files remain sent for every offered message. No new embedding, extraction, detector training, defence optimisation or coalition fitting.

## Scenarios and prior information

Reuse the twenty seeds 191001–191020 and sampled source records from fresh_seed_validation_v1, preserving missing-image/extraction failures and paired randomness. These validation results have already been inspected; this is explicitly a paired sensitivity study, not a new untouched holdout. Use E1 and E2, both 1%/5% nominal attack fractions, all eight repetition policies and all three eligible payloads. E0 remains a deterministic test environment, not an additional sensitivity sweep.

Keep the immutable defence and coalition weights from the preceding freeze. Evaluate both endpoints and all six existing defender caps; 70%/85% remain principal examples. Same timing, observer access, source costs and no-caching model. Tight deadlines, packetisation, physical bandwidth and traffic concealment are not added in this stage.

## Two interference ledgers

- **Object-priced:** session cap floor(beta × 3N), logical 100-epoch block cap floor(beta × 3n_block), as before. Suppressing each original or copy costs one action.
- **Byte-priced:** session cap floor(beta × B0), block cap floor(beta × B0_block), where B0 is the actual one-copy transmitted workload, including every 133-byte envelope and excluding absent C3 files. Suppressing a transmission costs that object's full serialized size, not the short representative object's length. B0 is identical across defence policies for the same workload. No carry-over between blocks.
- Budget ceilings are externally specified workload-accounting quantities. The attack does not receive future natural-loss draws, object lists, source success flags or receiver state. Equal numeric beta values do not express equal physical capabilities across the two ledgers.
- All-copy suppression reserves the required amount at the original transmission. Pending reservations reduce available session/block budget; amounts move from reserved to spent as each actual copy is suppressed. Charge copies to their logical epoch block. Assert no pending reservations at the end. Never refund suppression because natural loss also occurred.

## Attack catalogue

Retain the original five rules unchanged: random-online, C1, C2, C3, burst. Apply them under each ledger; reuse recorded object-priced outcomes after checking compatibility of the new engine.

Add four observation-based rules:

1. observe_C1, observe_C2, observe_C3: fixed-target controls with the same observation warm-up and all-copy budget commitment used by the adaptive rule.
2. observe_best: one identical causal algorithm across defender policies. It infers the session's repetition pattern from actual emitted traffic, then selects a target minimising the cost to suppress all copies of one logical epoch's channel object. Under object pricing this is 1+r_i; under byte pricing it is (1+r_i) × that channel's observed serialized byte length. Ties use C1, then C2, then C3.

The observer sees all actual emissions before suppression/natural loss, including public channel, epoch and copy identifiers. It knows the deterministic 100-ms copy offset and at most one extra copy. For each channel, it records the first actual original, then waits strictly beyond its copy boundary before inferring whether a copy was emitted. If the first image is absent, it must wait for a later actual C3 original. No inference is taken from a complete future frame list or from the true policy argument.

All four observation-based rules wait until all three channels' repetition counts are inferred. They then fix a target for the session and suppress an epoch only if the original arrives after learning and the remaining budget can cover its full copy set. They do not suppress late copies whose original was not committed. They are causal one-time policy-learning heuristics, not unrestricted optimal adaptive attackers. All-copy reservation is not assumed to dominate partial suppression under natural loss.

## Comparisons

For frozen mixtures, weight each attack's pure-policy outcomes first, then take a minimum over attack rules. Do not choose a different fixed-target control for each pure-policy row before mixing; that would give an oracle the realised policy.

Report legacy-five, matched fixed-reservation-three, adaptive-only and augmented-nine catalogue performance. The augmented catalogue contains the legacy rules and cannot improve the defender's restricted worst-case score. Compare within each ledger; do not interpret same-beta cross-ledger differences as a fair test of equally powerful adversaries.

Keep the balanced-randomisation and frozen Shapley-knapsack comparators. Evaluate frozen coalition-policy values under the expanded catalogue without refitting or calculating a new optimal core. Use twenty seed blocks and 2,000 paired bootstrap resamples (seed 192999) for descriptive intervals, with the previously documented nonsmooth-minimum and multiple-comparison limitations. Record each fixed attack's mean and inference timing/target evidence.

Planned total: 20 × 2 environments × 2 attack fractions × 9 attacks × 2 ledgers × 8 policies × 3 payloads = 34,560 session records (6,912,000 offered simulated epochs). Of these, 9,600 legacy object-priced records are reused and 24,960 records are new sensitivity outcomes. Identical transport replays may be shared computationally across payloads but gamma bytes remain charged on every message.

## Gates

Preserve source/freeze/earlier result hashes. Test observation-prefix causality, exact copy-boundary ordering, missing originals, actual byte sizes, reservation exhaustion, cross-block copies, fixed denominators, and zero final pending budget. Reconcile all legacy object-rule records against the original receiver semantics. Verify every frozen support meets its actual hard cap and all extended minima are no larger than their legacy counterparts. Stop on any failed gate; never retune to repair a negative research result.
