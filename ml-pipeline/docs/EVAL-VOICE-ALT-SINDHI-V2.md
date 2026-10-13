# EVAL-VOICE-ALT-SINDHI-V2

Fresh reference-only evaluation of the pinned BuzzASR Sindhi checkpoint on the
frozen 50-record Sindhi FLEURS subset. The model declares FLEURS training, so
scores are contaminated/reference-only and cannot authorize production choice.

Protocol: CPU float32, eight torch threads, one warmup, one scored call per
sample, and no retries. An independent Sindhi holdout remains required.
