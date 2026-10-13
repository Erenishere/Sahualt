# Retrieval Repository Structure

## Status

This repository is one installable Python distribution with five bounded areas:

- `sahulat_visual`: completed and locked Visual Retrieval V1.
- `sahulat_text`: Phase 2 text data, evaluation, and future retrieval components.
- `sahulat_database`: Migration 001 execution and PostgreSQL contract verification.
- `sahulat_api`: optional internal visual-only HTTP adapter, not a business backend.
- `sahulat_voice`: isolated STT foundation and FLEURS benchmark preparation; model evaluation pending.

TEXT-QUERY-V1 **software tooling** is separately FROZEN / GREEN in
`configs/gates/text_query_tooling_v1.json`. It preserves source/contract/test evidence, not
human data: genuine queries remain 0/PENDING and query dataset freeze is NOT POSSIBLE.
The EVAL-TEXT-V1 protocol remains frozen; text retrieval is not unblocked.
See [parallel engineering track](parallel-engineering-track-v1.md) for the proposed independent
runtime, deployment, voice and vendor-assistant boundaries. The visual-only adapter is now
implemented under [Visual HTTP V1](../API-VISUAL-V1.md). The independent
[voice foundation](../VOICE-STT-FOUNDATION-V1.md) now has bounded PCM WAV ingestion,
Whisper/MMS adapters, transcript checksums and an evaluation-input scaffold; real speech-model
verification is pending. Deployment, full voice search and vendor-assistant remain plans,
not replacements for accepted ADRs.
The independent [EVAL-VOICE-V1](../EVAL-VOICE-V1.md) preparation gate preregisters 50 FLEURS
test recordings per language and verifies source/PCM16/reference parity before dataset freeze.
Preparing this corpus does not run speech models or unblock text retrieval.

The visual package is not moved or modified. Its imports, CLI, evaluation protocol and evidence
paths remain stable; the optional HTTP adapter depends on its existing service boundary.

## Source layout

```text
src/
|-- sahulat_api/
|   |-- app.py                 # Lifecycle, health/readiness, safe image endpoint
|   |-- uploads.py             # Bounded in-memory multipart parser
|   |-- identity.py            # Explicit external -> canonical identity adapter
|   |-- catalogue.py           # Optional read-only backend reference projection
|   `-- settings.py            # Runtime settings, not business credentials
|-- sahulat_database/
|   |-- migrations.py          # Checksum-verified SQL migration execution
|   `-- verification.py        # DB contract and integrity evidence
|-- sahulat_visual/            # Existing locked Baseline C implementation
|-- sahulat_voice/             # Independent STT only; no text/DB/API/visual dependency
|   |-- audio.py               # Bounded 16 kHz mono PCM WAV validation
|   |-- adapters.py            # Pinned offline-default Whisper and MMS adapters
|   |-- transcript.py          # Separate voice normalization and deterministic checksum
|   |-- evaluation.py          # Human voice input validator and WER/CER scaffold only
|   |-- benchmark/             # Offline FLEURS acquisition, preparation, preregistration and freeze
|   `-- cli.py                 # Capabilities, transcription, neutral input validation
`-- sahulat_text/
    |-- contracts.py           # Shared result and retriever interfaces
    |-- ingestion/
    |   |-- contracts.py       # Fixture-independent canonical write contract
    |   |-- canonical.py       # Deterministic IDs and parity checksums
    |   |-- postgres.py        # Transactional canonical PostgreSQL importer
    |   `-- khaadi/            # Frozen Khaadi v1 reader and mapper only
    |-- normalization.py       # Shared locked Gate 1 / ingestion / document policy
    |-- documents/
    |   |-- projection.py      # Immutable fixture-independent Product semantics
    |   |-- repository.py      # Read-only PostgreSQL Product/Variant loader
    |   |-- builder.py         # Pure product-text-v1 rendering and checksums
    |   |-- serialization.py   # Canonical UTF-8 JSON bytes and SHA-256
    |   |-- artifacts.py       # JSONL, manifest, parity and build evidence
    |   `-- cli.py             # Build entry point; no retrieval
    |-- retrievers/
    |   |-- lexical/            # Future Baseline A: PostgreSQL FTS
    |   |-- dense/              # Future Baseline B: dense text retrieval
    |   `-- hybrid/             # Future Baseline D: lexical+dense RRF
    |-- evaluation/            # Pre-registered policy, human collection/validators and freeze
    `-- service/               # Future product-ID search orchestration
```

## Dependency rules

