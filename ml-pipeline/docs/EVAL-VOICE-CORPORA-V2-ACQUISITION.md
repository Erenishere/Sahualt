# EVAL-VOICE-CORPORA-V2 — audio acquisition readiness

This is an amendment to the completed metadata audit, not a new experiment. It
preserves the frozen V2 protocol and audit artifacts, pins the additional South
Asian English source, and evaluates whether selected audio may be acquired. It
does not download audio, execute a checkpoint, change decoding, or authorize
fine-tuning.

## Source and rights decisions

The South Asian English source is Mozilla Data Collective dataset
`cmrt70sar001umm07jwxzhw89`, derived from Common Voice Scripted Speech 26.0
English release `cv-corpus-26.0-2026-06-12`. Its test split has 3,864 clips from
81 speakers (5.94 hours), and the publisher states that train/dev/test are
speaker-disjoint. The accent tag combines India, Pakistan, and Sri Lanka, so it
must not be presented as a Pakistan-only benchmark. The declared license is
CC0-1.0. Local evaluation must retain the publisher restrictions against speaker
identification and dataset rehosting.

UrduSpeech remains blocked because the dataset card's CC BY 4.0 declaration does
not finish the source-media rights review for published YouTube and Pakistan
Television material. Its dataset-level attribution requirement is recorded, but
local audio evaluation and media redistribution remain blocked pending review.
The Pashto Audio-Visual Corpus page states CC0-1.0 and public download; local use
and media redistribution remain blocked because the same page says consent and
redistribution documentation still awaits owner review. Common Voice 27 Sindhi
remains reference-only: Mozilla lists CC0-1.0 and intended ASR evaluation use,
while forbidding speaker identification and rehosting or resharing. Fresh
Sindhi recordings require per-speaker evaluation permission; public distribution
requires separate explicit permission and a license. These are recorded source
terms and project controls, not legal advice.

## Transcript difference policy

The pinned UrduSpeech metadata contains both `Transcription` and `ground_truth`.
Neither is silently promoted to the authoritative scoring reference. Every
non-identical pair is classified deterministically as Unicode-only,
punctuation/whitespace-only, script-profile change, missing/added words,
spelling/token substitution, or semantic-review-required. Semantic meaning is a
human decision and is never inferred by the classifier.

The report preserves independent SHA-256 identities, character/token lengths,
and the pinned source file/line pointer for both fields without copying raw text.
Until human adjudication freezes a reference decision, every mismatched row is
excluded from scoring and from an acquisition-ready selected manifest.

## Speaker and checkpoint overlap

Cross-subset `Speaker_id` values are published labels, not verified people. The
report records hashed labels, subset membership, record counts, and preview
selection counts. Subsets must be reported separately. Pooled confidence or
speaker-independence claims are prohibited unless publisher namespace semantics
are resolved; verified same-person overlaps must then be grouped or excluded.

Every repository checkpoint and revision already present in the project is
listed with known training declarations. Missing evidence is `UNKNOWN`, never
clear. BuzzASR's FLEURS/Common Voice exposure keeps public Sindhi results
reference-only. Ghag's declared Common Voice 17 Pashto use and incomplete base
model evidence prevent an independence claim.

## Sindhi holdout protocol

The approved collection design requires 50 human-authored Perso-Arabic Sindhi
utterances (30 commerce and 20 everyday), 100 fresh recordings, and ten
pseudonymous speakers. Two speakers record each utterance and each speaker makes
ten recordings. Consent, local evaluation permission, public-corpus
attestations, a second human transcript reviewer, and canonical 16 kHz mono
PCM16 WAV are mandatory. FLEURS, Common Voice, synthetic/TTS,
translated-benchmark, and model-generated sources are rejected.

Protocol approval does not imply that data exists. The holdout remains
`PENDING`, 0/100 recordings, 0/10 speakers, with model evaluation `NOT_RUN`.

## Commands

```powershell
python scripts/prepare_voice_corpora_v2_readiness.py preregister
python scripts/prepare_voice_corpora_v2_readiness.py verify-protocol
python scripts/prepare_voice_corpora_v2_readiness.py audit --allow-network
python scripts/prepare_voice_corpora_v2_readiness.py verify-readiness
python scripts/prepare_voice_corpora_v2_readiness.py status
```

The network audit retrieves only the same pinned UrduSpeech repository inventory
and small `clean_transcription.jsonl` metadata files used by the completed source
audit. It never retrieves speech media.

## Gate rule

`AUDIO_ACQUISITION_READY` requires all of the following:

1. Dataset provenance and local-use rights are approved and documented.
2. Transcript differences are human-adjudicated or excluded in a frozen selected manifest.
3. Speaker-label overlap and known/unknown checkpoint exposure are documented.
4. Selected evaluation manifests are immutable and checksum-anchored.
5. The independent Sindhi collection protocol is approved.

Any false criterion keeps the gate `BLOCKED`. Do not download audio or run a
model while blocked.
