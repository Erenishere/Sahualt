# Sahulat AI — Phase 2 Execution Plan

**Document type:** Architectural / engineering / project planning (no implementation)  
**Sources of truth:** FYP Proposal *SAHULAT — A Multimodal Commerce Discovery, Controlled Offer, and Vendor Intelligence Platform* (2026-27); Codex Visual Retrieval V1 milestone (2026-09-06); current repository state  
**Audience:** FYP team (Adeel, Bisma, Erum), supervisor, industry sponsor review  
**Status:** Canonical projection / product-text-v1 GREEN; EVAL-TEXT-V1 protocol pre-registered, human queries/labels PENDING; retrieval NOT STARTED

---

# 1. Executive Summary

## Current Project State

**VISUAL RETRIEVAL V1 is complete and locked** inside this workspace as an installable Python package (`src/sahulat_visual`). Delivered: dual encoder adapters (OpenCLIP / FashionCLIP), dataset audit, EVAL-VISUAL-V1, exact cosine index, product aggregation, CLI, tests, ADR-ML-001 selecting **OpenCLIP ViT-B/32 LAION-2B** for initial CPU serving, and documented pgvector integration boundaries. PostgreSQL 18.6 has frozen Migration 001 Catalog Core V1 and verified canonical fixture ingestion. A separate optional **visual-only internal FastAPI adapter** now wraps the existing service with health/readiness, bounded memory-only uploads, safe errors and explicit external-ID scope; see `docs/API-VISUAL-V1.md`. **Not present:** ASP.NET Core API, Next.js UI, text HTTP/retrieval, Redis, FTS, pgvector, voice, offer engine, vendor assistant, or multimodal late fusion.

## Next Recommended Milestone

**TEXT RETRIEVAL V1 — Lexical + Dense + Text-Hybrid (RRF)**  
Use the production Product/Variant/Listing/Inventory/Image contract in **ADR-DATA-001**, map the Gate 1-audited Khaadi fixture through a fixture-independent canonical input into PostgreSQL, then freeze **EVAL-TEXT-V1**, implement proposal Baselines **A / B / D**, expose a product-ID-centric search service boundary, and retain Visual V1 unchanged.

## Why This Milestone Comes Next

1. **Proposal research question 1** asks how hybrid *text* retrieval improves over lexical-only and dense-only — that is Baseline D vs A/B and must precede full multimodal Baseline E.  
2. **Proposal methodology Iteration 1** requires a reproducible lexical baseline and evaluation queries before multimodal fusion experiments.  
3. **Visual branch is already frozen** (Baseline C evidence + serving decision). Text branches are the missing independent ranking lists required by the late-fusion algorithm (§5.2).  
4. **No proposal-critical blocker** forces voice, offers, or UI before text retrieval in the ML/search track; those remain parallel platform work for other team members.

## Expected Outcome

A locked, reproducible **text search increment** that:

- defines production-owned canonical documents, then instantiates them for ~400 Khaadi evaluation products;  
- runs **lexical**, **dense**, and **hybrid (RRF)** retrieval on the same EVAL-TEXT-V1 query set;  
- returns **unique ranked product IDs** through a Python service/CLI boundary;  
- produces benchmark, failure analysis, ADRs, and defense-ready evidence;  
- does **not** claim full multimodal fusion success (that is a later milestone).

---

# 2. Proposal Requirements Extracted

## Problem / motivation

Customers often start with incomplete text, voice, or a reference image. Keyword-only search fails on synonyms and informal language; image-only search ignores situational constraints. Vendors need grounded analytics; offers must remain deterministic and separate from search AI.

## Objectives (relevant to this phase)

- Catalog with structured metadata and search indexes (FR-03–FR-05).  
- Text search via **PostgreSQL full-text search** + **multilingual dense embeddings** (specific objective; tech stack: BGE-M3 or validated alternative).  
- Fuse lexical, dense-text, and (later) image rankings with documented late fusion / RRF.  
- Evaluate against baselines A–E; report honestly vs targets (e.g. full hybrid nDCG@10 ≥ +10% vs lexical-only — **full multimodal target**, not text-only).

## Functional requirements (search-related)

| ID | Requirement (proposal wording summary) |
| --- | --- |
| FR-04 | Multiple images + structured searchable attributes |
| FR-05 | Index published products for lexical, dense-text, and visual retrieval |
| FR-06 | Typed text search + optional catalog filters |
| FR-08 | Image search with selected vision model (**done in Visual V1**) |
| FR-09 | Image + text combined; separate evidence then late fusion (**later**) |
| FR-10 | Ranked eligible products + grounded refinements (**partial later**) |

## Non-functional (search-related)

NFR-01 p95 search &lt; 3 s (system target); NFR-04 degraded branch isolation; NFR-08 reproducibility; NFR-12 observability.

## Architecture (proposal)

Next.js ↔ **ASP.NET Core** (system of record) ↔ internal **FastAPI** AI/ML; PostgreSQL FTS + pgvector; Redis optional; object storage for images.

## Explicit exclusions (must not enter this milestone)

Autonomous purchasing; LLM bargaining; payments; logistics; unrestricted SQL; training foundation models from scratch; claiming equal Urdu/Sindhi/Pashto ASR accuracy.

## Ambiguities (do not invent)

1. **Lexical engine:** Proposal mandates **PostgreSQL FTS**; Codex suggested **BM25**. Resolution required via ADR (see §21).  
2. **Dense model:** “BGE-M3 or validated multilingual alternative” — final choice after local eval.  
3. **Text relevance labels:** Proposal requires graded judgments (0/1/2) with ≥2 reviewers; Khaadi has **no** ready text query set.  
4. **Category/brand/tags:** Production accepts vendor-provided category and optional brand. Khaadi lacks these columns, so the fixture must not invent them; both remain excluded from `product-text-v1`.  
5. **Parent platform timing:** Text retrieval can progress in Python offline; production FTS authenticity depends on an owned application schema and migration contract, not merely a reachable PostgreSQL server.

## Academic contribution (search)

Applied late-fusion IR system with reproducible baselines — not a new foundation model.

