# EVAL-VOICE-CORPORA-V2 manifest selection and exclusion report

**Metadata manifest status:** `FROZEN_METADATA_ONLY_AUDIO_NOT_ACQUIRED`

No audio was downloaded; no ASR model was executed or fine-tuned.
Publisher audio SHA-256 values are inventory metadata and were not locally rehashed.
Speaker labels are retained as published identifiers, not treated as verified people.

## Reconciliation and selected counts

- Full pinned UrduSpeech benchmark inventory: 4,170 records.
- Previously audited preview count: 544 (200 + 200 + 144).
- Exact `Transcription`/`ground_truth` matches: 3,791.
- Mismatched transcript rows excluded: 379.
- Duplicate publisher audio-hash groups: 0.

| Subset | Published | Eligible | Selected | Target | Target met | Excluded |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| standard_urdu | 2,173 | 1,977 | 200 | 200 | yes | 1,973 |
| code_switched | 1,853 | 1,597 | 200 | 200 | yes | 1,653 |
| pakistani_english | 144 | 141 | 141 | 200 | no | 3 |

The full record-level decision trail is stored in the three canonical subset ledgers linked
by the frozen registry. Each row records source IDs and pointers, published speaker label,
both transcript-field hashes and lengths, discrepancy classification, decision, and reason.
Mismatched transcript strings are not copied to the exclusion ledgers and are not resolved
automatically. Selected manifests contain both exact-matching source transcript fields.

## Exclusion reasons

- `DURATION_EXCEEDS_PROTOCOL_LIMIT`: 91 record decisions.
- `OUTSIDE_DETERMINISTIC_SAMPLE_TARGET`: 3,174 record decisions.
- `TRANSCRIPT_MISMATCH_UNADJUDICATED`: 379 record decisions.

## Source rights and acquisition gate

Source rights records are copied from the pinned acquisition-readiness report without
reinterpreting or upgrading their status. The UrduSpeech rights review and evaluation
independence remain unresolved. Metadata-manifest freeze is not audio-acquisition approval.
The acquisition gate remains BLOCKED for every current source.

## Remaining source coverage

South Asian English, Pashto, Common Voice Sindhi, and the fresh Sindhi holdout have no
frozen selected metadata manifest in this bundle. Their authoritative source and rights
statuses remain in the gate; acquisition remains rejected until their source-specific
metadata, permissions, revisions, and independent-sample gates are resolved.
