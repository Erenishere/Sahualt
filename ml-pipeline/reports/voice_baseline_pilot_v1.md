# VOICE-BASELINE-PILOT-V1

**Status: PILOT — waiting for consented first-party recordings.**

No eligible first-party audio or human-verified references are present in the
pilot workspace. Therefore no inference has run, and no WER, CER, failure,
latency, commerce, error-example, or strongest-model results are claimed.

| Group | Recordings | Speakers | Target | Ideal native speakers |
| --- | ---: | ---: | ---: | ---: |
| Urdu (`ur`) | 0 | 0 | 30 | 5 |
| Urdu-English (`ur_en`) | 0 | 0 | 30 | 5 |
| Sindhi (`sd`) | 0 | 0 | 30 | 5 |
| Pashto (`ps`) | 0 | 0 | 30 | 5 |

The consent-gated recording, annotation, deterministic selection, freeze,
offline inference, and comparison workflow is documented in
[`VOICE-BASELINE-PILOT-V1.md`](../docs/VOICE-BASELINE-PILOT-V1.md). Run
`scripts/voice_baseline_pilot_v1.py init`, obtain approved consent, add fresh
human recordings and independently verified references, then validate and
freeze before inference.

This pilot is separate from EVAL-VOICE-V1 and EVAL-VOICE-CORPORA-V2. It does
not replace their evidence or promote any model to production. Small sample
sizes will be reported as pilot limitations.
