# VOICE-STT-FOUNDATION-V1 validation

Verified on 2026-09-12 in the existing Python 3.12.10 Windows environment.

## Status

| Check | Result |
| --- | --- |
| Audio / adapter / transcript / evaluation-input tooling | GREEN / VERIFIED |
| Overall real STT integration gate | RED / NOT YET VERIFIED |
| Cached Whisper large-v3 real inference | PENDING: pinned weights unavailable |
| Cached MMS real inference | PENDING: pinned base and language weights unavailable |
| Genuine human voice inputs supplied to this workflow | 0 / PENDING |
| Human reference transcripts supplied | 0 / PENDING |
| Multilingual accuracy and real STT latency | NOT MEASURED |
| Voice-to-search / voice HTTP | NOT IMPLEMENTED |

See [the isolated foundation contract](../docs/VOICE-STT-FOUNDATION-V1.md).
No software-generated transcript/reference fixture is represented as human benchmark evidence.

## Implemented scope

Isolated `sahulat_voice`: bounded 16 kHz mono 16-bit PCM WAV validation, explicit English/Urdu/
Sindhi/Pashto selection, lazy pinned offline-default Whisper large-v3 and MMS adapters,
serialized model/language access, conservative NFC/control/whitespace normalization,
immutable raw/normalized transcript with deterministic SHA-256, separate latency observations,
safe failures, minimal module CLI and a neutral multilingual evaluation input/metric scaffold.

No additional dependencies were installed or upgraded. Existing torch 2.10.0+cpu and
Transformers 4.57.6 are reused. CUDA was measured unavailable and is not validated.
Whisper's installed 128-bin feature extractor was executed against synthetic audio without
weights, FFmpeg, SciPy, librosa, torchaudio or soundfile. This is preprocessing proof only.

Public Hub metadata confirmed pinned revisions and MMS safetensors adapters `eng`,
`urd-script_arabic`, `snd`, `pus`. MMS's non-commercial license is an explicit research-use
limitation, not a commercial-model approval. See primary model sources in the contract.

## Safety and deterministic behavior

- Invalid headers/chunks, duplicate data chunks, truncated/oversized/unsupported formats,
  invalid duration/rate/channels/depth/alignment fail before model loading.
- Source audio is bounded, unmodified, memory-only. No shell decoder or URL ingestion exists.
- Same decoder output/provenance produces byte-identical UTF-8 sorted compact JSON + LF and
  transcript checksum. Latency is excluded. Greedy model decoding is not a cross-hardware
  inference determinism guarantee.
- Language is caller-declared, never inferred. Whisper transcribes rather than translates.
  MMS adapter loads keep revision/offline/safetensors options; switching is serialized with
  inference so tokenizer/head state cannot cross requests.
- Unknown/missing language adapter, loading/inference errors, nonfinite MMS logits,
  truncated Whisper decoding, invalid/empty transcript and cancellation fail safely.
  Upstream exception text, paths and stack traces are not exposed.
- Voice input manifests accept only strict fields, human-source attestations, bounded metadata,
  safe relative paths and verified original audio SHA-256. Duplicate IDs/audio/JSON keys,
  unsupported versions and ranking/product fields are rejected.
- Empty evaluation template reports PENDING, sample count 0, all four language counts 0 and
  `evaluation_results=NOT_RUN`. Its canonical **empty-template** checksum is
  `42c215260005a93b0681b1da0971b8f56690d849a0f10c94043b1a0406c16691`;
  this is not a frozen human dataset.
- WER/CER helpers are tested using synthetic strings only. No benchmark runner/results,
  performance threshold, fabricated ground truth, automatic human judgment or query exists.

## Executed verification

