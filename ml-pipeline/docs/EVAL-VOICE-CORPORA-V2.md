# EVAL-VOICE-CORPORA-V2 — dataset expansion gate

This protocol audits new public speech sources for the existing Sahulat AI ASR
baselines. It does not select or fine-tune models. It is isolated from the frozen
`EVAL-VOICE-V1`, `EVAL-VOICE-ALT-V2`, and Sindhi reference-only artifacts.

## Current boundary

The first gate is metadata-only. It pins the UrduSpeech repository revision,
verifies the complete benchmark file inventory, downloads only published JSONL
metadata, verifies Git blob identities, and produces deterministic sample previews.
It does not download speech audio or execute a model.

Audio acquisition remains blocked until all of these are resolved:

1. Source-media rights are reviewed separately from the dataset card's declared license.
2. A human listening sample confirms transcript/audio quality.
3. Exact-audio and speaker-overlap findings are reviewed.
4. Model-training overlap is recorded for every evaluated checkpoint.
5. The source audio conversion and immutable evaluation-manifest protocol is frozen.

## Source classifications

| Source | Classification | Use |
| --- | --- | --- |
| UrduSpeech benchmark | `NOT_VERIFIED` | Metadata audit and selection preview only |
| Common Voice 27 Sindhi | `REFERENCE_ONLY` | Supplementary reporting; never independent selection evidence |
| Pashto Audio-Visual Corpus | `QUARANTINED_AUDIT_ONLY` | Await rights, consent, listening and demographic review |
| South Asian English | `SOURCE_ID_PENDING` | Claimed counts are not evidence until source metadata is pinned |
| SINDHI-HOLDOUT-V1 | `PENDING` | Required fresh-human independent Sindhi gate |

UrduSpeech's three published benchmark directories are Standard Urdu,
Urdu-English code-switching, and Pakistani-accented English. Selection previews
balance duration group, category and published speaker identifier, then use a
seeded SHA-256 order. A published speaker label is not interpreted as a verified
person across subsets. Samples longer than the existing 30-second runtime limit
are excluded from preview selection. Exact duplicate-audio hashes are also
excluded and reported.

The Pakistani-English subset contains fewer than 200 published audio files, so
its 200-record goal is a ceiling, not a promised sample count. Standard Urdu and
code-switching each require 200 eligible records before the later audio gate can
proceed.

## Commands

```powershell
python scripts/prepare_voice_corpora_v2.py preregister
python scripts/prepare_voice_corpora_v2.py verify-protocol
python scripts/prepare_voice_corpora_v2.py audit --allow-network
python scripts/prepare_voice_corpora_v2.py verify-audit
python scripts/prepare_voice_corpora_v2.py status
```

`audit --allow-network` reads the pinned Hugging Face API revision and only the
small `clean_transcription.jsonl` files. It writes checksum-anchored JSON and
Markdown reports. Re-running never overwrites different evidence.

## Stop condition

Stop after the metadata audit. Do not download evaluation audio, run Whisper,
MMS, Ghag, BuzzASR, or any alternative checkpoint, modify decoding or scoring,
fine-tune, select a production model, or combine these future scores with the
frozen FLEURS evidence.
