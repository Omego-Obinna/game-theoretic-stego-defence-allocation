# Provenance and limits of the public package

The new manuscript's sole author is Obinna Omego. The earlier architecture
manuscript is by Obinna Omego and Michal Bosy. Do not merge their author lists or
present one manuscript's evidence as a new result of the other.

The original selected embedding run is ours-qim-v3-2-20260606T204306-d220f9.
The full source CSV SHA-256 is
e5c56cc77c0b116d6c1e1b7a912dfca1995db3ee9d1ebb43bd7c20252d11c4a0.
The eligible payloads are 0.1, 0.2 and 0.4 bpp. Source failures are retained.
Neither 0.3-bpp experiments nor excluded historical detector runs form new
transport payoffs or enter this package.

## Included and unchanged

The numerical development, fitted-game, validation and sensitivity records,
frozen weights, plans and experiment source files are copied byte-for-byte.
Their historical cross-file hash checks remain operational. No policies were
retuned and no unfavorable results were removed. Code dependencies and original
archived metadata are distinguished from the packaging checks performed later.

## One redacted report

The historical validation_results.json contains local absolute paths to gamma
and stego-image fixtures. In the public copy only the common local archive prefix
is replaced with EXTERNAL_ARCHIVE/. File sizes, fixture hashes, case outcomes
and numerical fields are unchanged. These paths are provenance markers, not
working downloads. Original and packaged hashes are recorded separately in
provenance_manifest.json. Old hashes remain historical; they are not silently
rewritten to represent a newly executed experiment.

## Deliberately excluded

Original cover/stego images, parameter-file contents, complete embedding logs,
hidden messages, detector weights, unpublished manuscript files, submission IDs,
editorial correspondence, Python environments and system caches are excluded.
The full original archive has not been cleared for public redistribution here.
The author must document a lawful access route if offering those materials.

Available source IDs, flags and sizes allow checking the transport analyses.
They do not independently prove the correctness of the inherited masked-bit
extraction flags. Re-running original-byte fixture checks requires the excluded
archive. The included engine unit tests instead use explicitly synthetic bytes
and a test-only authentication key, never a deployment key.

## Authorship and AI assistance

The research workflow used AI assistance for code development, analysis support,
figures and manuscript drafting/editing. This is not represented as proofreading
alone. The author is responsible for reviewing the scientific claims, references,
software, permissions and final outputs, and for making the disclosure required
by the selected journal. Automated tests do not replace that author review.
