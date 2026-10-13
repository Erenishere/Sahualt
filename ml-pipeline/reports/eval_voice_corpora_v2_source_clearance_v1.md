# EVAL-VOICE-CORPORA-V2 — Source Clearance V1

**As of:** 2026-10-12  
**Status:** Preliminary clearance records prepared; audio acquisition remains `BLOCKED`.

This is a technical evidence dossier, not a legal opinion or permission grant. Codex prepared the records on 2026-10-12. No authorized human decision reviewer is assigned, no source owner was contacted, and no legal review was performed. The dataset publisher's statement is recorded separately from project approval. No audio was downloaded, no model was executed, and no fine-tuning, manifest change, or readiness-rule amendment occurred.

## Clearance decisions

| Source | Preliminary decision | Publisher-stated use / terms | Project-permitted use now | Human decision outstanding |
| --- | --- | --- | --- | --- |
| UrduSpeech | `PENDING_NOT_CLEARED` | Dataset card declares CC-BY-4.0 and ASR research use; media sources include YouTube and Pakistan Television. | Metadata audit only. No audio acquisition or local ASR approval. | Resolve rights in the underlying media, not merely the dataset wrapper, and provide a dated permitted-use decision. |
| South Asian English CV26 | `PUBLISHER_TERMS_DOCUMENTED; PROJECT GATE PENDING` | CC0-1.0; English ASR research/development intended; no speaker identification or rehosting. Test split is 3,864 clips / 81 speakers and the bundled accent tag spans India, Pakistan, and Sri Lanka. | No acquisition until a selected metadata manifest and checkpoint-exposure assessment are complete. Future scope: local test evaluation without identity attempts, rehosting, or resharing; report the regional scope accurately. | Freeze selected metadata IDs and have a human reviewer accept the source and independence evidence. |
| Pashto Audio-Visual Corpus | `NOT_CLEARED` | Page labels package CC0-1.0 and ASR use, but also says consent and public-redistribution documentation await owner review and that the page is a private draft not submitted for review/publication. | Metadata/rights review only. No audio or video acquisition, extraction, or ASR use. | Obtain owner/steward confirmation resolving consent, source-media rights, and audio-only evaluation/extraction scope. |
| Common Voice Sindhi CV27 | `REFERENCE_ONLY; INDEPENDENCE AND MANIFEST PENDING` | CC0-1.0; ASR evaluation intended; no speaker identification, rehosting, or resharing. Publisher lists 328 validated clips and 42 in the official test split; 65,569 remain unresolved. | Metadata review only for now. Not independent model-selection evidence; no audio acquisition until a selected manifest is frozen. | Freeze an eligible selection and assess model exposure, including BuzzASR's Common Voice 25 training declaration. |
| Fresh Sindhi holdout | `APPROVED_PROTOCOL; DATA PENDING` | SINDHI-HOLDOUT-V1 allows local evaluation only with recorded per-speaker permission. Public distribution needs separate explicit permission and a license. | None yet: 0/100 recordings, no selected manifest, and no evaluation. | Collect consented recordings, review references/attestations, then freeze and verify the holdout. |

The full structured records include reviewer/preparer fields, date, exact source and checkpoint revisions, evidence URLs, permitted-use distinctions, and unresolved restrictions. A null `clearance_decision_date` means no human clearance decision has been made.

## Checkpoint exposure and model terms

All source-specific exposure assessments remain `UNKNOWN` unless a known declaration is stated below. A source's public `test` label, a lack of found duplicates, or publication after a model release does not prove independence.

| Pinned checkpoint | Published evidence | Clearance consequence |
| --- | --- | --- |
| Whisper large-v3 `06f233fe06e710322aca913c1bc4249a0d71fce1` | Apache-2.0. The pinned model card reports 1M hours weakly labeled and 4M hours pseudo-labeled audio, without a complete auditable corpus inventory. | Exposure to UrduSpeech, CV26, Pashto Audio-Visual, CV27, and fresh Sindhi remains `UNKNOWN`. |
| MMS-1B-All `3d33597edbdaaba14a8e858e2c8caa76e3cec0cd` | CC-BY-NC-4.0. The pinned model card lists Google FLEURS as a training dataset. | Exposure to the new V2 sources remains `UNKNOWN`; the separate noncommercial model license needs review for any use outside academic research. Frozen FLEURS results remain separate. |
| Pashto Ghag `ed20e00d47d0852ed24f07b4370c0bdac2e5f241` | Apache-2.0; model card declares validated Pashto Common Voice 17 training; base-model exposure inventory is incomplete. | Pashto Audio-Visual exact audio/speaker overlap remains `UNKNOWN`, not clear. |
| BuzzASR Sindhi `8e85f09a5c0b17c635ffa8fd124b1efa56fcb5c7` | MIT; model card declares FLEURS, Common Voice 25.0, and text-only Goldfish training; fine-tuned from Whisper large-v3. | Common Voice 27 has a possible release-family overlap; exact sample/audio/speaker overlap is not established, so status remains `UNKNOWN` and CV27 remains `REFERENCE_ONLY`. Fresh-holdout speaker exposure remains unknown pending attestations. |

