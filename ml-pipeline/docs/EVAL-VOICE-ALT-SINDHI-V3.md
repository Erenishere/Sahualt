# EVAL-VOICE-ALT-SINDHI-V3

Fresh reference-only evaluation of the pinned BuzzASR Sindhi checkpoint. The
published checkpoint fixes Sindhi and transcription in its generation config;
the adapter therefore does not redundantly pass those arguments to the frozen
Transformers runtime. All other protocol controls remain unchanged.
