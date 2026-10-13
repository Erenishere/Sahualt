# EVAL-VOICE-ALT-SINDHI-V1

This is a fresh, frozen comparison of the pinned BuzzASR Sindhi checkpoint on
the same 50-record Sindhi FLEURS subset used by the preserved Whisper and MMS
results. The candidate explicitly declares FLEURS training, so its result is
`CONTAMINATED / REFERENCE-ONLY` and cannot support production model selection.

The run uses CPU float32 inference, eight torch threads, one warmup, exactly one
scored call per sample, and no retries. An independent Sindhi holdout remains
required for any production decision.