| Verification | Measured result |
| --- | --- |
| Full repository suite, `RUN_DATABASE_TESTS=1` | **672 passed, 4 skipped**, 171.69 seconds |
| Voice suite (subset, not additional to total) | **126 passed, 2 skipped**, 16.81 seconds |
| Database-marker coverage in full suite | **91 passed**, all database tests enabled |
| Existing model skips | 2 existing pretrained opt-in tests |
| New speech-model skips | 2 opt-in tests requiring cached weights and explicit human input |
| Ruff lint | PASS |
| Ruff formatting | PASS, 145 Python files |
| Default mypy | PASS, 72 existing source files |
| Standalone voice + existing integration mypy | PASS, 20 files |
| Dependency validation | `pip check` PASS |
| Frozen TEXT-QUERY-V1 tooling snapshot verification | FROZEN / GREEN, unchanged snapshot |
| Real offline Whisper/MMS loading attempt | Both safely return `model_unavailable` |
| Cached OpenCLIP → loopback API → bridge → scoped DB | **PASS**, 5 canonical products |
| Visual ranking/order/scores | Preserved by existing smoke assertions |
| Visual bridge catalog writes | **0** |

Two unchanged upstream deprecation warnings remain in existing Starlette/httpx/AnyIO code.
No existing test was weakened, removed or edited. The full suite includes database security,
fixture ingestion, product documents, frozen protocols, visual API and bridge regressions.

Commands:

```powershell
$env:RUN_DATABASE_TESTS='1'
python -m pytest -q --tb=short
python -m pytest tests/voice -q --tb=short
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m mypy src/sahulat_voice integration
python -m pip check
python scripts/freeze_text_query_tooling.py --verify-only
python -m sahulat_voice.cli capabilities
python -m sahulat_voice.cli validate-evaluation-input `
  --manifest configs/voice_evaluation_input_v1.example.json --audio-root data/voice
```

The existing cached visual smoke was rerun offline using its checksum-locked index and
protected scoped-reader configuration; no credentials or connection values are included here.

## Complete file inventory

Added:

```text
src/sahulat_voice/__init__.py
src/sahulat_voice/errors.py
src/sahulat_voice/contracts.py
src/sahulat_voice/audio.py
src/sahulat_voice/transcript.py
src/sahulat_voice/adapters.py
src/sahulat_voice/service.py
src/sahulat_voice/evaluation.py
src/sahulat_voice/cli.py
tests/voice/__init__.py
tests/voice/conftest.py
tests/voice/test_foundation.py
tests/voice/test_adapters.py
tests/voice/test_evaluation.py
tests/voice/test_model_smoke.py
configs/voice_evaluation_input_v1.example.json
docs/VOICE-STT-FOUNDATION-V1.md
reports/voice_stt_foundation_v1_validation.md
```

Updated:

```text
README.md
docs/architecture/repository-structure.md
```

Only architecture/status documentation is updated outside the isolated speech implementation.
The project manifest's original content was restored when its frozen-snapshot relationship was
identified; no new entry point/extra or dependency/type-scope change remains in `pyproject.toml`.
No existing source/test modules, migrations, text/labeling artifacts, accepted ADRs, requirements
or model/retrieval semantics were changed. This checkout has no Git metadata; no commit was made.

## Blockers and stop boundary

Real speech verification needs the pinned cached Whisper/MMS weights and appropriate MMS
language adapters, plus explicit permissioned human WAV/reference input for the two opt-in
smoke tests. No multi-GB weight download was performed. The documented CLI permits only an
explicit operator download opt-in. Actual model quality, multilingual code-switching,
speaker-separated evaluation, real cold/warm latency, CUDA and deployment resource use remain
unverified. Synchronous calls have no hard inference timeout/preemptive cancellation guarantee.

No text retrieval, FTS, BM25, embeddings/vector infrastructure, Search, human-query collection,
relevance labels, adjudication, authentication, Commerce, frontend, voice-to-search, vendor RAG
or public deployment was implemented. No teammate-owned modules or secrets were modified.
Stop at the isolated voice foundation; do not unblock text retrieval or advance to another gate.