---

# 3. Current Implementation Audit

| Asset | State | Evidence |
| --- | --- | --- |
| Visual encoder abstraction + OpenCLIP/FashionCLIP | COMPLETE | `src/sahulat_visual/encoders/` |
| Image validation, audit, duplicates | COMPLETE | `reports/dataset_audit.md` |
| EVAL-VISUAL-V1 + frozen split | LOCKED | `docs/EVAL-VISUAL-V1.md`, `artifacts/eval_visual_v1/` |
| Catalogue visual index (2093 vectors OpenCLIP) | COMPLETE | `artifacts/catalogue-openclip.npz` |
| VisualRetrievalService + CLI | COMPLETE | `retrieval.py`, `cli.py` |
| ADR-ML-001 OpenCLIP serving | ACCEPTED | `docs/ADR-ML-001-…` |
| Unit/integration/model tests | VERIFIED | 65 executed; 63 fast pass in last report |
| Visual HTTP adapter / pgvector boundary | VISUAL HTTP IMPLEMENTED; pgvector docs only | `docs/API-VISUAL-V1.md`, `src/sahulat_api` |
| Canonical Product projection / product-text-v1 | COMPLETE / GREEN | ADR-ML-004, documents package, JSONL + manifest, product_text_v1_build.md |
| BM25 / dense text | NOT STARTED | — |
| Hybrid RRF / multimodal fusion | NOT STARTED | — |
| FastAPI / .NET / Next.js | Visual-only internal FastAPI implemented; .NET/Next.js absent | Separate optional `sahulat_api`, no business API |
| PostgreSQL Catalog Core | COMPLETE / FROZEN | Migration 001, DB-CONTRACT-V1, integrity review |
| Khaadi fixture ingestion | COMPLETE / GREEN | 400 Products, 400 default Variants/Listings, 2,093 retained Visual V1 images, deterministic parity |
| Voice / offers / vendor assistant | NOT STARTED | — |

### Locked

EVAL-VISUAL-V1; OpenCLIP as initial visual serving model; FashionCLIP as alternate; visual metric formulas; visual service product aggregation semantics.

### Experimental / not locked

Any future ANN/pgvector adapter vs exact cosine; weighted fusion vs RRF; text encoder selection; lexical engine choice when Postgres absent.

### Integration dependencies unresolved

No parent API, auth or catalogue CRUD service. Owned Catalog Core migrations, fixture ingestion
and canonical document construction now exist. Search remains product-ID centric;
enrichment/auth belong elsewhere.

---

# 4. Proposal-to-Implementation Gap Analysis

| Proposal Requirement | Current Status | Evidence | Remaining Work | Priority |
| --- | --- | --- | --- | --- |
| FR-01 Auth / roles | NOT STARTED | No .NET Identity | Backend track | Later-phase |
| FR-02 RBAC / tenant scope | NOT STARTED | — | Backend | Later-phase |
| FR-03 Vendor catalog CRUD | NOT STARTED | Demo data via Khaadi import | Backend + data | Later-phase |
| FR-04 Structured attributes + images | PARTIAL | Images + CSV fields; no category/brand columns | Metadata policy + schema mapping | Immediate |
| FR-05 Lexical + dense + visual indexes | PARTIAL | Visual only | Text indexes + versioning | Immediate |
| FR-06 Typed text search | NOT STARTED | — | Text retrieval V1 | Immediate |
| FR-07 Voice Urdu/Sindhi/Pashto | NOT STARTED | — | After text pipeline | Later-phase |
| FR-08 Image search (OpenCLIP vs FashionCLIP) | COMPLETE | ADR-ML-001, benchmarks | Keep locked; optional FastAPI wrap later | Locked |
| FR-09 Image+text late fusion | NOT STARTED | Needs text + visual lists | After Text V1 | Next-after |
| FR-10 Refinements / confidence | NOT STARTED | — | After hybrid multimodal | Later-phase |
| FR-11–14 Offer workflow | NOT STARTED | — | Commerce track | Later-phase |
| FR-15–17 Vendor dashboards / assistant | NOT STARTED | — | Vendor track | Later-phase |
| FR-18–19 Admin / audit | NOT STARTED | — | Platform | Later-phase |
| FR-20 Health / eval metrics | PARTIAL | Visual CLI metrics | Extend for text | Immediate |
| Baseline A Lexical | NOT STARTED | — | EVAL-TEXT-V1 + lexical | Immediate |
| Baseline B Dense text | NOT STARTED | — | Dense encoder ADR + eval | Immediate |
| Baseline C Image | COMPLETE | Comparison reports | Locked | Locked |
| Baseline D Text hybrid | NOT STARTED | — | RRF text fusion | Immediate |
| Baseline E Full multimodal | NOT STARTED | — | Late fusion visual+text | Next-after |
| PostgreSQL FTS | NOT STARTED | Catalog Core exists; no Search schema or FTS objects | ADR-ML-004 + ADR-ML-002 | Immediate |
| pgvector | NOT STARTED | Protocol only | Later adapter | Next-phase/later |
| Docker Compose platform | NOT STARTED | — | Integration | Later-phase |
| nDCG@10 +10% vs lexical (full hybrid) | NOT STARTED | Target is system-level | Measure after Baseline E | Later gate |
| Graded relevance query set ≥120 multimodal | NOT STARTED | Visual used product-ID proxy | Create text labels first | Immediate |

### ML component audit

