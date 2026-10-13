# VOICE-STT-FOUNDATION-V1

Status: **TOOLING VERIFIED; REAL-MODEL / HUMAN EVALUATION PENDING**.
End-to-end gate: **RED** until cached real-model smoke verification is possible.
This is Adeel's independent ML workstream, not full voice search or a public service.

## Boundary

```text
Human audio → bounded validation → STT adapter → raw + normalized transcript
                                               → checksum + latency observation
Human references → separate voice input validator → WER/CER scaffold (not run)
```

The isolated `sahulat_voice` package imports no visual, API, database, text, annotation,
or integration packages. No database connection, HTTP endpoint, search call, query artifact,
relevance judgment, domain event or catalog mutation is involved. Bisma/Erum's text contracts,
human-query tooling and FTS/backend-readiness modules are untouched. STT output is never
automatically registered as an EVAL-TEXT-V1 query or benchmark reference.

## Audio ingestion v1

The memory-only service accepts raw bytes, not user-controlled commands, URLs or decoder paths.
Supported input is deliberately narrow: RIFF/WAVE, one PCM format chunk (16-byte `fmt `),
one data chunk, mono, signed 16-bit little-endian, **16,000 Hz**, 0.1–30 seconds inclusive,
at most 2 MiB including headers/metadata. RIFF length, chunk boundaries, byte rate, block
alignment and sample alignment are verified before model loading. Local CLI file reads are
bounded to limit + 1 bytes. Samples are detached float32 buffers in [-1, 1]; source audio
bytes are neither modified nor persisted by the service.

MP3, WebM, Ogg, float/extensible/compressed WAV, other rates/channels/depths, truncated input,
duplicate data chunks and longer recordings fail closed. There is no FFmpeg invocation,
resampling, re-encoding, VAD, denoising, streaming or automatic silence detection in v1.
Adopt a separately versioned audio adapter if browser/mobile recording formats are later
required; don't silently change this preprocessing contract.

## Models and explicit languages

| Adapter | Public repository | Pinned revision | License |
| --- | --- | --- | --- |
| Whisper | `openai/whisper-large-v3` | `06f233fe06e710322aca913c1bc4249a0d71fce1` | Apache-2.0 |
| MMS | `facebook/mms-1b-all` | `3d33597edbdaaba14a8e858e2c8caa76e3cec0cd` | CC-BY-NC-4.0 |

