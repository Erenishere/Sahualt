# EVAL-VOICE-V1 preparation validation

Completion notice: [VOICE-DATASET-ACQUISITION-V1 is now GREEN](voice_dataset_acquisition_v1_validation.md).
All four pinned archives are verified; the actual 200 recordings are prepared and externally
FROZEN with byte-identical rebuild verification. Whisper/MMS remain NOT RUN. The machine
validation evidence now records that completion. The original RED/PENDING snapshot below is
retained as historical evidence of the earlier acquisition dependency, not current status.

## Current gate state

| Item | Verified state |
| --- | --- |
| Protocol and source/code preregistration | GREEN / FROZEN |
| Acquisition/preparation/freeze tooling | GREEN |
| Overall actual protocol/subset gate | RED / DATA PENDING |
| Actual FLEURS audio acquisition | NOT COMPLETE: 0/4 complete archives verified |
| Actual 200-sample corpus freeze | PENDING |
| Whisper/MMS model execution | NOT RUN |
| STT accuracy / model latency | NOT MEASURED |
| Voice-to-search / Search infrastructure | NOT IMPLEMENTED |

Authoritative policy: [EVAL-VOICE-V1](../docs/EVAL-VOICE-V1.md),
`configs/eval_voice_v1.json`, `configs/fleurs_sources_v1.json`.
External preregistration: `configs/gates/eval_voice_v1_protocol.json`;
registry checksum `28c98d02effdefd46cc87e67f2d7c99512246ce553709b246b9848f9d142eb17`.
The protocol/source/code were registered and verified before full audio acquisition or STT
model execution. Selected source encoding was inspected before registration: mono 16 kHz
IEEE float32 WAV with an 18-byte format chunk, supported by the offline adapter.

## Source and selection evidence