| ML Component | Proposal Requirement | Current State | Evaluation State | Next Action |
| --- | --- | --- | --- | --- |
| Visual retrieval | FR-08, Baseline C | COMPLETE / LOCKED | EVAL-VISUAL-V1 done | Regression only |
| Lexical / FTS | FR-05/06, Baseline A | NOT STARTED | None | Define engine ADR; implement |
| Dense text | FR-05/06, Baseline B | NOT STARTED | None | Candidate eval (BGE-M3…) |
| Text hybrid RRF | RQ1, Baseline D | NOT STARTED | None | Same query set comparison |
| Multimodal late fusion | FR-09, Baseline E, RQ2 | NOT STARTED | None | After Text V1 |
| Speech-to-text | FR-07 | NOT STARTED | None | Out of this milestone |
| Multilingual query handling | Normalization §4.5 | NOT STARTED | None | Minimal English/Urdu-script policy only if data supports; no full multilingual claim |
| Vendor assistant / RAG tools | FR-16/17 | NOT STARTED | None | Out of scope |
| Agentic tool execution | §4.9 | NOT STARTED | None | Out of scope |
| Model serving (HTTP) | FastAPI internal | Visual-only adapter implemented | Locked Visual V1, synthetic endpoint/lineage tests | No text route; parent authz/deployment remain separate |
| Evaluation harness | §8 | Visual only | Locked visual | Clone patterns for text |

---

# 5. Locked Existing Components

Do **not** reopen without new defect evidence, integration necessity, or supervisor-approved scope change:

1. EVAL-VISUAL-V1 protocol, split, checksums  
2. OpenCLIP as initial visual serving default  
3. FashionCLIP as selectable alternate  
4. Visual encoder factory / preprocessing identity rules  
5. Product MAX aggregation + unique-product suppression for visual  
6. Visual CLI command contracts (unless additive)  
7. No visual fine-tuning this stage  

**Regression gate for Phase 2:** existing visual unit/integration tests and documented CLI smoke checks must remain green.

---

# 6. Recommended Next Milestone

## Name

**TEXT RETRIEVAL + TEXT-HYBRID V1** (proposal Baselines A, B, D)

## Consistency check vs proposal

| Proposed Codex sequence | Proposal alignment |
| --- | --- |
| Canonical product documents | **Aligned** (§4.6) |
| Text query benchmark + EVAL-TEXT-V1 | **Aligned** (§5.1 Iter 1, §8.2) |
| BM25 → Dense → Hybrid RRF | **Partially aligned** — hybrid RRF and dense yes; **lexical should be PostgreSQL FTS per proposal**, with BM25 only as documented interim if Postgres unavailable |
| Unique ranked products + search service | **Aligned** |
| Immediate multimodal / voice | **Not next** — proposal places voice and Baseline E after text baselines exist |

## Milestone goal

Deliver a defendable answer to **Research Question 1** on the project catalog, with reusable service boundaries for later Baseline E and .NET orchestration.

---

# 7. Scope — In / Out

## IN SCOPE

- Production Product/Variant/Listing/Inventory/Image boundary and ingestion contract (ADR-DATA-001)  
- Product metadata audit of Khaadi CSV against the production contract  
- Canonical product document schema + builder (`product-text-v1`)  
- Text normalization policy (deterministic, documented; no invented attributes)  
- EVAL-TEXT-V1 freeze (queries, relevance policy, metrics, config)  
- Lexical retriever (PostgreSQL FTS when available; interim local lexical only if ADR accepts temporary deviation)  
- Dense text encoder adapter + catalogue embeddings (`dense-text-v1`)  
- Hybrid fusion via RRF (`hybrid-rrf-v1`) for **text branches only**  
- Benchmark comparison A vs B vs D on identical query set  
- Failure analysis + latency methodology  
- Product-ID-centric Python search service + CLI  
- Unit/integration/contract tests; visual regression suite  
- ADRs, docs, evidence packs  
- Config/versioning for indexes and eval  

## OUT OF SCOPE (this milestone)

- Visual model reselection / fine-tuning  
- Multimodal late fusion Baseline E (scheduled next ML phase)  
- Voice ASR / transcript UI  
- Recommended-search LLM paraphrasing / facet refinements (except documenting hooks)  
- Vendor assistant, offers, payments, personalization, checkout  
- Learning-to-rank, sponsored ranking  
- Production auth inside ML package  
- Full multilingual production claims  
- Rewriting locked visual package internals without blocker  

---

# 8. Deliverables

## D0 — Production Product Ingestion Contract

- **Purpose:** Define the real product lifecycle before allowing fixture shape to influence search design.  
- **Output:** `docs/ADR-DATA-001-product-ingestion-and-search-metadata-contract.md`.  
- **Acceptance:** Product, ProductVariant, Listing, Inventory, and ProductImage separation; vendor validation; source of truth; semantic vs dynamic fields; missing-data policy; versioning; checksums; and re-index triggers are explicit.  
- **Status:** ACCEPTED.  

## D1 — Product Metadata Audit

- **Purpose:** Measure how faithfully Khaadi can instantiate the production contract without inventing attributes.  
- **Input:** ADR-DATA-001, `khaadi_data.csv`, and `manifest.json`.  
- **Output:** `reports/product_metadata_audit.md` + machine-readable JSON.  
- **Acceptance:** Row/ID counts, duplicates, nulls, blanks, malformed values, distinct values, usable coverage, text lengths, placeholder values, normalization impact, price parse success, and availability vocabulary are recorded.  
- **Evidence:** Audit report committed; field policy cited by document builder.  
- **Dependency:** D0 and dataset present.
- **Status:** COMPLETE — 400 valid document candidates, 0 quarantined product IDs.  

## D2 — Canonical Product Document Schema (`product-text-v1`)

- **Purpose:** Transform production product semantics into one deterministic text record per `product_id`; keep listing state separate.  
- **Input:** Canonical PostgreSQL Product/Variant projection; no CSV fields or listing data.
- **Output:** Schema doc, builder module, `artifacts/product_documents/product-text-v1.jsonl` (or equivalent).  
- **Tests:** Determinism, missing-field handling, no path leakage.  
- **Docs:** ADR-ML-004 implements the fixed Name → Description → optional Color transformation; price, currency, availability, and stock remain structured.  
- **Evidence:** `reports/product_text_v1_build.md`, JSONL and deterministic manifest/checksums;
  future indexes must retain document version/hash.
- **Dependency:** D1.
- **Status:** COMPLETE / GREEN. ADR-ML-004 accepted; 400 eligible canonical Products produce
  400 documents with measured DB parity. EVAL-TEXT-V1 results and indexing remain NOT STARTED.