Repository revisions and required MMS safetensors filenames were checked against the public
Hub metadata on 2026-09-12. MMS is a **research alternative, not an approved commercial
deployment dependency**; commercial use needs a compatible license/model decision.
[Whisper model card](https://huggingface.co/openai/whisper-large-v3),
[MMS model card](https://huggingface.co/facebook/mms-1b-all).

| Declared language | Transcript code / Whisper token | MMS adapter |
| --- | --- | --- |
| English | `en` | `eng` |
| Urdu | `ur` | `urd-script_arabic` |
| Sindhi | `sd` | `snd` |
| Pashto | `ps` | `pus` |

These are declared model language paths, **not accuracy guarantees**. Urdu script selection is
explicit, not a translation or transliteration. There is no automatic language detection,
fallback to another language/model or equal-accuracy claim. Low-resource language quality and
code-switching require human evaluation before use. The MMS scripts/codes are listed in its
[supported-language source](https://huggingface.co/facebook/mms-1b-all/raw/main/README.md);
Whisper codes were also verified in the installed Transformers 4.57.6 tokenizer.

`create_adapter(name, settings)` is lazy. Existing pinned ML dependencies are reused without
changing `pyproject.toml` or the frozen text-tooling registry. CPU/float32 is the default;
explicit CUDA fails if unavailable and is not validated in this environment. Downloads are
disabled by default, remote custom code and implicit authenticated Hub credentials are disabled,
and model/adapter weights must use safetensors. Multi-GB weights and several GB of working RAM
are required; neither speech model is currently cached.

Each adapter loads its base model/processor once per instance. Reuse the service inside a
process for warm calls; separate CLI invocations create separate instances. Inference uses
evaluation mode and disabled gradients. Whisper uses caller-declared language, `task=transcribe`,
greedy decoding, one beam, no timestamps and 256 new tokens maximum; reaching the cap without
EOS fails instead of silently publishing a truncated transcript. MMS uses finite-logit CTC
argmax and the corresponding language-specific tokenizer/head. Base load deliberately omits
`target_lang`: installed Transformers' automatic adapter load does not forward our pin/offline
options. Explicit adapter loads carry the same revision, offline mode and safetensors restriction.
Whole transcription calls are serialized within each adapter, including MMS language switches.

## Transcript contract and determinism

`TranscriptionService(adapter).transcribe(payload, language)` produces an immutable result
containing an immutable `Transcript`. The independent pure `build_transcript` contract
does not load models. Required machine record fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | `voice-transcript-v1` |
| `normalization_version` | `voice-nfc-whitespace-v1` |
| `audio_sha256` | SHA-256 of exact original validated WAV bytes |
| `language`, `language_source` | Explicit caller code and `caller_declared`, not detected speech |
| `model` | Name, public repository, full revision |
| `raw_text` | Exact decoder output, retained for provenance |
| `text` | Conservatively normalized output |
| `transcript_checksum` | `sha256:<64 lowercase hex digits>` |

Normalization: NFC, remove non-whitespace Unicode `Cc` controls, trim/collapse whitespace,
preserve case, punctuation, script and meaningful joiners. Reject surrogate code points,
non-strings and raw transcripts longer than 2,048 characters. Empty normalized decoder output
is an explicit error, never `Unknown`/`N/A`. No translation, transliteration, spelling repair,
stemming, keyword generation, query expansion or LLM rewrite occurs. This voice normalization
is separately versioned and does not change ADR-ML-004's product normalization.

Canonical serialization is UTF-8, `ensure_ascii=False`, lexicographically sorted JSON keys,
compact separators, no NaN/Infinity, exactly one LF at EOF. SHA-256 covers this serialization
of every semantic/provenance field above **except the checksum field itself**. Audio identity,
language, model revision, raw and normalized texts participate. Thus equal normalized text with
different raw text intentionally has a different provenance checksum. Runtime, timestamps,
machine paths, latency, retrieval output and connection metadata never participate.

Same input/decoder output produces byte-identical canonical records/checksums. Greedy decoding
reduces variability but **does not guarantee bit-identical STT inference across hardware,
PyTorch kernels, devices or library versions**. No claim of deterministic multilingual accuracy
or model result reproducibility is made without actual evaluation.

Timing observations are separate: audio validation, STT including base/adaptor load and lock
wait, adapter base-load duration, total call duration and audio seconds. Base-load duration is
the adapter's lifetime observation, not a repeated per-request charge. CUDA synchronization
is used when CUDA is explicitly selected. Timings are observational only, no SLO threshold.

## CLI

From the existing installed checkout (Python 3.12, existing `[ml]` dependencies):

```powershell
python -m sahulat_voice.cli capabilities
python -m sahulat_voice.cli validate-evaluation-input `
  --manifest configs/voice_evaluation_input_v1.example.json --audio-root data/voice

# Supply your own real WAV file. Default requires the pinned weights to be cached.
python -m sahulat_voice.cli transcribe --model whisper --language ur `
  --audio data/voice/recording.wav --output artifacts/voice/transcript.json
python -m sahulat_voice.cli transcribe --model mms --language sd `
  --audio data/voice/recording.wav --output artifacts/voice/transcript.json
```

`--allow-download` is a deliberate opt-in for a multi-GB Hub download; it is not used during
validation. The CLI writes the canonical transcript plus `<output>.observation.json` atomically
per file. The observation includes private raw/normalized text, so store it accordingly.
It rejects outputs that overwrite the input audio. Console success contains only status,
checksum, duration and total time, not transcript text or file paths. Voice artifacts are
already protected by the existing ignored `artifacts/` rule.

## Safe failure model

Failures expose fixed typed codes only: invalid/oversized/unsupported audio, unsupported
language, invalid configuration, unavailable model/adapter, failed inference, invalid/empty
transcript, invalid manifest, checksum mismatch, I/O failure, cancellation. Upstream errors,
stack traces and private paths are not returned. Loading failure never publishes half-loaded
model/processor state; failed language switches must reload before reuse. KeyboardInterrupt
at CLI boundaries returns a safe cancellation with exit code 130 and no fabricated result.

This synchronous CLI/library has no public HTTP surface and no hard inference timeout or
preemptive cancellation guarantee. A future bounded worker/runtime gate must define that
operational policy before service exposure. Silence/noise may cause model hallucinations:
input validation is not proof of speech and normalized output is not proof of correctness.

## Multilingual evaluation scaffold (no evaluation dataset/result)

`configs/voice_evaluation_input_v1.example.json` is an **empty neutral template**:
`voice-evaluation-input-v1`, `samples=[]`, data PENDING. No recordings, references or benchmark
rows are fabricated. At most 200 samples / 1 MiB manifest are accepted in this initial scaffold;
there is no prescribed benchmark count, split or acceptance threshold.

Each future human-supplied sample must contain exactly:

| Field | Validation |
| --- | --- |
| `sample_id` | Unique non-empty ASCII letters/digits/underscore/hyphen, at most 128 |
| `language` | One of `en`, `ur`, `sd`, `ps` |
| `audio_path` | Canonical relative POSIX WAV path under the supplied audio root; no escape/absolute/ADS path |
| `audio_sha256` | Exact original WAV checksum, verified before inference |
| `reference_text` | Genuine human reference, preserved exactly; usable under voice normalization |
| `reference_author` | Human pseudonym/provenance, non-empty, at most 128 |
| `reference_source` | Literal `human` |
| `source` | `human_recording` or `licensed_dataset`, never synthetic/LLM benchmark data |
| `use_permission_confirmed` | Boolean `true` (human attestation; software cannot independently prove consent) |

Extra fields, rankings/scores/product identities, duplicate JSON keys, duplicate IDs/audio
checksums, invalid versions/metadata, malformed audio and checksum drift are rejected. Samples
are Unicode-sorted by `sample_id`; canonical manifest checksum ignores JSON formatting/input
list order but preserves original reference text. Validator output counts all four languages
and explicitly says `NOT_RUN`; empty input never becomes a benchmark GREEN result.

`transcript_error_counts(reference, hypothesis)` is an independently tested WER/CER scaffold:
both strings use the voice normalization; case/punctuation remain, words are whitespace-split,
CER includes normalized spaces, edit distance / human-reference denominator, rates not clamped.
Empty reference fails; empty hypothesis counts all reference units as errors. **No runner or
benchmark results are produced**. Before claims, separately freeze licensed human recordings,
speaker separation/provenance, human references, scoring policy and multilingual protocol.
This is not EVAL-TEXT-V1 and does not touch its annotation contract.

## Verification and next boundary

Synthetic audio and backend doubles test safety, wiring, language mapping and determinism only.
The installed Whisper feature extractor is exercised without weights or extra audio decoders.
Opt-in cached model tests require explicit real human manifest/root and no implicit download:

```powershell
$env:RUN_VOICE_MODEL_TESTS='1'
$env:VOICE_SMOKE_MANIFEST='data/voice/human-input.json'
$env:VOICE_SMOKE_AUDIO_ROOT='data/voice'
python -m pytest tests/voice/test_model_smoke.py -q
```

Real STT/model latency and accuracy remain unverified until these tests can run on supplied
human inputs. Visual ranking, frozen product corpus, query freeze, PostgreSQL FTS and team
labeling are independent and unchanged. Stop at speech foundation; voice-to-search integration,
HTTP STT serving, vendor RAG, Commerce and deployment require later explicit gates.

The subsequent [EVAL-VOICE-V1](EVAL-VOICE-V1.md) gate supplies a separate, licensed FLEURS
four-language test subset and freezes offline preparation/scoring policy before model execution.
Its primary scoring view is explicitly separate from the strict diagnostic helper above.
Dataset preparation preserves this foundation's input/transcript contracts and does not establish
real STT accuracy or latency; see [preparation validation](../reports/voice_eval_v1_preparation.md).
