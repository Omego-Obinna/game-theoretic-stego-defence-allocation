# Game-Theoretic Defence Allocation for Reliable Multichannel Steganography

Research software and saved numerical results for the manuscript by **Obinna
Omego**. This package does not assert acceptance or publication of the manuscript.
It is prepared for an author-reviewed repository release.

## What this work contributes

The study allocates optional whole-object repetitions across three complementary
transport objects under hard additional-byte caps. A restricted attacker-defender
game selects a feasible mixture; coalition-restricted game values support Shapley
attribution, interaction analysis and core diagnostics. Frozen policies are
evaluated on new simulation seeds and under changed attacker observations and
interference prices.

This is a **transport-allocation and capability-valuation study**, not a new
embedding algorithm, original-message decoder, deep-learning detector, physical
network implementation, or proof of steganographic concealment.

## Quick start: no GPU or source image archive required

Use Python 3.12 (tested with 3.12.3). From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python tools/check_integrity.py
python tools/reproduce.py check
python tools/reproduce.py analysis
```

On Windows, activate with `.venv\Scripts\activate` instead. The commands use only
the included transport/game code and saved numerical records. No embedding,
extraction, detector training, external service, or download of research data is
performed. Package installation itself requires access to your Python package
source. See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for precise scope.

Reproduction runs write to a newly created directory under reproduced/. They do
not overwrite the reference study/ files, alter frozen policies, or select new
policies using validation outcomes. Do not run the historical entry points
directly in study/ unless you deliberately intend to replace their outputs.

To rebuild the figures from saved estimates:

```bash
python tools/reproduce.py figures
```

## Repository contents

| Location | Contents |
| --- | --- |
| study/transport_validation_v1/ | Authenticated reference receiver, byte accounting, 35 unit tests, historical validation report |
| study/transport_pilot_v1/ | Development simulator, fixed plan, sampled record metadata, 3,960 saved session records and payoff summaries |
| study/game_analysis_v1/ | Restricted minimax, 1,728 coalition subgames, Shapley/core routines, 216 fitted configurations and 15 tests |
| study/fresh_seed_validation_v1/ | Frozen strategies, development-disjoint samples, 15,840 saved session records and 216 evaluation configurations |
| study/transport_sensitivity_v1/ | Observation/pricing extension, 34,560 saved records, 288 evaluation configurations and 14 additional tests |
| study/manuscript_results_v1/ and study/manuscript_rebalanced_v1/ | Original figure-generation code |
| recorded_figures/ | Ten existing publication figure PDFs and full-grid numerical figure data |
| tools/ | Safe copied-workspace reproduction and integrity checks |
| docs/ | Data dictionary, provenance, scientific limits and figure mapping |
| provenance_manifest.json | Original and packaged SHA-256 fingerprints of copied research files |
| CHECKSUMS.sha256 | Integrity inventory for the prepared repository |
| validation/ | Packaging verification report and logs |

## Main findings and interpretation

- At the principal caps under the original catalogue, minimax improves on the
  development-selected fixed policies but does not consistently beat balanced
  repetition. The shared cap is not equal actual byte expenditure.
- Shapley values attribute fitted capability worth; they are not probabilities,
  byte allocations or guarantees of a stable core. Empty-core cases are retained.
- Repetition-aware targeting and changed suppression prices can reverse the
  ranking of frozen policies. These are transfer scores, not refitted game values.
- The primary endpoint is valid completion of all required objects before the
  deadline. The secondary endpoint uses an archived masked-bit extraction flag,
  not a new independent original-message decoding measurement.
- Bootstrap intervals are descriptive paired seed-block intervals. They do not
  establish equivalence, guaranteed coverage, or independence across the grid.

## Inherited data and excluded materials

The earlier manuscript, *Cover-Parameterised Multichannel Hybrid Steganography:
Compositional Security, Detectability, and Robustness*, by Obinna Omego and Michal
Bosy, supplies the architecture and original archive. It is a separate work;
no acceptance, preprint identifier or public archive location is assumed here.
Eligible payloads are **0.1, 0.2 and 0.4 bpp only**. No 0.3-bpp data or excluded
detector runs are included or used by this package.

Source image identifiers, availability flags, archived extraction indicators and
object sizes needed for the saved-outcome analysis are included. Original images,
gamma-file contents, the full embedding CSV, detector checkpoints, manuscript
submissions and correspondence are excluded. Hence the package does **not**
independently regenerate the original embedding archive or repeat its full-byte
fixture validation. See [PROVENANCE.md](docs/PROVENANCE.md).

## Licence and citation

The new software and software documentation use the MIT licence. Research-output
and third-party rights are separately described in [LICENSE_SCOPE.md](LICENSE_SCOPE.md).
Use CITATION.cff for the software citation. Repository URL, release DOI and any
eventual manuscript citation must be added only after they actually exist.

## Release and peer review

This author-named package is **not an anonymous reviewer supplement**. Before
public deposition, check the journal's double-anonymous review process, author
and data-sharing permissions, and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).
Do not upload the separate submission_private/ folder or confidential submission
identifiers. A GitHub release can subsequently be archived in a persistent
repository such as Zenodo; an archival DOI must never be invented.