- **Frozen corpus:** `PRODUCT-TEXT-V1`, SHA-256
  `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`;
  versioned registry `configs/corpora/product_text_v1.json`, content-addressed snapshot.
  Future experiments must bind this identity/hash, not the mutable working build path.

## D3 — EVAL-TEXT-V1 Protocol + Query Set

- **Purpose:** Freeze text evaluation comparable across A/B/D.  
- **Input:** Catalog products; labeling plan (human graded relevance).  
- **Output:** `docs/EVAL-TEXT-V1.md`, `configs/eval_text_v1.yaml`, frozen query JSON, labeling guide.  
- **Acceptance:** ≥N labeled queries (recommend **≥40** for interim ML gate; scale toward proposal **≥120 multimodal total** across later phases); dual-review or adjudication policy documented; **no fabricated labels**.  
- **Evidence:** Query file hash, judge instructions, disagreement log.  
- **Dependency:** D1 (for realistic query design).
- **Current status:** Protocol FROZEN in `configs/eval_text_v1.yaml` and its semantic JSON lock;
  `docs/EVAL-TEXT-V1.md`, `docs/text-labeling-v1.md` and human-input validators are implemented.
  Real query set and exhaustive human labels remain PENDING. D3's labeled-dataset acceptance
  is not complete; no metric runner or benchmark evidence is claimed.

## D4 — Lexical Retriever (`bm25-v1` or `pgfts-v1`)

- **Purpose:** Baseline A.  
- **Input:** product-text-v1 documents.  
- **Output:** Index artifact + retriever implementing shared `TextRetriever` protocol.  
- **Tests:** Exact token hits, empty query, top-k uniqueness.  
- **Docs:** ADR-ML-002 lexical engine decision.  
- **Evidence:** Benchmark JSON under EVAL-TEXT-V1.  
- **Dependency:** D2, D3, ADR-ML-002.

## D5 — Dense Text Retriever (`dense-text-v1`)

- **Purpose:** Baseline B.  
- **Input:** Same documents; selected encoder revision.  
- **Output:** Embeddings + versioned vector index; encoder factory.  
- **Tests:** Normalization, dimension, compatibility validation.  
- **Docs:** ADR-ML-003 dense encoder selection (after measurement).  
- **Evidence:** Benchmark + latency.  
- **Dependency:** D2, D3; candidate shortlist.

## D6 — Hybrid RRF (`hybrid-rrf-v1`)

- **Purpose:** Baseline D; answer RQ1.  
- **Input:** Lexical + dense ranked lists.  
- **Output:** Fusion module; configurable `RRF_K`, candidate cutoffs.  
- **Tests:** Deterministic fusion; unique products; tie policy.  
- **Evidence:** Comparison table A/B/D; per-query wins/losses.  
- **Dependency:** D4, D5.

## D7 — Text Search Service Boundary

- **Purpose:** Injectable service analogous to `VisualRetrievalService`.  
- **Input:** Indexes + query string + top_k.  
- **Output:** Ranked `{product_id, score, source_ranks?}` dataclasses; CLI `query-text`.  
- **Tests:** Contract tests; invalid top_k.  
- **Docs:** Extend `docs/http-integration.md` with `POST /api/v1/search/text`.  
- **Dependency:** D4–D6.

## D8 — Benchmark Report + Failure Analysis

- **Purpose:** Defense evidence for RQ1.  
- **Output:** `reports/text_model_comparison.md`, `reports/text_failure_analysis.md`, JSON artifacts.  
- **Acceptance:** Same eval hash across A/B/D; latency reported; limitations explicit.  
- **Dependency:** D3–D6.

## D9 — Regression + Validation Pack

- **Purpose:** Prove Visual V1 untouched.  
- **Output:** Updated `reports/validation.md`; CI still green for visual markers.  
- **Dependency:** Throughout.

## D10 — Planning Traceability Closeout

- **Purpose:** Link proposal FR/RQ → stories → evidence.  
- **Output:** Updated RTM section in this plan or `reports/traceability_text_v1.md`.  
- **Dependency:** D8–D9.

---

# 9. Work Breakdown Structure

```text
Epic: Text Retrieval V1 (Baselines A/B/D)
  Feature: Production Data Contract
    Story: Lock product ingestion and search metadata boundary
      Task: Separate Product, ProductVariant, Listing, Inventory, and ProductImage ownership
      Task: Define validation, source-of-truth, and re-index rules
      Task: Accept ADR-DATA-001

  Feature: Metadata & Documents
    Story: Audit Khaadi product text fields
      Task: Map CSV columns to the production contract
      Task: Measure sparsity / duplicates / empty descriptions
      Task: Write metadata audit report
    Story: Build product-text-v1 documents
      Task: Define schema + field order policy
      Task: Implement deterministic builder
      Task: Emit versioned artifact + hash
      Task: Unit tests for builder

  Feature: Evaluation Contract
    Story: Design EVAL-TEXT-V1
      Task: Define query classes (exact brand/name, attribute, paraphrase, hard negative)
      Task: Define relevance grades 0/1/2 and product-ID mapping rules
      Task: Produce labeling worksheet + dual-review process
      Task: Freeze YAML + docs (no coding of models yet)
    Story: Create labeled query set
      Task: Draft candidate queries from catalog vocabulary
      Task: Human label + adjudicate
      Task: Freeze query JSON + checksum

  Feature: Lexical Retrieval
    Story: Decide lexical engine (ADR-ML-002)
      Task: Record PostgreSQL FTS as the proposal-faithful Baseline A
      Task: Define schema ownership, configuration, and reproducibility evidence
    Story: Implement lexical retriever
      Task: Shared TextRetriever protocol
      Task: Index build CLI
      Task: Query path + tests

  Feature: Dense Retrieval
    Story: Candidate encoder bake-off
      Task: Shortlist BGE-M3 + ≤1 alternate
      Task: Offline embed latency/size notes
      Task: ADR-ML-003 after EVAL metrics
    Story: Implement dense pipeline
      Task: Encoder adapter + factory
      Task: Catalogue embedding + versioned index
      Task: Exact cosine search + tests

  Feature: Hybrid Fusion
    Story: Implement RRF text hybrid
      Task: RRF with configurable k and cutoffs
      Task: Unique product enforcement
      Task: Comparison CLI A/B/D
      Task: Failure analysis script

  Feature: Service & Integration Contracts
    Story: TextRetrievalService + CLI
      Task: Mirror visual service patterns
      Task: HTTP contract doc for text search
      Task: Contract tests
    Story: Visual regression gate
      Task: Ensure visual tests still pass
      Task: Update validation.md

  Feature: Documentation & Defense Evidence
    Story: Milestone report package
      Task: Comparison + failure reports
      Task: README section for text commands
      Task: Traceability matrix update
```

