# EVAL-VOICE-CORPORA-V2 — audio acquisition readiness

**Gate: BLOCKED** (target: `AUDIO_ACQUISITION_READY`)

No audio was downloaded, no model was run, and fine-tuning remains unauthorized.

## Record reconciliation

| Population | Count |
| --- | ---: |
| Published UrduSpeech benchmark records | 4,170 |
| Runtime-eligible (<=30s) | 4,079 |
| Duration-ineligible | 91 |
| Deterministic preview selected | 544 |
| Published records outside preview | 3,626 |

The 544-record preview is 200 Standard Urdu + 200 code-switched + all 144
Pakistani-English records. It is a subset of the 4,170-record published inventory.

## Transcript field audit

- Exact matches: 3,791
- Differences: 379
- Format-only: 2
- Human semantic review required: 377
- Confirmed semantic differences: 0 (not inferred automatically)
- Authoritative scoring reference: `PENDING_HUMAN_ADJUDICATION`

| Classification | Count |
| --- | ---: |
| MISSING_OR_ADDED_WORDS | 97 |
| PUNCTUATION_OR_WHITESPACE_ONLY | 2 |
| SCRIPT_PROFILE_CHANGE | 172 |
| SEMANTIC_REVIEW_REQUIRED | 29 |
| SPELLING_OR_TOKEN_SUBSTITUTION | 79 |

Both source fields remain independently hash-addressed with pinned file/line pointers.
Raw transcript text is not copied into this report. Mismatched rows are excluded from
scoring until a human adjudication manifest selects a reference and is frozen.

## Cross-subset speaker labels

- Repeated published identifiers: 37
- Repeated identifiers in the 544-record preview: 37
- Identity meaning: unverified label, not a verified person
- Reporting rule: keep subsets separate; do not claim pooled speaker independence.

| Subset pair | Shared identifiers |
| --- | ---: |
| code_switched / pakistani_english | 11 |
| standard_urdu / code_switched | 37 |
| standard_urdu / pakistani_english | 11 |

## South Asian English source

- Dataset ID: `cmrt70sar001umm07jwxzhw89`
- Test split: 3,864 clips, 81 speakers, 5.94 hours
- Scope: India, Pakistan, and Sri Lanka; not Pakistan-only
- Split: publisher states speaker-disjoint train/dev/test
- License: CC0-1.0; do not identify speakers or rehost the dataset
- Acquisition: blocked until the selected manifest is frozen

## Rights and checkpoint exposure

| Corpus | License | Local evaluation | Distribution/access limits |
| --- | --- | --- | --- |
| [common_voice_27_sindhi](https://mozilladatacollective.com/datasets/cmu5wbmn400bco107vi2n2yhb) | cc0-1.0 | ALLOWED_BY_STATED_INTENDED_USE | FORBIDDEN |
| [pashto_audio_visual](https://mozilladatacollective.com/datasets/cmuzrhfbd006l07nxoe3inrzq) | cc0-1.0 | PENDING_OWNER_CONSENT_DOCUMENTATION_REVIEW | PENDING_OWNER_CONSENT_DOCUMENTATION_REVIEW |
| sindhi_holdout_v1 | PER_RECORDING_PERMISSION | ALLOWED_ONLY_WITH_RECORDED_SPEAKER_PERMISSION | NOT_AUTHORIZED_WITHOUT_SEPARATE_EXPLICIT_PERMISSION_AND_LICENSE |
| [south_asian_english](https://mozilladatacollective.com/datasets/cmrt70sar001umm07jwxzhw89) | cc0-1.0 | CONDITIONALLY_ALLOWED | REHOSTING_AND_RESHARING_FORBIDDEN |
| [urduspeech](https://huggingface.co/datasets/ASLP-lab/UrduSpeech/tree/16dd380cfd9049a3db7f06a98e878086916bf833) | cc-by-4.0 | PENDING_ORIGINAL_SOURCE_MEDIA_RIGHTS_REVIEW | BLOCKED_PENDING_SOURCE_RIGHTS_REVIEW |

The two Mozilla Common Voice sources prohibit speaker identification and rehosting;
CC0 does not override those publisher restrictions. UrduSpeech source-media rights and
Pashto consent/redistribution review remain open.

All four pinned checkpoint revisions are recorded. Unknown exposure remains `UNKNOWN`;
it is never converted to clear. BuzzASR remains related to Common Voice and its Sindhi
public-corpus results remain reference-only.

## Sindhi holdout protocol

The collection protocol is approved and fail-closed, but data remains `PENDING` at
0/100 recordings and 0/10 speakers. Model evaluation remains `NOT_RUN`.

## Blocking items

- UrduSpeech source-media rights and Pashto consent/redistribution review remain pending.
- Non-identical UrduSpeech transcript fields are not human-adjudicated and are excluded.
- Selected audio evaluation manifests are previews and are not frozen.

The gate may become `AUDIO_ACQUISITION_READY` only when every Boolean criterion in the
JSON gate is true. Until then, do not download audio or execute a model.
