# EVAL-VOICE-ALT-V2 — compatibility-fixed specialist comparison

This is a fresh immutable run of the EVAL-VOICE-ALT-V1 comparison after fixing
Transformers 4.57 compatibility for the pinned Pashto tokenizer. It reuses only
the already verified checkpoints and the identical frozen 50-record Pashto subset.
The prior V1 failure evidence remains preserved and is not retried.

The adapter reads the published tokenizer configuration without rewriting it. When
the published `extra_special_tokens` value is a list, it supplies the equivalent
token-to-token mapping required by the frozen Transformers 4.57.6 runtime. No
dependency upgrade, model change, decoding change, or inference retry is allowed.

The run uses the same CPU/float32/8-thread protocol, one warmup, exactly one scored
call per sample, the same scoring implementation, and the same independence gates.
Sindhi remains contaminated/reference-only and is not inferred. This run exists only
to produce a valid observation for comparison with the preserved historical results;
it does not authorize production selection.