The exact model-card README hashes at the pinned commits and checkpoint revisions are recorded in the JSON file. Whisper/MMS checkpoint exposure was not upgraded based on incomplete training documentation.

## Source evidence

- [UrduSpeech pinned dataset card](https://huggingface.co/datasets/ASLP-lab/UrduSpeech/blob/16dd380cfd9049a3db7f06a98e878086916bf833/README.md) declares CC-BY-4.0 and identifies YouTube/PTV source content. That declaration does not resolve the rights of each underlying recording.
- [South Asian English Common Voice 26 source](https://mozilladatacollective.com/datasets/cmrt70sar001umm07jwxzhw89) declares CC0, specifies a speaker-disjoint test split, documents the combined regional accent tag, and forbids speaker identity attempts and rehosting.
- [Pashto Audio-Visual Corpus source](https://mozilladatacollective.com/datasets/cmuzrhfbd006l07nxoe3inrzq) shows a CC0 label while also stating that consent and public-redistribution documents await owner review and that the page is a private draft. The project retains the blocked status pending an owner decision.
- [Common Voice 27 Sindhi source](https://mozilladatacollective.com/datasets/cmu5wbmn400bco107vi2n2yhb) declares CC0 and ASR evaluation intent, prohibits speaker identification/rehosting/resharing, and reports 328 validated clips, 42 official test clips, and 65,569 unresolved clips.
- Pinned checkpoint cards: [Whisper large-v3](https://huggingface.co/openai/whisper-large-v3/blob/06f233fe06e710322aca913c1bc4249a0d71fce1/README.md), [MMS-1B-All](https://huggingface.co/facebook/mms-1b-all/blob/3d33597edbdaaba14a8e858e2c8caa76e3cec0cd/README.md), [Pashto Ghag](https://huggingface.co/Nasimbahar/pashto-ghag-whisper-medium-asr/blob/ed20e00d47d0852ed24f07b4370c0bdac2e5f241/README.md), and [BuzzASR Sindhi](https://huggingface.co/BuzzASR/sindhi/blob/8e85f09a5c0b17c635ffa8fd124b1efa56fcb5c7/README.md).

Live Mozilla Data Collective pages were reviewed on 2026-10-12; they do not provide an immutable page snapshot hash. For Hugging Face sources, dataset/model revisions are pinned in the local registry, and the exact README SHA-256 values are included in the structured record. The UrduSpeech metadata manifests remain unchanged: Standard Urdu 200, code-switched 200, Pakistani English 141. The Pakistani English shortfall is accepted; do not add records to reach 200. Report `n=141` and uncertainty when evaluation is authorized.

## Remaining blockers

1. A human rights reviewer and, where needed, source owners must provide dated decisions and permitted-use boundaries for UrduSpeech and Pashto.
2. Freeze South Asian English and Common Voice Sindhi selected metadata manifests without changing existing UrduSpeech manifests.
3. Document exact checkpoint exposure for each selected source. Unknown stays `UNKNOWN`; source-owner statements or auditable model training manifests are required to clear it.
4. Collect the approved fresh Sindhi holdout only after recording each participant's permission; complete transcript review and the existing freeze gate before any model run.

The manifest-freeze gate remains `METADATA_MANIFESTS_FROZEN_ACQUISITION_BLOCKED`; the existing acquisition-readiness gate remains `BLOCKED`. EVAL-VOICE-V1 evidence, existing rights statuses, and readiness rules are unchanged. The JSON report anchors this dossier to SHA-256 hashes of the current source registry, readiness records, and frozen manifest records.
