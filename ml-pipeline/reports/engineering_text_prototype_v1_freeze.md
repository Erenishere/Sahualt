# Engineering text prototype V1 — freeze snapshot

**Frozen:** 2026-09-26  
**Registry:** `configs/gates/engineering_text_prototype_v1.json`

## Summary

Parallel engineering track for text retrieval prototypes **A (lexical FTS)**, **B (dense pgvector
toy encoder)**, and **D (hybrid RRF)** is complete at prototype depth. Further retrieval code
changes are deferred until **EVAL-TEXT-V1 human label freeze**.

## Verification recorded in-repo

| Check | Result |
| --- | --- |
| Unit tests (`lexical`, `dense`, `hybrid`, `rank_fusion`) | PASS (30 tests) |
| Corpus mismatch guard (`HybridRRFRetriever`) | PASS (unit) |
| Toy PostgreSQL smoke (lexical / dense / hybrid) | **Operator** — run on host with `psql` + pgvector |

Automated agents on locked-down Windows hosts may fail DB smoke with `WinError 4551` (Application
Control blocking `psql`). That does not reopen prototype development; run smokes locally and attach
PASS output to team notes if required.

## Official benchmark

| Gate | Status |
| --- | --- |
| EVAL-TEXT-V1 metrics / qrels-driven eval | BLOCKED |
| Reason | `HUMAN_LABEL_FREEZE_PENDING` (0/40 queries; labels not frozen) |

## Human workflow (active)

See [docs/ENGINEERING-TEXT-PROTOTYPE-V1.md](../docs/ENGINEERING-TEXT-PROTOTYPE-V1.md) and
[docs/EVAL-TEXT-V1-TEAM-RUNBOOK.md](../docs/EVAL-TEXT-V1-TEAM-RUNBOOK.md).
