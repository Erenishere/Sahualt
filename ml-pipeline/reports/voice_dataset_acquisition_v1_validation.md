# VOICE-DATASET-ACQUISITION-V1 validation

Gate status: **GREEN**. Dataset **FLEURS-VOICE-V1: FROZEN**.
This completes acquisition and preparation, not STT evaluation. Whisper/MMS were not run.
This report supersedes the acquisition-dependent RED/PENDING snapshot in
[the original preparation report](voice_eval_v1_preparation.md).
Machine evidence: `artifacts/voice_evaluation_v1_validation.json`.

## Frozen authority and acquisition

The unchanged [EVAL-VOICE-V1](../docs/EVAL-VOICE-V1.md) and
`configs/fleurs_sources_v1.json` pin official Google FLEURS revision
`70bb2e84b976b7e960aa89f1c648e09c59f894dd`. No alternate dataset, split, selection,
language, reference policy or reduced sample count was introduced.

Protocol registry checksum:
`28c98d02effdefd46cc87e67f2d7c99512246ce553709b246b9848f9d142eb17`.
Canonical source-lock SHA-256:
`8d455480cffd08d82616dab1e878c6f5b3b481cdbc08e412c6ac1b461cc65664`.
The preregistration registry remains immutable; its historical `NOT_YET_FROZEN`
observation is not the current dataset status. Current status comes from the separate
`configs/corpora/fleurs_voice_v1.json` external freeze descriptor and full verifier.

All complete test archives passed exact pinned size and whole-object SHA-256 checks:

| Config | Source archive | Bytes | Verified SHA-256 |
| --- | --- | ---: | --- |
| `en_us` | `data/en_us/audio/test.tar.gz` | 289,851,356 | `d9c2e37b41aacd41bc283554a0a82b5476b36887049774ecb2819dcaaa55a356` |
| `ur_pk` | `data/ur_pk/audio/test.tar.gz` | 149,549,883 | `618840ad5fb21a59cc179ec535ddbc8e756e2fb40624689c6d59c93e019cd745` |
| `sd_in` | `data/sd_in/audio/test.tar.gz` | 621,842,598 | `94f572b97e73c8176f39de3922a4022f729f50d285a493aea630ccfc664487ed` |
| `ps_af` | `data/ps_af/audio/test.tar.gz` | 303,903,990 | `153dc026a7790539d71aeead7933d0f092b318ade0f327cd4355b8de5473795e` |

Total compressed bytes: **1,365,147,827**. The existing acquisition command independently
verified all **9** cached authoritative objects: these 4 archives, 4 test TSVs and the card.
Their cache is `.cache/voice/fleurs/<pinned-revision>/`; source files were not edited.

The isolated operational downloader uses bounded 4 MiB HTTP ranges, exact HTTP 206/range/size
checks, up to 8 workers and bounded retries. It resumes local fragments but treats them as
untrusted until the assembled whole object passes its pinned checksum. Verified objects are
installed without overwriting different content. Repeating acquisition reused all four
complete objects. No additional dependency or frozen implementation change was needed.
Signed redirect URLs and upstream exception strings are not printed. Earlier partial cache
objects remain ignored and are not accepted as source verification evidence.

## Actual recordings, preparation and lineage

| Language/config | Parsed source rows | Selected | Prepared | Frozen |
| --- | ---: | ---: | ---: | ---: |
| English / `en_us` | 647 | 50 | 50 | 50 |
| Urdu / `ur_pk` | 299 | 50 | 50 | 50 |
| Sindhi / `sd_in` | 980 | 50 | 50 | 50 |
| Pashto / `ps_af` | 512 | 50 | 50 | 50 |
| Total | 2,438 | 200 | 200 | 200 |

The existing seeded, distinct-sentence selection was replayed unchanged. Data-only selection
excludes 5 out-of-duration rows, 210 repeated readings of selected sentence IDs and 2,023 rows
outside the fixed subset. Conflicting-reference groups and missing/invalid references: **0**.
No selected sample failed verification or was replaced.

All 200 selected originals are mono 16 kHz IEEE float32 WAV. Offline `fleurs-pcm16-v1`
conversion produced 200 mono, 16 kHz, signed little-endian PCM16 WAVs. Exact source/TSV frame
parity passed: **36,355,840 frames**, **2,272.24 seconds** in total. The locked quantizer
records **7 clipped samples in 1 recording**; this is disclosed conversion evidence,
not silent repair or a reason to replace a selected recording. No resampling, trimming,
downmixing, denoising, gain normalization or model preprocessing occurred.

The verifier recomputed source/prepared audio hashes, replayed conversion byte-for-byte,
checked published reference text, source rows, tar members, filenames, selection and metadata.
Published human-authored read-script references remain exact; no audio/reference was generated
or rewritten. This does not assert newly verified verbatim annotations or individual consent.
CC BY 4.0 attribution and the subset/conversion change notice are retained in `ATTRIBUTION.md`.
The runtime's existing bounded PCM16-only audio contract remains unchanged.

## Dataset identity and determinism

External descriptor: `configs/corpora/fleurs_voice_v1.json`.
Bundle: `artifacts/voice_evaluation_v1/`.

Manifest SHA-256:
`e2efd78d0af8fe8ecc2c6483ab7db0ff9dba6763fd148be58bbc6c4fd05499e4`.

Semantic SHA-256:
`7ab3516ef5a1bcc735bfb833f24c818015970b5bfc7bc4b138579c7c11d059a2`.

