# EVAL-VOICE-CORPORA-V2 exclusion-bias addendum V1

**Status:** supplemental descriptive audit; frozen manifests and selection are unchanged.

## Population reconciliation

The 379 transcript disagreements were audited across the full pinned UrduSpeech benchmark inventory of 4,170 records, not only within the earlier 544-record preview. The earlier preview was marked `PREVIEW_NOT_FROZEN`; it selected duration-eligible records before transcript agreement was an exclusion criterion. The final 541-record selection was then drawn deterministically from the full inventory after applying the frozen transcript-exclusion policy.

| Subset / language | Full inventory | Disagreements in inventory | Disagreement rate | Earlier preview | Disagreements in preview | Frozen selection | Preview IDs retained | New replacement IDs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Standard Urdu (`ur`) | 2,173 | 185 | 8.51% | 200 | 17 | 200 | 183 | 17 |
| Urdu-English (`ur-en`) | 1,853 | 191 | 10.31% | 200 | 27 | 200 | 173 | 27 |
| Pakistani English (`en-pk`) | 144 | 3 | 2.08% | 144 | 3 | 141 | 141 | 0 |
| **Total** | **4,170** | **379** | **9.09%** | **544** | **47** | **541** | **497** | **44** |

Thus, 332 of the 379 inventory-wide disagreements were not in the earlier preview sample. All 47 disputed preview records were excluded. The 44 new selections replace the 17 Standard Urdu and 27 Urdu-English preview disagreements. Pakistani English had only 144 inventory records; after its three transcript exclusions, all 141 remaining eligible records were selected, leaving a 59-record shortfall against the nominal target of 200. This reconciles the counts: 497 retained preview IDs + 44 replacements = 541 frozen records. It is not `544 - 379` because 379 is a source-wide audit count, not the mismatch count inside the preview.

## Disagreement and script-profile distributions

The frozen deterministic disagreement classifier reported:

| Category | Standard Urdu | Urdu-English | Pakistani English | Total |
| --- | ---: | ---: | ---: | ---: |
| Missing or added words | 57 | 40 | 0 | 97 |
| Punctuation or whitespace only | 1 | 1 | 0 | 2 |
| Script-profile change (classifier category) | 62 | 108 | 2 | 172 |
| Semantic review required | 22 | 7 | 0 | 29 |
| Spelling or token substitution | 43 | 35 | 1 | 79 |
| **Total** | **185** | **191** | **3** | **379** |

Separately, a descriptive Unicode heuristic was applied to alphabetic characters in each published transcript field: `Transcription` and `ground_truth`. It records `LATIN`, `ARABIC`, `DEVANAGARI`, `CYRILLIC`, `GREEK`, or `OTHER` from Unicode character names; punctuation, combining marks, and numerals are ignored. The two fields had different detected profiles in 172 records and the same profile in 207. This heuristic is not linguistic adjudication and is independent of the deterministic disagreement category; matching script profiles do not imply matching meaning or correct transcription. Full field-profile counts and pairings are in the JSON addendum.

The identical aggregate value of 172 for classifier-category `SCRIPT_PROFILE_CHANGE` and heuristic `PROFILE_DIFFERS` does not establish that they are the same 172 records.

## Published speaker labels

The JSON addendum contains exact mismatch counts for each published speaker label, separated by subset: 31 distinct labels in Standard Urdu, 20 in Urdu-English, and 3 in Pakistani English. These are source labels only, not verified speaker identities. They are not merged or compared across subsets as identities.

## Bias assessment and limits

The exclusion policy removes records whose two publisher transcript fields disagree, so the frozen evaluation sample is conditional on source-field agreement. This may underrepresent speech or transcript cases associated with script changes, missing/added words, semantic review, or spelling/token substitutions. The observed disagreement rate is highest in the Urdu-English subset (10.31%), and its classifier category `SCRIPT_PROFILE_CHANGE` accounts for 108 of 191 disagreements. That is a material selection-bias risk to disclose.

These metadata counts do not establish whether excluded audio is acoustically harder or how exclusion changes model WER/CER; no audio was acquired or evaluated. The mismatches remain unadjudicated, and no semantic differences were automatically resolved. The frozen selection must not be changed without a separately versioned protocol amendment.

## Provenance, gate, and remaining blockers

The descriptive audit was recomputed from the pinned revision's inventory and `clean_transcription.jsonl` metadata only. Its metadata evidence checksum matches the prior source audit. No audio bytes were requested, no transcript strings were persisted in this report, and no model was run or fine-tuned. Input artifact hashes and complete language, profile, category, and published-label counts are recorded in [the JSON addendum](eval_voice_corpora_v2_exclusion_bias_addendum_v1.json).

The manifest-freeze verifier passes with status `METADATA_MANIFESTS_FROZEN_ACQUISITION_BLOCKED` (4,170 decision rows; selected counts 200/200/141). The separate, pre-existing readiness verifier remains `BLOCKED`; its rules and report were not changed. The acquisition gate and source-rights registry remain authoritative, and this addendum neither grants rights nor upgrades checkpoint independence.

Remaining source statuses are copied without reinterpretation from the authoritative freeze registry:

| Source | Current authoritative status | Blocking condition |
| --- | --- | --- |
| UrduSpeech | Rights `PENDING_SOURCE_MEDIA_RIGHTS_REVIEW`; local evaluation `PENDING_ORIGINAL_SOURCE_MEDIA_RIGHTS_REVIEW`; independence `NOT_VERIFIED` | Source-media rights and exposure review |
| South Asian English | Local evaluation `CONDITIONALLY_ALLOWED`; no selected manifest | Freeze a selected manifest before acquisition |
| Pashto Audio-Visual | `QUARANTINED_AUDIT_ONLY`; owner-consent documentation pending; rights review pending | Consent/rights clarification and a selected manifest |
| Common Voice Sindhi | `REFERENCE_ONLY`; local evaluation allowed by stated intended use; no selected manifest | Freeze an eligible manifest; do not use as independent model-selection evidence yet |
| Fresh Sindhi holdout | Protocol `APPROVED_DATA_PENDING`; local evaluation only with recorded speaker permission | Collect/validate consented recordings and freeze the holdout |

The acquisition gate remains `BLOCKED` for all five sources. EVAL-VOICE-V1 evidence was not changed.
