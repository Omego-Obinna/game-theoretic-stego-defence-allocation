# No-caching transport pilot v1 — frozen development design

19 September 2026. Author decision: both full gamma files are sent for every offered message. No caching, new embedding, extraction, detector inference or training. This is a development pilot, not final confirmatory evidence.

## Design fixed before execution

- Eight repetition policies: 000 through 111. One optional copy per channel; no ECC/checkpoints.
- Three payload strata: 0.1/0.2/0.4 bpp from the allowlisted historical run, including recorded extraction failures. All 10,000 source IDs per stratum are eligible for sampling. Missing saved images do not emit a C3 object; their epochs cannot complete.
- Five development seeds: 190901–190905. For each seed sample 200 distinct cover IDs uniformly without replacement. Use the same IDs/order across payloads. Repeated images/seeds/payloads are not independent replications.
- Timing inherited from validated model: epoch interval 100 ms, deadline 500 ms, copy offset 100 ms, window 10, maximum arrival spread 300 ms. Objects are precomputed. No service time, serialization delay, queueing or link-capacity constraint is modelled.
- E0: no natural loss; delay 20 + discrete Uniform[0,50] ms.
- E1: 1% independent object loss; delay 20 + Uniform[0,50] + Uniform[0,50] ms.
- E2: 1% independent object loss; delay 20 + Uniform[0,50] + Uniform[0,100] ms; a common outage starts with probability 0.005 per epoch boundary when inactive and lasts three intervals. Copies are lost according to their send time, not their logical epoch.
- Independent pseudorandom streams are keyed by seed, environment and transmission identity. Shared transmissions see the same natural impairment across policies/attacks. Impairment randomness is unavailable to the attacker.
- Attack conditions: no attack; beta 0.01 and 0.05 each with random-online, C1-targeted, C2-targeted, C3-targeted, and burst suppression. Eleven conditions total.
- Random-online rule: suppress current emission if an independent keyed draw is below 0.25 and budget remains. This is an online Bernoulli rule capped by budget, not uniform sampling of an entire future trace.
- Targeted rules suppress eligible transmissions on the named channel while budget remains. Burst rule chooses one seeded start epoch per 100-epoch block, then suppresses consecutive eligible emissions whose logical epoch is at or beyond that start, while budget remains.
- All attack rules are causal. Session allowance floor(beta × 3N), per-100-epoch allowance floor(beta × 300), no carry-over. Originals and copies cost one action each. Allowance is based on offered epochs even when a source image is missing. Natural loss neither spends nor refunds attack allowance.
- Defender caps 0%, 50%, 100% extra application bytes; 200% omitted because it adds no policies. Each policy must satisfy its cap for the actual offered workload. Count emitted gamma objects, images and envelopes; absent C3 objects incur no transmitted bytes. B0 is the actual corresponding one-copy workload cost.

## Endpoints and computation

Primary: valid required-object completion count / all 200 offered epochs. Secondary: completion AND the image's archived exact masked-bit extraction flag, also divided by 200; bit-weighted version uses recorded payload lengths. Neither endpoint establishes original-message decoding. Record latency conditional on completion, missed epochs, transmitted bytes, attack expenditure and natural loss.

Use short authenticated representative objects to replay suppression/delay; full-file sizes determine costs. No tampering is part of the payoff sweep. Test metadata replay against the already validated receiver using full archived object bytes before running the pilot, including missing C3. This abstraction is valid only for the current atomic-object model, whose delays/losses are independent of byte length. It cannot support bandwidth-constrained latency or cryptographic-speed claims.

Planned scope: 8 policies × 3 environments × 11 attack conditions × 5 seeds × 3 payload strata = 3,960 sessions / 792,000 offered simulated epochs. These are reused cover records, not 792,000 new embedding trials. Record all session-level outcomes and selected source IDs. Report seed means, sample standard deviations and paired seed differences, not millions of independent-trial confidence bounds.

Do not select an equilibrium or claim a strategic improvement in this stage. Produce the restricted policy–attack payoff summaries and identify feasible policies, saturated controls and obvious design limitations. Policy optimisation and fresh-seed evaluation are subsequent stages. Best-in-pilot rows are descriptive, not held-out winners.

## Execution gates

Source manifest/log hashes and eligible counts must match. Run the prior 35 unit tests. Pass full-byte versus representative-object equivalence checks. Verify denominators, cost reconciliation, attack caps, missing-image handling, source-success flag persistence, clean control behaviour and deterministic rerun identity. Stop on failure. Save code/config/source hashes with results.