---

# 10. Jira Backlog

| Key | Title | Value | Acceptance Criteria | Deps | Pri | SP | Owner type | Reviewer | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DATA-1 | Lock production ingestion/search metadata contract | Prevent fixture-driven architecture | Product/Variant/Listing/Inventory/Image split, validation, source of truth, semantic fields, filters, and re-index rules accepted | — | Highest | 2 | Architect/Backend | ML | ADR-DATA-001 |
| TXT-1 | Audit Khaadi metadata for text indexing | Measure fixture fit | Audit maps every source field to ADR-DATA-001 and records complete quality statistics | DATA-1 | Highest | 2 | ML/Data | QA | `product_metadata_audit.*` |
| TXT-2 | Define & build `product-text-v1` | Deterministic docs | Same input → same hash; all products covered or exclusions listed | TXT-1 | Highest | 3 | ML | SE | docs artifact + tests |
| TXT-3 | Author EVAL-TEXT-V1 protocol | Freeze eval | Doc + YAML frozen; metrics listed; labeling SOP | TXT-1 | Highest | 5 | ML/QA | Supervisor optional | `EVAL-TEXT-V1.md` |
| TXT-4 | Label text query set | Ground truth | Dual review policy applied; checksum frozen; **no invented labels** | TXT-3 | Highest | 8 | Team (all) | QA lead | query JSON + adjudication log |
| TXT-5 | ADR-ML-002 PostgreSQL FTS baseline | Proposal alignment | PostgreSQL FTS decision, schema ownership, configuration, and evidence contract recorded | Product documents | Highest | 2 | Architect/ML | Backend | ADR file |
| TXT-6 | Implement lexical retriever Baseline A | Lexical baseline | Index+query; unique products; unit tests | TXT-2,5 | High | 5 | ML | SE | benchmark A |
| TXT-7 | Dense encoder candidates + ADR-ML-003 | Semantic baseline | ≥1 primary candidate measured; revision pinned | TXT-2,3 | High | 5 | ML | SE | ADR + bake-off notes |
| TXT-8 | Implement dense retriever Baseline B | Dense path | Embeddings versioned; compatibility checks; tests | TXT-7 | High | 5 | ML | SE | benchmark B |
| TXT-9 | Implement RRF hybrid Baseline D | RQ1 answer | Same eval hash; comparison table; unique products | TXT-6,8 | High | 5 | ML | QA | comparison report |
| TXT-10 | TextRetrievalService + CLI + HTTP contract | Integrable API | Invalid top_k structured error; product-ID results | TXT-9 | Medium | 5 | ML/SE | Backend | service tests + doc |
| TXT-11 | Failure analysis + latency report | Defense evidence | Per-query failures categorized; p50/p95 defined | TXT-9 | Medium | 3 | ML | QA | failure report |
| TXT-12 | Visual regression + validation update | Protect V1 | Visual markers green; validation.md updated | TXT-10 | Highest | 2 | QA | ML | validation.md |

**Note:** TXT-4 at 8 points is labeling labor — split into draft / label-batch-1 / adjudicate if sprint capacity requires.

---

# 11. Sprint Plan

Assume **2-week sprints**, three members; ML-heavy stories owned primarily by Adeel with Bisma/Erum on labeling, contracts, and backend-readiness for FTS.

### Gate 0 — Production Contract

- **Goal:** Prevent Khaadi fixture structure from defining the production model.  
- **Story:** DATA-1.  
- **Exit gate:** ADR-DATA-001 accepted before metadata audit or builder code.  

### Sprint 1 — Documents + Evaluation Freeze

- **Goal:** Canonical product text exists; EVAL-TEXT-V1 protocol frozen; labeling started.  
- **Stories:** TXT-1, TXT-2, TXT-3, start TXT-4, TXT-5.  
- **Demo:** Show sample product documents + draft queries + ADR-ML-002 draft.  
- **Exit gate:** Metadata audit accepted; document builder tests green; EVAL doc reviewed.

### Sprint 2 — Lexical + Dense Baselines

- **Goal:** Baselines A and B runnable on frozen (or interim labeled subset) queries.  
- **Stories:** Finish TXT-4 (minimum viable labeled set), TXT-6, TXT-7, TXT-8.  
- **Demo:** Side-by-side A vs B on 10 demo queries + metrics on frozen set.  
- **Exit gate:** Both indexes versioned; unit tests pass; visual regression still green.

### Sprint 3 — Hybrid + Service + Evidence

- **Goal:** Baseline D complete; service boundary; RQ1 evidence pack.  
- **Stories:** TXT-9, TXT-10, TXT-11, TXT-12.  
- **Demo:** CLI text query; comparison table A/B/D; no visual regressions.  
- **Exit gate:** Definition of Done for milestone (§18); READY for Baseline E planning.

*(The local database is infrastructure readiness only; do not create FTS tables before the product and document contracts are frozen.)*

---

# 12. Parallel Execution Plan

**Contract-first rule:** Freeze `TextRetriever` protocol, result dataclass, document schema, and EVAL-TEXT-V1 **before** parallel A/B coding.

| Stream | Tasks | Dependencies | Required contract | Output | Integration point | Blocker risk |
| --- | --- | --- | --- | --- | --- | --- |
| A — Retrieval eng. | Lexical + dense impl | Schema + protocol | `TextRetriever`, doc version | Indexes | Hybrid fusion | Medium if protocol drifts |
| B — Evaluation | Query design + labeling | Metadata audit | Relevance SOP | Frozen queries | Benchmarks | **High** if labels delayed |
| C — Platform | Postgres/pgvector readiness | .NET migrations | FTS schema, vector table | DB indexes | Swap lexical/dense stores | Medium (team schedule) |
| D — QA/Docs | Test plan, RTM, validation | Continuous | DoD checklist | Reports | Milestone close | Low |

