# SINDHI-HOLDOUT-V1

This gate collects an independent human Sindhi ASR holdout. It requires 50
human-authored Perso-Arabic Sindhi utterances (30 commerce/search and 20
everyday), 100 fresh recordings, and 10 pseudonymous speakers (`SPK001` through
`SPK010`). Each utterance is assigned to exactly two speakers and each speaker
records exactly ten utterances.

The collection importer accepts only the exact provenance values
`recording_source=fresh_human_recording`, `reference_source=human`, and
`preparation_version=sindhi-holdout-preparation-v1`. This excludes FLEURS,
Common Voice, synthetic/TTS, translated-benchmark, and model-generated sources.
References remain raw human text and require a named human reviewer; no model
output is accepted in the dataset. Audio is validated by the existing 16 kHz
mono PCM16 WAV contract. Freeze copies each recording into a canonical artifact
tree and records per-file and manifest SHA-256 checksums. Model evaluation is
unavailable until freeze verification passes.

Every speaker must confirm consent and evaluation-use permission before a
recording is accepted. Public-corpus participation is captured separately for
Common Voice, FLEURS, BuzzASR-related data, and other public Sindhi ASR data.
Those field names are risk attestations, not evidence that a recording came from
a forbidden source and not automatic proof of independence. A positive
attestation requires explicit overlap review before the final evaluation freeze.

The assignment function is deterministic but requires the final human-authored
utterance inventory before it can produce the frozen assignment manifest.
An entirely empty input is valid only as `PENDING`; it cannot be frozen.
