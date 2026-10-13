# EVAL-VOICE-ALT-V2 comparison

The compatibility-fixed Pashto Ghag run completed on the frozen 50-record Pashto
subset. Values below are Pashto-only micro aggregates under the recorded scoring
protocol; latency is mean scored-call wall time.

| System | WER | CER | Mean latency |
| --- | ---: | ---: | ---: |
| Pashto Ghag (V2) | 0.4686 | 0.2261 | 27,827.7 ms |
| Historical Whisper large-v3 | 0.9034 | 0.3481 | 47,938.4 ms |
| Historical MMS-1B | 0.4317 | 0.1694 | 23,610.0 ms |

V2 produced 50/50 successful samples with no failed samples. The historical
Whisper and MMS figures are preserved observations, not rerun in this work.
Pashto Ghag independence is not verified because complete training manifests and
base-model overlap are unavailable; Sindhi was not inferred and production
selection remains unauthorized.

Evidence: `artifacts/eval_voice_alt_v2/validation.json` and
`configs/gates/eval_voice_alt_v2_result.json`.

## Sindhi candidate comparison

BuzzASR Sindhi V3 completed 49/50 samples successfully (one inference failure):

| System | WER | CER | Successful samples | Mean latency |
| --- | ---: | ---: | ---: | ---: |
| BuzzASR Sindhi (V3) | 0.2333 | 0.1092 | 49/50 | 27,513.2 ms |
| Historical Whisper large-v3 | 1.0151 | 0.9101 | 47/50 | not comparable due failures |
| Historical MMS-1B | 0.2408 | 0.0872 | 50/50 | 108,146.7 ms |

BuzzASR is slightly better than MMS on WER and much better than Whisper, but
slightly worse than MMS on CER and has one failed sample. Because BuzzASR
declares FLEURS training, this remains contaminated/reference-only evidence;
the independent Sindhi holdout is still pending.

Evidence: `artifacts/eval_voice_alt_sindhi_v3/validation.json` and
`configs/gates/eval_voice_alt_sindhi_v3_result.json`.
