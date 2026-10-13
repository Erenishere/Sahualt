# Sahulat AI

FYP monorepo: customer/vendor commerce workflows with multimodal product search (text, image, voice).

## Overview

Sahulat AI combines a **Next.js frontend**, **ASP.NET Core backend**, and a **Python ML pipeline** (visual, text, voice retrieval). The backend owns business data and orchestration; ML services expose HTTP inference boundaries consumed by the backend only.

## Repository structure

| Path | Role |
| --- | --- |
| `frontend/` | Next.js UI (calls backend API only) |
| `backend/` | ASP.NET Core — auth, catalog, search orchestration, vendor flows |
| `ml-pipeline/` | Existing Python retrieval/evaluation packages (unchanged imports) |
| `infrastructure/` | Docker, Postgres init, Redis, reverse proxy |
| `shared/` | Versioned API contracts and schemas (no business logic) |
| `docs/` | System-wide architecture, FYP, requirements, deployment |
| `scripts/` | Local dev setup and verification |

ML implementation evidence and benchmarks live under **`ml-pipeline/docs/`**, not root `docs/`.

## Technology stack

- Frontend: Next.js, TypeScript
- Backend: ASP.NET Core
- ML: Python 3.12, PostgreSQL, pgvector (prototype indexes)
- Data: PostgreSQL, Redis (planned)

## Running locally (summary)

1. Copy root `.env.example` and configure service URLs.
2. ML pipeline: see [ml-pipeline/README.md](ml-pipeline/README.md).
3. Backend: `dotnet run --project backend/src/SahulatAI.Api`.
4. Frontend: `npm run dev` in `frontend/` (after `npm install`).

Use `scripts/setup-dev.ps1` and `scripts/verify-all.ps1` when wired for your machine.

## Evaluation

- Visual/text/voice **ML protocols** and frozen gates: `ml-pipeline/configs/gates/`, `ml-pipeline/docs/`.
- Text retrieval engineering prototype: **FROZEN** — `python ml-pipeline/scripts/engineering_text_prototype_status.py`.
- Human EVAL-TEXT-V1 collection: `python ml-pipeline/scripts/text_eval_coordinator_status.py`.

## Restructure milestone

See [docs/fyp/repo-structure-v1.md](docs/fyp/repo-structure-v1.md) for REPO-STRUCTURE-V1 definition of done.

The vendor-only assistant follows the [Vendor Business Assistant implementation plan](docs/architecture/vendor-business-assistant-implementation-plan.md). Release 1 covers catalog and stock questions; sales analytics require the later commerce foundation.