Avoid parallel fusion coding until A and B share identical rank list schemas.

---

# 13. Dependency Graph

```text
[Hard] ADR-DATA-001 production contract
           ↓
[Hard] Khaadi metadata audit against contract
           ↓
[Hard] product-text-v1 schema + builder
           ↓
[Hard] EVAL-TEXT-V1 protocol ──→ [Hard] Labeled query freeze
           ↓                              ↓
[Hard] ADR-ML-002 lexical engine          │
           ↓                              │
     Lexical index (A) ───────────────────┤
           │                              │
[Soft] Dense candidate bake-off           │
           ↓                              │
     Dense index (B) ─────────────────────┤
           ↓                              │
[Hard] Hybrid RRF (D) ←───────────────────┘
           ↓
[Hard] Comparison + failure analysis
           ↓
[Hard] TextRetrievalService + CLI + HTTP contract
           ↓
[Hard] Visual regression validation
           ↓
[Soft] PostgreSQL FTS / pgvector adapters (when backend ready)
           ↓
[Later] Multimodal late fusion Baseline E
```

- **Hard:** cannot skip.  
- **Soft:** can progress with interim local indexes; must re-verify on authoritative store.  
- **Optional:** Redis cache — proposal optional; not required for V1 correctness.

---

# 14. Architecture Impact

| Area | Gap vs proposal | Classification |
| --- | --- | --- |
| Frontend Next.js | Absent | Later-phase |
| ASP.NET Core backend | Absent | Later-phase (owns auth/catalog) |
| FastAPI AI/ML HTTP | Internal visual-only adapter exists; text/voice/RAG absent | Track B only; no text retrieval unblocking |
| PostgreSQL FTS | Catalog Core available; Search/FTS absent | Implement after fixture parity, ADR-ML-004, and ADR-ML-002 |
| pgvector | Absent | Next-phase adapter after exact local baseline |
| Redis | Absent | Optional |
| API contracts | Visual HTTP V1 versioned/OpenAPI snapshot; text TBD | Future text gate remains blocked |
| AuthZ | Not in ML package | Correct — backend later |
| Product catalogue | CSV demo only | Immediate for documents; transactional catalog later |
| Indexing | Visual only | Immediate text indexes |
| Search | Visual only | Immediate text+hybrid |
| Model serving | In-process | Sufficient for milestone |
| Logging/config/CI | Present for visual | Extend for text |
| Docker platform | Absent | Later-phase |
| Testing | Visual strong | Extend; keep visual regression |

**Search ownership boundary:** ML/search returns product IDs + scores + index/model versions. Backend owns price/stock/auth/eligibility enrichment.

---

# 15. EVAL-TEXT-V1 Plan

## Dataset

- **Frozen authority:** `docs/EVAL-TEXT-V1.md`, `configs/eval_text_v1.yaml` and
  `configs/eval_text_v1.protocol.json`; the precise settings below supersede earlier planning
  suggestions. Protocol freeze is separate from the pending human dataset freeze.
- **Catalog:** `PRODUCT-TEXT-V1`, 400 canonical UUID Products, SHA-256
  `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`.
- **Documents:** `product-text-v1` contains normalized Product Name, Product Description, and optional Color (plus ID/version/checksum). Price, currency, availability, and stock are structured filter metadata. Khaadi must not invent missing category or brand.

## Query structure

Each frozen human query record (labels remain separate):

```text
query_id, query_text, language_tag, query_class, split,
intent_group_id, author_id, authorship
```

## Relevance criteria

- Graded **0 / 1 / 2** per proposal §8.2.  
- Require two independent human grades for every query/Product pair; third-human adjudication
  resolves disagreements. Unjudged is an error, never zero. Canonical Product UUIDs are label
  identities, not external Khaadi IDs. Full schemas: `docs/text-labeling-v1.md`.
- Minimum 40 English-only semantic queries, at least 20 queries/independent intent groups per
  split, disjoint dev/test groups, all five classes represented in each split. Minimum primary
  workload: 32,000 judge rows. Commercial filters and model-generated queries are out of scope.
- **Do not fabricate labels.** Until labels exist, implementation may use synthetic unit fixtures that are **explicitly non-benchmark**.

## Baseline systems

- A Lexical (PG FTS or ADR-approved interim)  
- B Dense only  
- D Hybrid RRF (lexical + dense)

## Metrics (align with proposal + existing visual harness)

Primary: nDCG@10. Report P@1/5/10, Recall@5/10, MRR, nDCG@5/10, HitRate@5 and no-result
rate. Complete-corpus relevance defines Recall/IDCG; binary relevance is grade >= 1.
Quality is query-macro over answerable queries separately per split. Retain zero-relevance
queries and report their diagnostic false-positive rate and explicit N/A quality cohort.
Frozen denominator/tie/uncertainty rules are in the protocol; no metrics are executed yet.

**Thresholds:** Do **not** invent text-only pass/fail thresholds. Establish baselines first. Proposal’s **+10% nDCG@10 vs lexical** applies to **full hybrid configuration (Baseline E)**, not a text-only gate — record text A/B/D honestly.

## Query classes (planned)

1. Exact / near-exact title tokens  
2. Attribute-focused (color, fabric terms present in descriptions)  
3. Paraphrase / situational English  
4. Hard negatives (similar words, wrong product type)  
5. Sparse-description products  

V1 language is frozen to English. Other languages, voice and structured filters need a later
version/protocol; do not mix them into this dataset or claim multilingual support.

## Latency methodology

Pre-registered warmups/repeats/query order, component scopes, linear p50/p95 aggregation and
excluded setup/network/business costs are in `configs/eval_text_v1.yaml` and the protocol.
Timing measurement and retriever execution remain future work.

## Failure analysis