The bundle contains **410 files**, including 200 selected original WAVs, 200 prepared WAVs,
5 card/TSV copies and 5 manifest/input/lineage/audit/attribution files. The manifest indexes
409 files, excluding itself; total bundle size is **220,955,433 bytes**.
The internal manifest deliberately retains `PREPARED_REQUIRES_EXTERNAL_FREEZE`; the separate
verified corpus descriptor supplies **FROZEN** status without mutating its hashed input bundle.

A second actual preparation + freeze + full verification compared every bundle file and the
external descriptor: **411/411 unchanged**, with an unchanged file set and both checksums.
This is actual FLEURS rebuild determinism, not synthetic-fixture evidence. The repeat preparation
took **21.328 seconds**, an observational data-preparation measurement, not STT latency.
Canonical Python 3.12 / Unicode 15.0.0 / NumPy 2.2.6 settings remain locked. Variable observations
and this validation report are outside the canonical hashed bundle.

## Executed verification

| Check | Result |
| --- | --- |
| Full suite, database tests enabled, Hub offline | **766 passed, 4 skipped**, 186.74 s |
| Database-marked tests, included in total | **91 passed** |
| Existing benchmark tests, included in total | **84 passed** |
| New acquisition transport tests, included in total | **10 passed** |
| Opt-in model skips | 2 visual + 2 STT; no STT inference |
| Ruff lint / formatting | PASS / PASS, 159 Python files |
| Configured mypy | PASS, 72 files |
| Explicit voice + integration + acquisition-script mypy | PASS, 29 files |
| Dependency validation | PASS; no new dependencies |
| Frozen text-query tooling | GREEN, unchanged |
| Protocol/source/code freeze verification | PASS, unchanged |
| Full source acquisition verification | PASS, 9/9 complete objects |
| Actual audio/reference lineage and conversion parity | PASS, 200/200 |
| Actual repeated build / freeze verification | PASS, byte-identical |

Two existing dependency deprecation warnings remain; no dependency or test was weakened.
Transport tests use tiny synthetic byte fragments, never benchmark audio or reference evidence.
Existing database, fixture, projection, text-tooling, visual API and bridge regression tests
remain green. A separate cached visual model smoke was not rerun in this acquisition gate.

Reproduction from the repository root and its existing environment:

```powershell
python scripts/prepare_voice_evaluation.py verify-protocol
python scripts/acquire_voice_dataset_v1.py --allow-download --workers 8
python scripts/prepare_voice_evaluation.py acquire
python scripts/prepare_voice_evaluation.py prepare
python scripts/prepare_voice_evaluation.py freeze
python scripts/prepare_voice_evaluation.py verify
$env:RUN_DATABASE_TESTS='1'
$env:HF_HUB_OFFLINE='1'
python -m pytest -q --tb=short
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m mypy src/sahulat_voice integration scripts/acquire_voice_dataset_v1.py
python -m pip check
python scripts/freeze_text_query_tooling.py --verify-only
```

The range downloader completes the archives only; an empty cache still needs the existing
acquisition workflow for the pinned card/TSVs. On this completed cache, `acquire` validates
all source objects without downloads. Offline `verify` needs the self-contained bundle and
external registries, not the full archive cache. Retain attribution with distribution.

## Complete file inventory and stop boundary

Added:

- `scripts/acquire_voice_dataset_v1.py`
- `tests/voice/test_dataset_acquisition.py`
- `reports/voice_dataset_acquisition_v1_validation.md`
- `configs/corpora/fleurs_voice_v1.json` (generated external freeze descriptor)
- `artifacts/voice_evaluation_v1/manifest.json`
- `artifacts/voice_evaluation_v1/evaluation-input.json`
- `artifacts/voice_evaluation_v1/lineage.json`
- `artifacts/voice_evaluation_v1/metadata-audit.json`
- `artifacts/voice_evaluation_v1/ATTRIBUTION.md`
- `artifacts/voice_evaluation_v1/source_metadata/README.md`
- `artifacts/voice_evaluation_v1/source_metadata/{en_us,ur_pk,sd_in,ps_af}/test.tsv` (4 files)
- `artifacts/voice_evaluation_v1/source_audio/{en,ur,sd,ps}/*.wav` (200 files, individually indexed in the manifest)
- `artifacts/voice_evaluation_v1/audio/{en,ur,sd,ps}/*.wav` (200 files, individually indexed in the manifest)

Modified:

- `README.md` (current acquisition/freeze status and report link only)
- `reports/voice_eval_v1_preparation.md` (superseding completion notice; historical evidence retained)
- `artifacts/voice_evaluation_v1_validation.json` (current measured completion evidence)

Ignored cache additions: four complete official archives and resumable acquisition fragments.
No Git metadata is present in this checkout; no commit, branch or push was performed.
Derived audio and caches remain excluded by the existing ignore conventions; freeze registries
and this inventory identify the intentional reproducibility artifacts.

Acquisition blockers: **none**. No secrets, catalog writes, schema changes, human query work,
human relevance labeling, FTS, BM25, vectors, retrieval or Search infrastructure were introduced.
Model results remain **NOT_RUN**. FLEURS locale/read-speech limitations and MMS training-domain
exposure remain as preregistered; no accuracy, production readiness or leaderboard claim is made.
Stop here. `EVAL-VOICE-RUN-V1` requires a separate explicit task; neither recognizer is run now.
