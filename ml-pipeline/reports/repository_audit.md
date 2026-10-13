# Repository audit

The supplied workspace was inspected before implementation on 2026-09-06.
`Get-ChildItem -Force` and `rg --files` found no files, including hidden files.
`git status --short` reported that this is not a Git repository.
Python 3.12.10 was available; pip was the only installed package.

## Existing architecture and relevant files

No source, Python packages, notebooks, dependency manifests, model loaders,
preprocessing, evaluation scripts, datasets, split manifests, reports, tests,
FastAPI app, PostgreSQL/pgvector integration, migrations, Docker or CI existed.
The broader Sahulat AI architecture is known only from the task description.

## Reusable components

None are present in this workspace. No existing files were removed or replaced.
The historical benchmark is contextual evidence, not executable evidence.

## Problems and reproducibility gaps

There is no historical query/gallery manifest, duplicate audit, dataset checksum,
checkpoint identifier, dependency lock, or metric definition to verify. Therefore
the supplied historical results cannot be reproduced exactly or used to select
a production encoder. Duplication, metric errors and model coupling in prior
experiments cannot be assessed without their source.

## Proposed changes

Create one installable `src/sahulat_visual` package; model-specific adapters with
one factory; safe image validation; manifest-based audit; frozen evaluation
configuration and content-bound splits; local exact cosine index; catalogue
pipeline; unique-product max aggregation; injectable retrieval service; canonical
benchmark and comparison commands; tests, CI, documentation and a selection ADR.

Use a local index protocol as the future pgvector boundary. No database or HTTP
server is added without an existing integration architecture. Document the HTTP
contract for the parent backend. Pin pretrained checkpoint revisions, preserve
all objective exclusions, and distinguish new evaluation from historical results.