Retain all P@1 misses and low nDCG queries; categorize: vocabulary gap, missing metadata, dense overgeneralization, lexical brittleness, label noise.

## Reproducibility metadata

Dataset version, document version, eval version, model revision, dependency lock/hash, seed, config YAML, source snapshot hash (repo still may lack git — continue package hash practice).

---

# 16. Success Criteria

1. ADR-DATA-001 remains the production ingestion and source-of-truth contract.  
2. `product-text-v1` covers all in-scope products with deterministic hashes and excludes listing state.  
3. EVAL-TEXT-V1 frozen with labeled queries and dual-review policy documented.  
4. Baselines A, B, D executed on **identical** frozen query set.  
5. Metrics + latency published; no cherry-picking.  
6. Hybrid comparison answers RQ1 with evidence (improvement **or** honest non-improvement).  
7. `TextRetrievalService` returns unique product IDs; invalid inputs structured errors.  
8. Visual V1 tests remain passing; EVAL-VISUAL-V1 not invalidated.  
9. ADRs for lexical engine and dense encoder accepted.  
10. HTTP contract for text search documented for .NET integration.  
11. Traceability matrix updated for FR-05, FR-06, RQ1.

---

# 17. Definition of Ready

A story is Ready when:

- Proposal requirement ID mapped  
- In/out scope confirmed for this milestone  
- Inputs available (data, contracts)  
- Acceptance criteria written and testable  
- Dependencies known (hard/soft)  
- Interface/protocol known or scheduled first  
- Test strategy defined  
- No unresolved **blocker** (labels may be in-progress if story is labeling itself)

---

# 18. Definition of Done

- Implementation merged/complete in workspace  
- Acceptance criteria pass  
- Unit tests pass; integration/contract where applicable  
- Code reviewed by second team member  
- Docs/README/ADR updated  
- Evidence artifacts saved under `reports/` / `artifacts/`  
- Jira/status updated  
- No critical visual regression  
- For ML stories: dataset, model, eval, config, reproducibility metadata recorded  

---

# 19. Testing Strategy

| Level | Focus |
| --- | --- |
| Unit | Normalization, document builder, RRF math, metric helpers |
| Integration | Index build → query → unique products |
| Contract | Shared retriever protocol; service dataclasses; HTTP schema examples |
| ML evaluation | EVAL-TEXT-V1 A/B/D only on frozen labels |
| Performance | p50/p95 scopes on controlled catalog |
| Regression | Full visual fast suite + opt-in model smoke |
| Security | Upload/query size limits documented; no auth invented in ML; eligibility deferred to backend |

---

# 20. Risks and Blockers

## Risk register

| Risk | Probability | Impact | Mitigation | Owner |
| --- | --- | --- | --- | --- |
| Weak/short product descriptions | High | High | Field policy honesty; failure analysis; do not invent attributes | ML/Data |
| No graded text labels yet | High | High | Labeling sprint; interim fixtures marked non-benchmark | All |
| Lexical engine ≠ proposal (no Postgres) | High | Medium | ADR-ML-002 interim BM25 + mandatory FTS parity story | Architect + Backend |
| Dense model large / slow on CPU | Medium | Medium | Measure; consider smaller multilingual alt only if justified | ML |
| Hybrid ≤ BM25/FTS | Medium | Medium | Report honestly; tune cutoffs/k only with frozen eval | ML |
| Scope creep into voice/multimodal | High | High | Scope lock §7; supervisor change control | Scrum lead |
| Metadata missing category/brand | Certain | Medium | Document gap; query classes avoid fake facets | Data |
| Integration mismatch with future .NET | Medium | Medium | Product-ID contracts first | SE |

## Current blockers

1. **No human-labeled text relevance set** — blocks *claiming* EVAL-TEXT-V1 results (does not block document builder, protocols, or unit-tested retrievers with synthetic fixtures).  
2. **No Search schema or FTS migration** — Catalog Core V1 is frozen, but Baseline A still waits for fixture parity, the document contract, and ADR-ML-002.

## Not blockers

Dense model choice undecided; visual-only FastAPI independent of text labels; multimodal fusion absent; voice absent.

---

# 21. ADRs Required

| ADR | Decision | Alternatives | Criteria | Resolve by |
| --- | --- | --- | --- | --- |
| ADR-DATA-001 | Product ingestion and search metadata | Product/Variant/Listing/Inventory/Image split vs flat product record | Lifecycle correctness, source of truth, re-index cost | **Accepted with variant addendum** |
| ADR-ML-002 | Lexical engine for Text V1 | PostgreSQL FTS (proposal); rank_bm25 / Whoosh interim; Elasticsearch (out) | Proposal alignment, availability, reproducibility | Before Baseline A “official” numbers |
| ADR-ML-003 | Dense text encoder | BGE-M3; other multilingual embedder | nDCG/MRR on EVAL-TEXT-V1, latency, size, license | After bake-off on frozen eval |
| ADR-ML-004 | Product document construction | Implement ADR-DATA-001 normalization, rendering, and serialization | Conformance and determinism | Before indexing |
| ADR-ML-005 | RRF parameters / cutoffs | Default k=60; BM25_TOP_N / DENSE_TOP_N | Stability on frozen eval; no leaky tuning | Before locking hybrid-rrf-v1 |
| ADR-ML-006 (later) | pgvector schema for text+image | Exact vs HNSW | Recall vs latency | When DB exists |
| ADR-ARCH-001 (later) | FastAPI endpoint packaging | Library-only vs HTTP service | Proposal architecture | Integration phase |

Do not lock ADR-ML-003/005 without measurements.

---

# 22. Documentation Required

1. `docs/ADR-DATA-001-product-ingestion-and-search-metadata-contract.md`  
2. `reports/product_metadata_audit.md`  
3. `docs/EVAL-TEXT-V1.md` + `configs/eval_text_v1.yaml`  
4. ADR-ML-002 … 005 as decided  
5. `reports/text_model_comparison.md` (+ JSON)  
6. `reports/text_failure_analysis.md`  
7. Extended `docs/http-integration.md` (text search)  
8. README text section  
9. Updated `reports/validation.md`  
10. This plan retained as Phase 2 blueprint  
11. Traceability matrix artifact  