1. Retrieval `contracts` has no database, model, web-framework, or visual dependencies.
2. Fixture readers map source rows into canonical ingestion inputs before SQL. The canonical
   PostgreSQL importer never reads Khaadi column names.
3. Khaadi ingestion verifies the frozen source, Gate 1 dispositions, and locked Visual V1 image
   retention. Fixture-only logic cannot leak into the canonical importer.
4. PostgreSQL is the business-data source of truth. JSON evidence is an evaluation snapshot,
   never a production write source.
5. Document construction consumes an immutable canonical Product projection, not Khaadi CSV
   fields. The pure builder has no SQL/fixture dependencies. The read-only loader uses Product
   and applicable non-archived Variant colors, never Listing, Inventory, images or external refs.
   ADR-ML-004 locks normalization, rendering, ordering and serialization for `product-text-v1`.
6. Lexical and dense retrievers implement `TextRetriever` independently.
7. Hybrid retrieval consumes ranked text results; it must not import Visual Retrieval V1.
8. Evaluation invokes public retriever contracts against one frozen EVAL-TEXT-V1 dataset.
   Synthetic fixtures are test data, never benchmark evidence.
   Currently only protocol registration, annotation validation and checksum freezing exist;
   human queries/labels and retrieval/metrics execution remain pending. Evaluation reads the
   registered corpus snapshot, not PostgreSQL or raw Khaadi CSV.
   Query-only commands collect human-supplied records, preserve coordinator-owned IDs/text,
   enforce blinding-related field allowlists and never read judging artifacts. Partial authoring
   collection is not the minimum/strata acceptance gate; freeze remains complete-validation-only.
9. Service orchestration returns product IDs, scores, and source ranks. It does not own catalog
   enrichment, tenancy, or commercial eligibility rules.
10. The optional HTTP adapter imports Visual V1, not text/annotation/retriever modules.
    Startup pins existing local index bytes and cached model identity. HTTP emits namespaced
    external IDs; optional backend reference resolution verifies image/product ownership
    without changing ranking or authorizing results. Neither runtime nor startup writes DB state.
11. Speech-to-text is isolated from all existing packages and teammate-owned text/labeling work.
    It uses the existing optional ML dependencies, not a new decoder or backend stack.
    Transcript normalization/checksums are distinct from product documents. Recognized speech
    never becomes a research query/reference automatically; no search or public route exists.
    Offline FLEURS preparation has a separate source lock, protocol registry and corpus registry.
    It never imports speech models, SQL, HTTP serving or text research modules. Only this adapter
    converts source encodings; runtime format/normalization remain unchanged. Published read-script
    references are retained exactly; no generated transcript or fabricated speaker metadata exists.

## Repository-level ownership

| Path | Responsibility |
| --- | --- |
| `database/` | Versioned canonical schema migrations |
| `configs/` | Versioned evaluation and runtime settings |
| `data/` | Local immutable source data; ignored by Git |
| `artifacts/` | Generated reproducibility evidence; ignored by Git |
| `docs/` | Architecture, ADRs, protocols, and integration contracts |
| `reports/` | Human-readable audits, validation, and failure analysis |
| `scripts/` | Thin entry points; reusable logic belongs under `src/` |
| `tests/` | Unit, integration, model, database, and contract verification |

## Phase 2 implementation order

1. Accept ADR-DATA-001 and lock Product/Variant/Listing/Inventory/Image ownership.
2. Audit Khaadi as an evaluation fixture against the production contract.
3. Apply Migration 001 and freeze DB-CONTRACT-V1 after integrity review.
4. Import the audited fixture through canonical inputs and prove Gate 1/PostgreSQL parity.
5. ADR-ML-004 accepted; `product-text-v1` built from canonical PostgreSQL projections (GREEN).
6. EVAL-TEXT-V1 protocol pre-registered; human queries and exhaustive labels remain pending.
7. Accept ADR-ML-002, then implement PostgreSQL FTS Baseline A.
8. Implement and evaluate dense Baseline B.
9. Implement text-only RRF Baseline D.
10. Add the search service/CLI boundary and evidence pack.

```text
Khaadi fixture -> fixture adapter -> canonical PostgreSQL Product/Variants
                                        |
                           CanonicalProductProjection
                                        |
                                 product-text-v1
                                        |
                         derived JSONL + manifest/checksum
```

Future vendor-created Products use the same projection/builder; Listing/Inventory remain
structured metadata, not searchable document text. EVAL-TEXT-V1 datasets/results, retrieval,
Voice-to-search, multimodal Baseline E, visual rework, pgvector and Commerce remain unimplemented.
Only the separate internal visual HTTP surface is implemented; no text route/retriever exists.
