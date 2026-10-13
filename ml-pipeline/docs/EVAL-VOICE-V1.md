# EVAL-VOICE-V1 — FLEURS multilingual STT preregistration

Protocol version: **EVAL-VOICE-V1**. Dataset identity: **FLEURS-VOICE-V1**.
Protocol/config/source/code are frozen by `preregister` before acquisition and before any
Whisper/MMS execution. Dataset preparation is a separate gate: PREPARED is not FROZEN;
the external corpus registry and full verification must pass before evaluation.

## Purpose and scope

Compare released Whisper large-v3 and MMS-1B-All on the **same 200 prepared test recordings**:
50 English (`en_us`), 50 Urdu (`ur_pk`), 50 Sindhi (`sd_in`), 50 Pashto (`ps_af`).
Only protocol and deterministic source acquisition/preparation/freeze are implemented here.
No STT model, evaluation runner, accuracy result, latency benchmark, search or text-query stage
is executed. This belongs to Adeel's independent ML workstream, not team text labeling/FTS.

Primary source: [Google FLEURS](https://huggingface.co/datasets/google/fleurs),
pinned Hub revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`.
The [dataset card](https://huggingface.co/datasets/google/fleurs/blob/main/README.md) declares
16 kHz audio and CC BY 4.0. Actual paths/bytes/checksums, not approximate card counts, are
locked in `configs/fleurs_sources_v1.json`. Full test-archive SHA-256 is the pinned Hub LFS
object identity; metadata/card hashes were measured on the pinned source.

| Language | Config | Measured TSV rows | Compressed test archive bytes |
| --- | --- | ---: | ---: |
| English | `en_us` | 647 | 289,851,356 |
| Urdu | `ur_pk` | 299 | 149,549,883 |
| Sindhi | `sd_in` | 980 | 621,842,598 |
| Pashto | `ps_af` | 512 | 303,903,990 |

Only test TSVs and test archives are acquired. No train/dev audio, Common Voice, own recordings
or model weights are fetched. The public source packages audio in gzip tar containers, so
acquisition reads approximately **1.37 GB** of test archives, not just 200 individual HTTP WAVs.
Only the selected 200 originals and 200 prepared WAVs enter the reproducibility bundle.

## Selection locked before model execution

Seven headerless UTF-8 tab-separated fields: sentence ID, WAV filename, `raw_transcription`,
published `transcription`, character transcription, declared audio frames, gender. Quotes
remain literal (`QUOTE_NONE`); no semantic repair or source modification occurs.

FLEURS sentence IDs repeat across independently recorded readings; **filename is utterance
identity**. Structural corruption, duplicate filenames and malformed TSV fail closed. Missing/
unusable reference or declared duration outside 1,600–480,000 frames is a documented data-only
exclusion. A reference empty after scoring normalization is also excluded. Sentence groups
with different exact published raw references are quarantined as entire groups.

Within each language, sort eligible recordings by the tuple:

```text
SHA-256(UTF-8("EVAL-VOICE-V1|20260912|<config>|<filename>")), filename
```

Take the first recording of each previously unselected sentence ID until **50 distinct
sentence IDs** are selected. Repeated readings of selected IDs and records beyond the fixed
subset are explicitly reported; they are not malformed/quarantined data. There is no length,
gender, speaker, recognizer score or accuracy-based ranking. Different languages do not require
the same 50 sentence IDs: this is a balanced corpus-design comparison, not paired translations.
Less than 50 eligible distinct IDs blocks freeze. Selected audio that fails decoding, integrity,
duration or source-frame parity blocks the gate; **no silent replacement** is allowed.

Sample identity: `fleurs_<config>_<source WAV numeric stem>`. Source sentence IDs, TSV row,
filename and original tar member are retained as lineage; no fabricated speaker ID is created.
No known speaker identifier is supplied by these TSVs. Don't claim verified speaker-disjoint
evaluation merely because this is a published test split.

## Reference policy and licensing

Canonical `reference_text` is the **exact published `raw_transcription`**. Keep the dataset's
published `transcription` separately in lineage. These are corpus read-script references,
not newly authored judgments or newly verified verbatim annotations of each audio recording.
Human-authored translations/read scripts may have dataset-provided automated normalization;
do not describe all dataset metadata as purely human-created or infer extra annotations.
No LLM generates, repairs, translates or paraphrases reference text.

The existing voice input contract uses `reference_source=human`,
`source=licensed_dataset`, `reference_author=dataset:google/fleurs-published-reference`.
The author field is explicit **publisher provenance**, not an invented individual annotator.
`use_permission_confirmed=true` refers to the published CC BY 4.0 reuse license, not a new
claim about individual participant consent. Dataset-source checksums and attribution are retained.

Credit Conneau, Ma, Khanuja, Zhang, Axelrod, Dalmia, Riesa, Rivera and Bapna (2022),
[FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech](https://arxiv.org/abs/2205.12446).
Include `ATTRIBUTION.md`, original source URL, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/),
and conversion/subset-change notice with redistribution; imply no endorsement.

## Offline audio preparation (runtime remains unchanged)

`fleurs-pcm16-v1`: verified source RIFF WAV, mono and 16 kHz, PCM16/PCM32/IEEE-float32 only,
bounded to 8 MiB per source file. Check RIFF/chunk/alignment/byte-rate validity, finite float
values, and exact decoded frames against TSV metadata. No resampling, downmixing, trimming,
gain normalization, VAD, denoising, shell decoder or learned preprocessing occurs.

PCM16 samples are retained exactly. PCM32 uses float64 `(signed_int32 / 65536)`; float32 uses
float64 `(source_float32 * 32768)`. Round to nearest ties-to-even with `numpy.rint`, count
quantization clipping, clip to [-32768, 32767], encode signed little-endian int16. Render a
deterministic ordinary RIFF WAV with 16-byte PCM format header; preserve every frame.
Rebuild from original selected WAVs during verification and compare **exact output bytes**.
Record original and prepared SHA-256 and encoding/clipping/frame statistics.

The STT runtime still accepts only mono signed PCM16 WAV at 16 kHz, 0.1–30 seconds, ≤2 MiB.
It does not accept source floats/PCM32 or silently convert them. Both recognizers must receive
the same prepared audio bytes. Source format support must be implementable before registering;
a genuine unsupported source contradiction requires an explicit protocol amendment/version,
not an automatic hidden fallback. Runtime contract/normalization are not reinterpreted.

Canonical environment: Python 3.12 / Unicode 15.0.0 / NumPy 2.2.6. JSON uses existing canonical
UTF-8, sorted keys, compact separators, no NaN/Infinity and exactly one LF at EOF. Sample lists
are sorted lexicographically by `sample_id`. No timestamps, signed download URLs, absolute
machine paths, random IDs, connection information or variable observations enter canonical hashes.

## Scoring preregistration (runner not implemented)

Primary **voice-asr-scoring-v1** is a separate scoring view, not a change to stored transcripts:
voice NFC/control/whitespace normalization, Unicode `casefold`, replace each Unicode `P*`
punctuation character with a space, then collapse/trim whitespace. Preserve letters, digits,
diacritics, script and meaningful joiners; no translation, spelling correction, synonyms,
stemming or language-model rewrite. Apply the same view to both hypotheses and raw references.
This avoids choosing a recognizer based on capitalization/punctuation conventions.

Primary metrics: per-language micro WER (whitespace words, Levenshtein edits / reference words)
and micro CER (Unicode codepoints **including normalized spaces**, edits / reference codepoints).
Rates are not clamped. Report equal-language macro averages of the four per-language micro rates;
never hide language results inside a single overall number. Empty scoring references block data
freeze. Model errors/empty output are explicit failures, counted as complete reference deletions
for primary metrics, with separate failure counts; never drop difficult/failed cases and publish
success-only accuracy. This is scoring of a failure, not a fabricated decoder transcript.
Existing strict scaffold WER/CER may be secondary diagnostics, never mislabeled as primary.

Model differences use matched frozen utterances within each language. If confidence intervals
are reported, use 2,000 paired utterance bootstrap draws with seed 20260912 and 2.5/97.5
percentiles, recomputing micro denominators in each draw. These are not speaker-cluster intervals.
There is no invented accuracy pass threshold, +10% retrieval gate or leaderboard reproduction.

## Future execution policy (not run in this gate)

Pinned Whisper/MMS repositories/revisions are listed in `configs/eval_voice_v1.json` and must
match the existing adapters. Declare language; never fallback or translate. No training/tuning
on these test samples and no post-results changes to selection, references or scoring.
MMS is CC-BY-NC-4.0 and remains a research alternative, not commercial-model approval.
Its [model card](https://huggingface.co/facebook/mms-1b-all) identifies FLEURS as a training/
fine-tuning source: this is released-model test benchmarking, **not proof of unseen-domain or
common zero-shot training conditions**. Whisper training overlap cannot be independently ruled out.

Primary execution is CPU/float32, same prepared waveform and declared language. Record hardware,
versions and decoding options. Use separate fresh-process cold base/adaptor load observations.
For each language/model, one unscored first-selected-sample warmup, then one timed call for
each frozen sample in `sample_id` order. Report per-language mean/median/p95 warm STT ms and
real-time factor; treat adapter switch/load separately from warm STT. Don't mix cold and warm
or CPU and later optional CUDA results; no latency SLO is imposed. Report errors, total sample
denominators, WER/CER normalization and source corpus hashes with every future comparison.

FLEURS is read speech, not Sahulat commerce queries. A later genuine human Sahulat-domain set
must have a separate identity/protocol/report and cannot be blended into these 200-sample scores.
No domain recordings or query strings are generated here.

## Artifacts and commands

```powershell
python scripts/prepare_voice_evaluation.py preregister
python scripts/prepare_voice_evaluation.py verify-protocol
python scripts/prepare_voice_evaluation.py acquire --allow-download
python scripts/prepare_voice_evaluation.py prepare
python scripts/prepare_voice_evaluation.py freeze
python scripts/prepare_voice_evaluation.py verify
```

Acquisition uses a dedicated ignored repository `.cache/voice/fleurs/<revision>` root, SHA/size
checks, bounded streaming and safe progress counts. Different existing source/canonical files
are not overwritten; identical runs are no-ops. No gzip tar member is extracted to a filesystem
path; only bounded selected file bytes are read. Traversal, links, ambiguous selected members,
oversized/expanded archives and missing selected members fail closed.

`artifacts/voice_evaluation_v1/` contains `evaluation-input.json`, `lineage.json`,
`metadata-audit.json`, `manifest.json`, `ATTRIBUTION.md`, pinned TSV/card copies,
200 selected source WAVs and 200 prepared WAVs. Every file is SHA-indexed. All four languages
are fully prepared before installing derived files; a partial I/O failure has no external
FROZEN descriptor and cannot verify as frozen. Re-running safely completes identical files.

`configs/gates/eval_voice_v1_protocol.json` externally anchors the preregistered protocol/source/
code hashes. `configs/corpora/fleurs_voice_v1.json` externally anchors frozen sample counts,
protocol identity, semantic and manifest hashes. Full verification checks these identities,
file allowlist/hashes, exact source TSV subset selection, original-to-PCM16 byte parity, exact
reference text and strict existing voice input schema. Changing any frozen policy/source/data
requires a new version or documented amendment before model evaluation; no replace/reconcile mode.

Stop after protocol/source/subset freeze and regression/static verification. Do not execute
Whisper/MMS, generate STT results, create Search/FTS/vectors, or touch team human text evaluation.
