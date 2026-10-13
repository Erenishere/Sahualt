# EVAL-VOICE-CORPORA-V2 source audit

| Field | Status |
| --- | --- |
| Metadata audit | METADATA_AUDIT_COMPLETE |
| Audio dataset | NOT_FROZEN |
| Media acquisition | BLOCKED_SOURCE_RIGHTS_AND_QUALITY_GATES |
| Model results | NOT_RUN |

## UrduSpeech pinned inventory

- Revision: `16dd380cfd9049a3db7f06a98e878086916bf833`
- Files: 4,288
- Audio files: 4,170
- Metadata files: 118
- Total bytes: 3,561,652,930
- Published records: 4,170
- Published `Transcription`/`ground_truth` mismatches: 379
- Exact duplicate-audio groups: 0
- Cross-subset speaker identifiers (identity unverified): 37

| Subset | Published records | <=30s eligible | Preview selected | Target |
| --- | ---: | ---: | ---: | ---: |
| standard_urdu | 2173 | 2160 | 200 | 200 |
| code_switched | 1853 | 1775 | 200 | 200 |
| pakistani_english | 144 | 144 | 144 | 200 |

Selections are deterministic previews only. No audio was downloaded, no transcript was
accepted as human-verified through listening, and no dataset or model result was frozen.
Cross-subset speaker labels are identifiers only; they are not treated as verified
people.

## Other source decisions

- Common Voice 27 Sindhi: `REFERENCE_ONLY`; 42 test clips; overlap audit pending.
- Pashto Audio-Visual Corpus: `QUARANTINED_AUDIT_ONLY`; rights and listening
  review pending.
- South Asian English: `SOURCE_ID_PENDING`; claimed counts are not frozen evidence.
- SINDHI-HOLDOUT-V1: `PENDING`; 0/100 fresh recordings; model evaluation `NOT_RUN`.

## Stop condition

Resolve source-media rights, conduct transcript listening review, audit checkpoint overlap, and freeze verified audio before model execution.
