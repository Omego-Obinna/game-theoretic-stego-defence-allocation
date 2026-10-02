# Data dictionary and interpretation

JSON probabilities and proportions use the interval 0-1 unless a field explicitly
states otherwise. Manuscript percentages multiply by 100; contrasts in percentage
points multiply probability differences by 100. Byte counts are serialized
application bytes, not physical link occupancy. Times are milliseconds.

## Sampled records

sampled_records.json is keyed first by simulation seed, then payload rate. Each
list contains 200 ordered source records corresponding to offered epochs.
image_id identifies the archived image; available records whether its source
image exists; recorded_success is the inherited masked-bit extraction indicator.
False availability remains in the offered denominator; repeats do not redraw the
extraction flag. Inspect the supplied records for the exact scalar types.

## Raw session records

session_results.json (pilot) and session_results.json.gz (validation/sensitivity)
are JSON lists, not CSV or newline-delimited JSON. A row is a pure-policy session.
The gzip containers preserve the recorded raw files and their hashes.

| Field | Meaning |
| --- | --- |
| seed, payload_bpp, environment | Simulation seed, inherited payload rate, and E0/E1/E2 impairment condition |
| beta, attack | Attacker budget fraction and selected rule |
| pricing | Sensitivity only: objects or bytes; not physically matched strengths |
| policy | Three-character optional-copy pattern in C1/C2/C3 order |
| completed_epochs, complete | Completed epoch indices and their count |
| completion_rate | Completed count divided by offered epochs |
| recorded_extraction_weighted_complete/rate | Completed epochs with the inherited success flag; not independent message decoding |
| baseline_bytes, emitted_bytes, extra_fraction | One-copy offered workload bytes, actual emitted bytes, and relative extra expenditure |
| latencies_ms | Completion latency only for completed epochs; not a failure-inclusive delay distribution |
| attack_cap, attack_spent_per_block | Attacker ledger allowance and per-block spending |
| natural_loss_objects, wasted_suppressions | Background losses and attacks spent on also-lost objects; counts can overlap |
| observed_target, inferred_repetitions | Sensitivity rule's causal metadata inference, where applicable |

## Game and evaluation records

game_results.json contains 216 configurations. Each includes a feasible policy
list, original attack list, payoff_matrix, noncooperative solution, comparator
weights/costs and cooperative worths/diagnostics. All original objects remain
mandatory in every coalition. Coalitions are integer bitmasks 0-7; policy text is
C1/C2/C3 order (100 means capability R1, coalition mask 1).

frozen_strategies.json contains original development-fixed policy and coalition
mixtures and bootstrap settings. evaluated_strategies.json contains 216 validation
or 288 sensitivity configurations, eight strategies each, seed-level expected
scores and descriptive paired bootstrap intervals. The 20 seeds are resampled
jointly across policies/attacks; 2,000 resamples are used.

Minimise after averaging attack-specific seed scores and integrating the mixture.
Do not average each seed's minimum instead. Capability worth is a restricted
minimax gain over the baseline; Shapley values explain this fitted worth. Frozen
coalition scores are not new worths or newly estimated Shapley values.

Historical metadata, execution manifests, diagnostics and verification reports
record the stage at which each check occurred. The later repository packaging
report is under validation/; it is not new experimental evidence.
