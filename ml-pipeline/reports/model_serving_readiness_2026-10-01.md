# Model serving readiness — 2026-10-01

Target: CPU serving for visual product retrieval and English, Urdu, Sindhi,
Pashto speech input. **Customer production status: BLOCKED.** This is an
implementation and evidence status, not a new model comparison.

| Boundary | Verified in this checkout | Remaining release gate |
| --- | --- | --- |
| Visual model | Pinned OpenCLIP loaded offline with the unchanged Khaadi index: 2,093 vectors, `khaadi-v1`, index SHA-256 `cd6c6d6e53f7f7ad94de3f555cca71685e5905d50eb36f54d7c87308e0a1084b`. Internal visual HTTP and canonical-resolution bridge focused checks passed. | Real vendor catalog images, a newly approved index, published-listing filtering and backend customer authorization are absent. Khaadi fixture IDs must not be shown as live products. |
| Voice HTTP | New `voice-http-v1` contract, loopback service, offline pinned-checkpoint load and SHA check, bounded WAV upload, English/Urdu allowlist, backpressure and safe errors. API checks: 92 passed. The real-cache readiness check returned liveness 200 and readiness 503 as designed. | Pinned Whisper weights are absent in this checkout, so real-model inference and CPU latency were not tested. There is no backend gateway or speech-to-search integration. |
| Voice evidence | Frozen `EVAL-VOICE-V1` verifier returned `EVIDENCE_VERIFIED` without rerunning models. | Independent target-user speech and operating SLOs are missing. Sindhi holdout remains PENDING; Pashto selection evidence is insufficient. MMS is noncommercial; Whisper FLEURS Sindhi/Pashto error rates are unsuitable as production approval. |

No real catalog or independent Sindhi/Pashto human recordings were supplied for
this work. No model was selected for a four-language commercial launch, no
frozen evaluation artifact was changed, and no endpoint was exposed to the
frontend. The next launch work depends on genuine catalog and speech inputs;
the internal APIs alone do not establish customer production readiness.
