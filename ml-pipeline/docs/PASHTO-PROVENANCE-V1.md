# PASHTO-PROVENANCE-V1

This gate is separate from the frozen ASR benchmark. It checks the exact
Pashto Ghag revision, Apache-2.0 license, published dataset declaration, pinned
weights, and evidence needed to establish independence from FLEURS.

The publisher card declares Mozilla Common Voice 17 Pashto training and does
not declare FLEURS. That declaration is not sufficient by itself: GREEN also
requires a complete training manifest, a FLEURS-overlap audit, and a signed or
otherwise attributable provenance attestation. Missing evidence keeps the gate
`NOT_GREEN` and does not alter any router or benchmark artifact.
