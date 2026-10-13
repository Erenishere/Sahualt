# EVAL-VOICE-CORPORA-V2 metadata manifest freeze

This phase freezes metadata-only UrduSpeech samples from the source registry's exact pinned
revision. It does not download audio, run ASR, tune models, resolve transcript differences, or
change EVAL-VOICE-V1 evidence or the prior acquisition-readiness rules.

Protocol revision 2 supersedes the initial pre-data preregistration after validation showed that
the pinned source reuses `audio_id` values across distinct rows. The source ID remains unchanged;
the existing path-derived evaluation record ID and metadata line are the unique row pointer. The
amendment does not change sample selection or exclusion policy, and explicitly leaves readiness
rules unchanged. The initial preregistration gate is retained as superseded audit history.

Protocol revision 3 supersedes revision 2 after a dry run exposed a ledger-count field access bug
before any manifest artifacts were written. It fixes only registry serialization metadata; source
IDs, samples, and selection/exclusion decisions are unchanged. Both earlier protocol gates remain
as immutable superseded audit history.

Protocol revision 4 supersedes revision 3 only for verification: the frozen record-level ledgers
are larger than the shared JSON reader's 2 MiB limit. A bounded canonical reader now verifies
them. The manifests, ledgers, and their hashes remain byte-for-byte unchanged from revision 3;
revision 3 remains pinned by the bundle registry as the generation protocol.

## Frozen selection

- Source: `ASLP-lab/UrduSpeech`, revision
  `16dd380cfd9049a3db7f06a98e878086916bf833`.
- Seed: `20261012`; per-subset targets: 200 Standard Urdu, 200 code-switched, and 200
  Pakistani English (the latter is optional and capped by eligible records).
- The existing deterministic stratified selector is applied after excluding all non-identical
  `Transcription`/`ground_truth` pairs, rows longer than 30 seconds, and every row whose publisher
  audio SHA-256 is duplicated anywhere in the pinned benchmark inventory.
- Both transcript source fields are preserved for selected exact-match rows. Every record, including
  exclusions, has a decision-ledger entry with source sample ID, speaker label, metadata pointer,
  transcript-field hashes/lengths, discrepancy flags, and exclusion reason.
- Speaker labels are source labels only and are not verified identities. Results must remain
  subset-separated; no pooled speaker-independence claim is made.
- The SHA-256 advertised in the source inventory is metadata evidence only. Without downloading
  audio it is not a local audio fingerprint verification.

## Artifacts and verification

Run these commands from the ML checkout:

```powershell
python scripts/freeze_voice_corpora_v2_manifests.py preregister
python scripts/freeze_voice_corpora_v2_manifests.py freeze --allow-network
python scripts/freeze_voice_corpora_v2_manifests.py verify
python -m pytest tests/voice/test_corpora_v2_manifest_freeze.py
```

`freeze --allow-network` retrieves only the pinned Hub inventory and `clean_transcription.jsonl`
metadata files. A request for a media path is rejected by construction. Outputs are installed
immutably; a differing artifact or checksum drift fails rather than overwriting the frozen record.
The canonical subset manifests are under `artifacts/eval_voice_corpora_v2_manifest_freeze/`;
the registry records their SHA-256 values and links the record-level decision ledgers and report.

## Gate meaning and blockers

The new gate can verify `METADATA_MANIFESTS_FROZEN_ACQUISITION_BLOCKED`; this means only that the
selected metadata and decision trail are immutable and reproducible. It is not an audio-ready or
model-evaluation gate. Acquisition is rejected unless a source has a frozen selected manifest,
explicit unconditional local-evaluation permission, verified evaluation independence, and no
source-level block.

The current UrduSpeech media rights review and evaluation-independence review are unresolved.
Other registry sources lack a frozen selected manifest in this phase; Pashto consent/redistribution
review is pending, Common Voice Sindhi is reference-only, South Asian English source metadata has
not been selected/frozen, and the fresh Sindhi holdout remains data-pending. The pre-existing
readiness gate remains unchanged and blocked. No ASR result is produced by this phase.