Dataset: [Google FLEURS](https://huggingface.co/datasets/google/fleurs), pinned revision
`70bb2e84b976b7e960aa89f1c648e09c59f894dd`. License:
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with attribution/change notice.
No train/dev samples, alternate corpus or cleaned derivative are used. Complete test-archive
bytes/SHA-256 are pinned; total archive size is 1,365,147,827 bytes. The cache is ignored.

All four exact UTF-8 headerless TSVs have passed their pinned checksum/size checks:

| Language/config | Source rows | Selected distinct sentence IDs | Duration exclusions | Repeated readings of selected IDs | Outside fixed subset |
| --- | ---: | ---: | ---: | ---: | ---: |
| English/en_us | 647 | 50 | 0 | 44 | 553 |
| Urdu/ur_pk | 299 | 50 | 0 | 23 | 226 |
| Sindhi/sd_in | 980 | 50 | 3 | 93 | 834 |
| Pashto/ps_af | 512 | 50 | 2 | 50 | 410 |
| Total | 2,438 | 200 | 5 | 210 | 2,023 |

Measured conflicting-reference groups, missing/invalid references and empty scoring
references: **0**. Subset/duplicate-reading exclusions are selection outcomes, not defects
or quarantined human labels. Five out-of-duration recordings are excluded by the preregistered
data-only rule. Filename, not repeated sentence ID, identifies a recorded utterance.
Selection is fixed seeded SHA-256 order, one recording per distinct sentence ID/language.
It is not model-output, length, gender, ranking or accuracy driven. A selected audio failure
blocks preparation without substitution.

Canonical references preserve exact published `raw_transcription`; published normalized
transcription is separate lineage. These are human-authored corpus read-script references,
not newly verified verbatim audio annotations. Collective publisher provenance is explicit;
no individual author/speaker identity is invented. Reuse permission denotes the published
license, not newly claimed participant consent. No software/LLM generates speech or references.

## Implementation and integrity boundary

Isolated `sahulat_voice.benchmark`: strict source locks, bounded pinned public acquisition,
metadata selection/audit, safe streamed tar reading, offline PCM16 conversion, immutable file
installation, protocol registration and external corpus freeze/verification. The thin script
does not modify shared package entry points, requirements, text contracts or migrations.

The offline adapter accepts verified mono 16 kHz PCM16/PCM32/IEEE float32 originals only.
Quantization uses float64 scaling, nearest ties-to-even rounding, explicit clipping accounting
and little-endian PCM16 output. No resampling, downmixing, denoising, trimming, VAD or model
preprocessing is introduced. The runtime continues rejecting floats/PCM32 and requiring its
existing bounded PCM16 WAV format. Originals, prepared bytes, references, rows and tar members
remain auditable. Verification replays source selection and conversion byte-for-byte.

Canonical JSON is compact sorted-key UTF-8 with one LF; samples sort by `sample_id`.
Canonical runtime: Python 3.12 / Unicode 15.0.0 / NumPy 2.2.6. Hashes exclude timestamps,
machine paths, signed download URLs, secrets and variable measurements. Exact key/file
allowlists reject extra results/retrieval fields and files. Source/protocol/code drift,
tampered originals/prepared audio/references/metadata/manifests and external registries fail
closed. Different existing artifacts cannot be overwritten; unchanged runs are no-ops.

All four languages are built before derived installation. Partial I/O failure cannot create
a verified external FROZEN corpus descriptor. The complete selected bundle is self-contained
for verification without redistributing/downloading all four source archives again.
Primary WER/CER normalization, denominators, failure handling and future latency/uncertainty
policy are preregistered, not executed or tuned. Strict foundation diagnostics stay unchanged.
MMS/FLEURS training-domain exposure and general read-speech limitations are explicit; this is
not commerce-domain validation, an identical zero-shot comparison or leaderboard reproduction.

## Executed verification

| Check | Result |
| --- | --- |
| Full repository suite with `RUN_DATABASE_TESTS=1` | **756 passed, 4 skipped**, 376.79 s |
| New benchmark tests (subset of total) | **84 passed** in the full suite |
| Database-marked regression tests (subset of total) | **91 passed** |
| Skips | 2 pretrained visual + 2 opt-in STT model tests |
| Ruff lint | PASS |
| Ruff formatting | PASS, 157 Python files |
| Existing configured mypy | PASS, 72 files |
| Voice + isolated integration mypy | PASS, 28 files |
| Dependency validation (`pip check`) | PASS, no new dependencies |
| Frozen text-query tooling verification | GREEN, unchanged snapshot |
| Cached OpenCLIP / HTTP / bridge / scoped DB smoke | GREEN: 5 resolved products, ranking preserved, 0 catalog writes |
| Actual FLEURS preparation/freeze and byte determinism | PENDING acquisition |

Machine-readable validation evidence: `artifacts/voice_evaluation_v1_validation.json`.
Actual prepared/frozen recording count: **0**. No actual dataset manifest, semantic checksum
or external FROZEN corpus descriptor exists. The 200 count above is verified **metadata
selection**, not a claim that 200 prepared recordings already exist. Synthetic round trips
prove tooling determinism, not actual FLEURS audio parity or artifact determinism.

Large-file acquisition did not complete. Initial streaming transfers were stopped after
prolonged slow progress; sanitized `io_failed` output alone does not establish their precise
underlying transport error. An approved retry and a separate installed Hugging Face Hub
0.36.2 downloader attempt did not yield complete archives; the latter returned FAILED without
any STT call. No new downloader dependency was installed. All four pinned public asset HEAD
requests return HTTP 200, but this is **not** full-file/checksum verification. Reliable complete
transfer remains an operational dependency; the exact Hub transfer failure is not established
from the intentionally URL-free error output. No source switch, conversion fallback or
protocol amendment was made. Acquisition processes have exited; no hidden transfer runs remain.
One canceled non-resumable `.download` temporary file was removed after validating its exact
pinned workspace-cache scope; published source data can be downloaded again. Hub resumable
partials were retained. No verified source asset, application file or business data was removed.

Two existing dependency deprecation warnings remain (Starlette/httpx and AnyIO portal alias);
dependencies/tests were not weakened or upgraded. The initial targeted run exposed two test
construction errors (nonexistent `.frames` property and missing error-code argument), both
corrected; the final full suite passes. Synthetic fixtures are strictly conversion/validation/
freeze test data, never actual FLEURS benchmark evidence. No synthetic benchmark is frozen.

```powershell
python scripts/prepare_voice_evaluation.py preregister
python scripts/prepare_voice_evaluation.py verify-protocol
python scripts/prepare_voice_evaluation.py acquire --allow-download
python scripts/prepare_voice_evaluation.py prepare
python scripts/prepare_voice_evaluation.py freeze
python scripts/prepare_voice_evaluation.py verify
$env:RUN_DATABASE_TESTS='1'
$env:HF_HUB_OFFLINE='1'
python -m pytest -q --tb=short
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m mypy src/sahulat_voice integration
python -m pip check
python scripts/freeze_text_query_tooling.py --verify-only
```

## Complete file inventory for this gate

Added source/config/documentation:

```text
src/sahulat_voice/benchmark/__init__.py
src/sahulat_voice/benchmark/audio.py
src/sahulat_voice/benchmark/cli.py
src/sahulat_voice/benchmark/dataset.py
src/sahulat_voice/benchmark/io.py
src/sahulat_voice/benchmark/metadata.py
src/sahulat_voice/benchmark/protocol.py
src/sahulat_voice/benchmark/source.py
scripts/prepare_voice_evaluation.py
tests/voice/test_benchmark_audio.py
tests/voice/test_benchmark_metadata.py
tests/voice/test_benchmark_freeze.py
configs/eval_voice_v1.json
configs/fleurs_sources_v1.json
docs/EVAL-VOICE-V1.md
reports/voice_eval_v1_preparation.md
```

Generated external registry: `configs/gates/eval_voice_v1_protocol.json`.
Generated validation evidence: `artifacts/voice_evaluation_v1_validation.json` (outside the
future frozen bundle; explicitly records RED/PENDING and contains no fabricated samples).
Expected after successful preparation: `configs/corpora/fleurs_voice_v1.json`,
`artifacts/voice_evaluation_v1/manifest.json`, `evaluation-input.json`, `lineage.json`,
`metadata-audit.json`, `ATTRIBUTION.md`, 5 pinned card/TSV copies, 200 original WAVs,
200 prepared WAVs. No secrets appear in these generated artifacts. Large cache/derived
bundles stay ignored by repository conventions; distribute with the registries/attribution.

Modified: `README.md`, `docs/architecture/repository-structure.md`,
`docs/VOICE-STT-FOUNDATION-V1.md` (documentation links/status only).

## Blockers and stop boundary

Actual audio acquisition/preparation/parity must complete before the FLEURS dataset is GREEN.
Missing files are exactly `data/en_us/audio/test.tar.gz`, `data/ur_pk/audio/test.tar.gz`,
`data/sd_in/audio/test.tar.gz`, `data/ps_af/audio/test.tar.gz` under the pinned revision cache.
Resume or supply these exact checksum-pinned assets using the approved source; then run
`prepare`, `freeze`, `verify`, and repeat preparation/verification to establish actual byte
determinism. Do not loosen source checks or freeze an empty/synthetic substitute. Preparation
and freeze were both executed against the incomplete cache and correctly refused without
creating a canonical bundle or FROZEN descriptor. Source metadata/card remain verified.
Real Whisper/MMS weights/inference, accuracy/latency evaluation and any voice runtime endpoint
remain later explicitly authorized work. FLEURS test provenance does not prove speaker-disjoint
or commerce-query performance. FLEURS locales are US English, Pakistani Urdu, Indian Sindhi
and Afghan Pashto; results will not establish coverage of all Pakistani accents. Human
text-query data remains PENDING in its independent stream.

No Search/FTS/tsvector/BM25/embeddings/vector store/RRF, voice-to-search, new API endpoint,
judgments, adjudication, text-labeling data, IAM/authentication, Commerce, frontend, RAG,
deployment or teammate-owned modules are implemented/modified. No secret is committed.
Stop at the preregistered source/preparation/freeze gate; neither STT model has run.
