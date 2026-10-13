# EVAL-VOICE-ALT-V1 — specialist checkpoint evaluation

This is Adeel's offline speech workstream, not a production selection ADR or a change to
EVAL-VOICE-V1. Preregister this document, candidate identities and implementation hashes
before any candidate inference. The prerequisite corpus and historical results stay immutable.

## Fixed inputs and identities

Use the fully verified FLEURS-VOICE-V1 bundle, manifest SHA-256
`e2efd78d0af8fe8ecc2c6483ab7db0ff9dba6763fd148be58bbc6c4fd05499e4`.
Select the existing 50 Pashto records by declared language only, with no reselection or repairs.
All 200 records and source/conversion/reference/lineage hashes are verified before execution.
Candidate identities, licenses, official README Git identities and weight SHA-256 values are
locked in `configs/voice_alt_v1_models.json`. Official metadata and pinned README copies are
retained separately from weights in the acquisition evidence. Apache-2.0/MIT declarations
are not a legal clearance of all training material. No floating revisions or remote custom code.

Pashto candidate: [Pashto Ghag](https://huggingface.co/Nasimbahar/pashto-ghag-whisper-medium-asr/blob/ed20e00d47d0852ed24f07b4370c0bdac2e5f241/README.md),
revision `ed20e00d47d0852ed24f07b4370c0bdac2e5f241`, Apache-2.0, Whisper-medium;
publisher declares Common Voice 17 Pashto training, not FLEURS. This is a different declared
fine-tuning domain. However, a model card is not a complete training manifest or a verified
exclusion attestation; underlying Whisper pretraining overlap is also unknown. Until stronger
provenance exists, classify this run **INDEPENDENCE_NOT_VERIFIED**,
`evaluation_independence=false`, not a proven CLEAN independent holdout. Scores can be compared
as released-checkpoint observations, with this qualification, not used to choose a winner.
Published model-card scores are not Sahulat measurements.

Sindhi candidate: [BuzzASR](https://huggingface.co/BuzzASR/sindhi/blob/8e85f09a5c0b17c635ffa8fd124b1efa56fcb5c7/README.md),
revision `8e85f09a5c0b17c635ffa8fd124b1efa56fcb5c7`, MIT, Whisper-large-v3;
publisher explicitly declares FLEURS, Common Voice 25 and text-only Goldfish training.
Any FLEURS result is **CONTAMINATED / REFERENCE-ONLY**, `evaluation_independence=false`,
`reason="model training includes FLEURS"`. This gate acquires the checkpoint and tests its
adapter boundary synthetically but does **not** perform the optional contaminated inference.
It does not mix a Sindhi reference score with independent model-selection evidence.

## Execution fixed before results

Pashto only, fresh process, CPU/float32, eight intra-op and eight inter-op Torch threads,
local verified safetensors, no downloads during loading/inference, no revision fallback.
Use the existing STT interface and inherited Whisper greedy decoding: declared `ps`,
task transcribe, `do_sample=false`, one beam, maximum 256 new tokens, no timestamps.
No prompts, repetition penalties, beam tuning, transcript correction or new normalization.
Retain published checkpoint generation defaults except these existing explicit runtime arguments.

Pashto Ghag exports Transformers 5's embedded feature-extractor layout. With frozen
Transformers 4.57.6, construct the standard WhisperFeatureExtractor from the exact published
`processor_config.json` and the standard tokenizer from the same pinned snapshot. This is
configuration-layout compatibility, not a second audio pipeline, resampling or asset rewrite.
No dependency upgrade or borrowed processor from another model. BuzzASR uses its own tokenizer;
its model-card suggested repetition penalties are deliberately not adopted.

One unscored warmup on the same first-selected Pashto sample under EVAL-VOICE-V1's frozen
seeded key; then exactly one scored call per sample in lexical `sample_id` order. All 50
samples, including failures, stay in the evidence. No inference retries or checkpoint resume.
Existing execution markers/results reject a repeated run; `verify` never creates a model.
Network-only bounded retries during acquisition are not inference retries.

Raw decoder output, unchanged normalized transcript and checksum, typed failures and timing
are retained using the existing service/capture/sample-call boundary. Primary scoring reuses
the frozen `voice-asr-scoring-v1` implementation: per-language micro WER/CER over all references;
failed inference scores complete reference deletions, not fabricated decoder text. CER counts
normalized Unicode codepoints including spaces. No clipping or new aggregate: only Pashto
micro scores are reported for this one-language run. No confidence intervals or pass thresholds.

Warm STT mean/median/p95 and RTF include every attempted scored call, including failures;
exclude warmup and cold loading. Null unattempted timings are not zero. Preserve all timing
outliers. Historical Whisper/MMS timing was non-isolated and contains operational stalls;
do not rerun, filter or recompute their recorded summaries to match this run's environment.

## Immutable evidence

`artifacts/eval_voice_alt_v1/` contains official metadata/README copies, acquired asset hashes,
preregistration copy, an exclusive execution marker, 50 scored-call checkpoints, Pashto result
and validation manifest. Canonical JSON uses existing UTF-8, sorted keys, compact separators,
finite numbers and one final LF. Semantic hashes exclude timing, never transcript identity.
Record CPU/dependency information and implementation hashes. Do not promise bit-identical
neural inference across hardware. External protocol/result registries anchor the bundle hashes.
The original results and original protocol/corpus are checked before and after execution.

## SINDHI-HOLDOUT-V1: data collection tooling only

Only fresh genuine human Sindhi speech and human references may populate this distinct dataset.
No TTS, ASR labels, LLM text, suggested utterance contents or artificial benchmark examples.
The input schema records speaker pseudonym, recording ID, relative audio path, original and
canonical audio SHA-256 (identical here: already-canonical mono PCM16/16 kHz WAV), exact human
reference, reference author/provenance, UTC recording date, consent/use-permission confirmation,
`language=sd`, `source=human_recording`, and collection/not-used-for-training attestations.
Human attestations are provenance, not automatic proof of independence or a language detector.
No runtime conversion, semantic rewriting or inferred metadata is permitted.

Reject duplicate IDs/audio, malformed/empty references, unsafe paths, noncanonical audio,
missing consent/provenance and speakers listed in any supplied training/adaptation speaker
exclusion set. Record that exclusion set with the manifest; new train/adaptation data must
respect this held-out speaker registry. Multiple evaluation recordings per speaker are allowed,
not claimed statistically independent speakers. Speaker IDs must not contain real contact data.

Empty input validates as PENDING and cannot freeze. A nonempty valid set can be frozen with
its declared count, deterministic recording order, indexed bytes and external checksum registry.
Freeze is a data-integrity operation, **not** automatic scientific adequacy or approval to score
or select models. No sample minimum, strata, model-selection rule or threshold is invented here;
a separate human-approved follow-up evaluation protocol is required before independent scoring.
No actual fresh holdout was supplied at preregistration; dataset PENDING, selection BLOCKED.

## Commands and stopping boundary

```powershell
python scripts/acquire_voice_alt_models_v1.py --allow-download --workers 8
python scripts/run_voice_alt_v1.py preregister
python scripts/run_voice_alt_v1.py run
python scripts/run_voice_alt_v1.py verify
python scripts/sindhi_holdout_v1.py validate --input <human-input.json> --audio-root <recordings>
python scripts/sindhi_holdout_v1.py freeze --input <human-input.json> --audio-root <recordings>
python scripts/sindhi_holdout_v1.py verify
```

No router, deployment, production winner, fine-tuning, HTTP STT, search integration, text/FTS,
Commerce, frontend, authentication or teammate-owned labeling/backend modules. Stop after
candidate observations, provenance verification and human holdout tooling.