---

# 23. Traceability Matrix

| Proposal | Epic | Stories | Implementation (planned) | Test | Evidence |
| --- | --- | --- | --- | --- | --- |
| FR-03/04 product lifecycle | Data contract | DATA-1 | Product/Variant/Listing/Inventory/Image boundary | Future backend contract | ADR-DATA-001 |
| FR-04/05 attributes+index | Documents | TXT-1,2 | Canonical projection + product-text-v1 COMPLETE; indexing NOT STARTED | Pure builder + PostgreSQL projection tests | ADR-ML-004 + product_text_v1_build.md + JSONL/manifest |
| FR-06 typed text | Text Retrieval | TXT-6,8,10 | Lexical+dense+service | Integration | CLI query |
| RQ1 hybrid text | Hybrid | TXT-9,11 | RRF D | EVAL-TEXT-V1 | comparison report |
| §4.6 canonical text | Documents | TXT-2 | Builder | Determinism | artifact |
| §8.1 Baseline A/B/D | Evaluation | TXT-3,4,6,8,9 | Benchmarks | ML eval | results JSON |
| §8.2 relevance/evaluation | Evaluation | TXT-3,4 | Protocol lock + human validators COMPLETE; real labels/results PENDING | Synthetic validator tests only | EVAL-TEXT-V1 + text-labeling-v1 + readiness evidence |
| FR-08 visual | — | Locked | sahulat_visual | Visual suite | ADR-ML-001 |
| FR-09 multimodal | Later epic | — | — | — | After Text V1 |
| NFR-08 reproducibility | All ML | TXT-3,12 | Config+hashes | Validation | validation.md |
| Tech: PG FTS | Lexical | TXT-5,6 | pgfts or interim | Contract | ADR-ML-002 |
| Tech: BGE-M3 | Dense | TXT-7,8 | Encoder | Bake-off | ADR-ML-003 |

```text
Proposal FR-06 / RQ1
        ↓
Epic: Text Retrieval V1
        ↓
Stories TXT-1 … TXT-12
        ↓
product-text-v1 → indexes → RRF → TextRetrievalService
        ↓
Unit + EVAL-TEXT-V1 + visual regression
        ↓
reports/text_model_comparison.md + ADRs
```

---

# 24. Implementation Sequence

```text
1. Confirm Visual V1 regression baseline (tests green) — no code changes
2. Accept ADR-DATA-001 Product/Variant/Listing/Inventory/Image contract (D0)
3. Audit Khaadi as an evaluation fixture against D0 (D1)
4. ADR-ML-004 transformation policy + deterministic builder (D2)
5. EVAL-TEXT-V1 protocol draft (D3)
6. Labeling campaign (minimum viable set) — freeze checksum
7. ADR-ML-002 lexical engine decision
8. Shared TextRetriever protocol + result types (contract-first)
9. Lexical Baseline A
10. Dense candidate bake-off → ADR-ML-003 → Baseline B
11. Hybrid RRF Baseline D + ADR-ML-005 params
12. Benchmark comparison + failure analysis (D8)
13. TextRetrievalService + CLI + HTTP contract (D7)
14. Tests, CI markers, validation.md (D9)
15. Traceability closeout (D10)
16. STOP — plan Baseline E (multimodal late fusion) as separate milestone
```

---

# 25. Implementation Readiness Decision

# READY TO IMPLEMENT

**Why:**

- Proposal and Visual V1 are reconciled; next milestone maps cleanly to Baselines A/B/D and RQ1.  
- Production Product/Variant/Listing/Inventory/Image semantics are locked in ADR-DATA-001; Khaadi exposes a usable evaluation subset.  
- Visual branch is locked; patterns for eval/index/service/CLI are reusable.  
- Remaining uncertainties (labels and PostgreSQL schema ownership) are **managed risks** — not reasons to halt contract, audit, or document work.

**Genuine constraints (do not stop start):**

- Official EVAL-TEXT-V1 **claims** wait on human labels.  
- ADR-ML-004 and canonical documents are complete. Proposal-faithful FTS still waits on
  accepted ADR-ML-002 / lexical configuration; no FTS implementation has started.

---

# 26. Immediate Next Actions

1. **Review canonical build evidence** (`product_text_v1_build.md`, JSONL and manifest).  
2. **Protocol is now pre-registered**; verify with `prepare_text_evaluation.py verify`.
3. **Next human-data gate:** supply genuine queries, freeze intent-disjoint splits, collect
   exhaustive independent judgments and adjudications, then freeze/verify the dataset.
   No synthetic benchmark labels; no automatic retrieval implementation.
4. **Backend track (parallel):** consume frozen DB-CONTRACT-V1; Migration 001 remains the current schema baseline.  
5. **Do not** begin FTS, dense retrieval, RRF, multimodal fusion, voice, or visual reselection.

---

## Discrepancy log (proposal vs Codex milestone)

| Topic | Proposal | Codex / current repo | Resolution |
| --- | --- | --- | --- |
| Product model | Full vendor catalogue lifecycle | Khaadi fixture exposes six metadata fields | Production contract first; fixture maps to a subset and never defines/invents fields |
| Lexical baseline | PostgreSQL full-text search | Catalog Core V1; no Search/FTS schema | Use PostgreSQL FTS after document/lexical ADRs; no official BM25 substitution |
| Next phase wording | Method Iter 1 lexical baseline then multimodal | “Text then hybrid” | Interpret hybrid as **text hybrid (D)** now; multimodal (E) next |
| Visual selection | Better model on local set | OpenCLIP chosen despite slight FashionCLIP metric lead | **Locked** — latency/uncertainty justified in ADR; do not reopen |
| Success +10% nDCG@10 | Full hybrid vs lexical | N/A yet | Do not apply as Text V1 pass gate |
| Workspace | Full platform | ML visual package only | Phase 2 stays ML/search; platform remains parallel |

---

*End of Phase 2 execution blueprint. No implementation was performed while authoring this document.*
