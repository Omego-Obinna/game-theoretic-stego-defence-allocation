# Frozen-strategy fresh-seed validation v1

Design fixed before generating new transport outcomes. Both full gamma files are sent for every offered message. No caching, new embedding, decoding, detector inference or training.

## Freeze and sampling

1. Hash the existing pilot, fitted games and source files. Copy the fitted strategy probabilities into a freeze manifest. Reconstruct optional coalition mixtures using ONLY the original development matrices and verified solver; confirm saved coalition values. Save all frozen weights before running holdout simulations. No holdout-informed fitting is permitted.
2. Use twenty fresh simulation seeds 191001–191020, disjoint from development and validation-fixture seeds. Sample 200 distinct cover IDs per seed from the 9,038 eligible archive IDs excluding the 962 IDs used in policy development. Use the same ID/order across payloads and shared impairment streams across policies/attacks. Sampling is independent across seeds, so holdout samples can overlap each other.
3. Include archived failures. Missing images emit no C3 object and cannot complete, but remain in offered-epoch denominators. These are new simulation draws and cover IDs disjoint from the policy-development samples, not new images, new CNN tests or a wholly unseen source corpus.

## Simulation and evaluation

Keep the existing environments, deadlines, five causal attack rules, object-budget accounting and eight repetition policies unchanged. Include the no-attack control. Scope: 20 seeds × 3 environments × 11 attack conditions × 8 policies × 3 payloads = 15,840 session records, each offering 200 epochs (3,168,000 simulated offered epochs, not independent observations).

Evaluate all 216 frozen game configurations and their eight stored strategies. Principal trade-off caps are 70%/85%; the other caps are controls. Both transport completion and recorded-extraction-weighted completion remain separate. The latter does not mean newly verified original-message decoding.

Compute a frozen mixture's expected performance exactly as the weighted sum of its pure-policy outcomes for each seed and attack. This integrates out the random once-per-session policy draw and avoids adding unnecessary Monte Carlo noise. It is not a sample of deployed mixed-policy sessions. Report actual expected transmitted bytes and enforce every supported pure policy's cap on each new workload.

For a strategy, the restricted worst-case statistic is the minimum of its five attack-specific means across twenty seeds. For comparisons, subtract these strategy-specific restricted worst-case statistics, not averages of seed-wise minima. Also retain the paired mean difference for each fixed attack.

Use 2,000 paired seed-block bootstrap resamples, seed 191999, taking 2.5/97.5 percentiles. Each resample keeps all policy/attack observations from a selected seed together. The principal comparison is frozen minimax versus balanced equal-repetition mixing; also compare best-fixed and Shapley-knapsack policies. Intervals are descriptive and unadjusted for multiple comparisons; twenty seeds and a minimum over tied/noisy attack means do not justify universal coverage or significance claims. No equivalence margin or accept/reject tuning threshold is imposed after seeing results.

## Cooperative component

Evaluate the frozen Shapley-knapsack policy alongside all other strategies. Also evaluate each coalition's development-fitted mixture against the fresh outcomes and centre its restricted worst-case performance on the frozen empty-coalition policy. These are out-of-sample values of trained coalition policies, not reoptimised holdout coalition worth. They may fail monotonicity because the frozen policies are estimated. Do not silently replace them with holdout-optimal solutions or claim a newly validated stable coalition. Keep the fitted Shapley attribution unchanged; record coalition-value changes without converting them into new spending rules.

## Boundaries

This evaluates generalisation within the original synthetic environment family and five-rule adversary catalogue. It does not add adaptive policy-inference attacks, byte-priced interference, tighter deadlines, bandwidth queues or new sources. Those are separately scoped sensitivities. Passing tests or a positive heldout comparison does not establish cryptographic security, full-message recovery, traffic concealment or Q1 acceptance.

Save all raw session records, sampled source metadata, frozen weights, comparison intervals, coalition-policy evaluations and hashes. Do not alter prior stage outputs or refit after execution. Report gains, ties and losses, including any balanced-policy advantage.
