# Sahulat AI — Product Retrieval

> **Monorepo path:** `sahulat-ai/ml-pipeline/` (see [MONOREPO.md](MONOREPO.md)). Root README: `../README.md`.

Installable Python retrieval subsystem for Sahulat AI. **Visual Retrieval V1** is
complete and locked. **Text Retrieval V1** is now organized for contract-first
implementation of lexical, dense, and text-hybrid RRF retrieval; those algorithms
and EVAL-TEXT-V1 results are not implemented or claimed yet. Voice search, multimodal
fusion, and commerce business logic remain out of scope.

The Phase 2 scope and sequencing are defined in the
[execution plan](reports/PHASE2_TEXT_RETRIEVAL_EXECUTION_PLAN.md). Repository
boundaries and dependency rules are documented in the
[repository structure](docs/architecture/repository-structure.md).
The production Product/Variant/Listing/Inventory/Image boundary, source-of-truth
rules, and immutable `product-text-v1` content are locked in
[ADR-DATA-001](docs/ADR-DATA-001-product-ingestion-and-search-metadata-contract.md).
Khaadi is an evaluation fixture and does not define the production product model.

Canonical PostgreSQL ingestion and **product-text-v1 construction are verified**. The
fixture-independent builder consumes only Product UUID, Name, Description and applicable
Variant colors, as frozen in [ADR-ML-004](docs/ADR-ML-004-product-text-document-construction.md).
See [build evidence](reports/product_text_v1_build.md). Text retrieval **prototypes** (lexical,
dense, hybrid RRF) are frozen as implementation proof only — see
[ENGINEERING-TEXT-PROTOTYPE-V1](docs/ENGINEERING-TEXT-PROTOTYPE-V1.md).
Official EVAL-TEXT-V1 metrics remain **blocked** until human label freeze.

The initial corpus is formally registered as **PRODUCT-TEXT-V1 / FROZEN** in
[the corpus registry](configs/corpora/product_text_v1.json), with a preserved content-addressed
snapshot. See [corpus identity and verification](docs/PRODUCT-TEXT-V1-CORPUS.md). Corpus freezing
does not freeze EVAL-TEXT-V1 queries or human relevance labels.

The [EVAL-TEXT-V1 protocol](docs/EVAL-TEXT-V1.md) is now independently pre-registered and
checksum-locked. Its [human labeling contract](docs/text-labeling-v1.md) requires real English
queries, dev/test intent separation and exhaustive two-human judgments. Human inputs are
pending; no benchmark labels, rankings or metrics have been generated.
The [human-query workflow](docs/TEXT-QUERY-V1-WORKFLOW.md) extends the existing CLI with
incremental import, complete validation, query-only freeze/verification and neutral status
evidence. No queries or labels are generated; incomplete human collection remains PENDING.
**TEXT-QUERY-V1 tooling is separately FROZEN / GREEN** in its
[software registry](configs/gates/text_query_tooling_v1.json), not a completed query dataset.
Human query data is PENDING (0); query dataset freeze is currently NOT POSSIBLE.
Coordinator materials: [team runbook](docs/EVAL-TEXT-V1-TEAM-RUNBOOK.md),
[checklist](docs/EVAL-TEXT-V1-COORDINATOR-CHECKLIST.md),
`python scripts/export_text_judging_products.py`,
`python scripts/text_eval_coordinator_status.py`,
`python scripts/engineering_text_prototype_status.py`.
The [parallel engineering track](docs/architecture/parallel-engineering-track-v1.md) documents
safe visual/runtime/voice/vendor-assistant boundaries without starting text retrieval.

The independent [VOICE-STT-FOUNDATION-V1](docs/VOICE-STT-FOUNDATION-V1.md) package now provides
bounded PCM WAV ingestion, pinned Whisper large-v3/MMS adapters, normalized transcript checksums,
latency observations and a neutral multilingual evaluation scaffold. Tooling is verified;
the frozen FLEURS model comparison is now executed separately below. No voice-to-search
integration exists. An isolated [Voice HTTP V1](docs/VOICE-HTTP-V1.md)
transcription adapter is now implemented for internal serving, but customer production launch
remains blocked by model, data, integration and deployment gates. Run
`python -m sahulat_voice.cli capabilities`.

The separate [EVAL-VOICE-V1](docs/EVAL-VOICE-V1.md) preregisters Google FLEURS test speech:
50 English, Urdu, Sindhi and Pashto recordings each. Offline preparation preserves published
reference scripts and selected originals, converts to the existing PCM16 runtime format,
and anchors the 200-sample bundle in an external checksum registry. See
[voice dataset acquisition validation](reports/voice_dataset_acquisition_v1_validation.md):
all four pinned archives are verified and the actual 200-recording bundle is FROZEN, with
50 recordings per language and byte-identical rebuild verification.
Use `python scripts/prepare_voice_evaluation.py verify` to verify a locally prepared frozen
bundle; `acquire --allow-download` explicitly fetches approximately 1.37 GB of pinned test
archives. No train/dev audio or model weights are fetched. Dataset freeze is not an STT
accuracy result; neither recognizer is executed by preparation tooling.

[EVAL-VOICE-RUN-V1](docs/EVAL-VOICE-RUN-V1.md) executes the two pinned existing adapters
offline on the same frozen 200 recordings, without tuning or benchmark changes. See
[comparison evidence](reports/eval_voice_run_v1.md) for WER/CER, retained failures,
separate cold/warm timing observations and operational-delay limitations. Run
`python scripts/run_voice_evaluation.py verify` to validate existing result artifacts;
`run` refuses repeated scored execution. MMS remains research-only; no production
recognizer is selected and voice is not connected to search.

[EVAL-VOICE-CORPORA-V2](docs/EVAL-VOICE-CORPORA-V2.md) is a separate metadata-first
gate for UrduSpeech, Common Voice 27 Sindhi, a proposed South Asian English subset,
the Pashto Audio-Visual Corpus, and the pending fresh-human Sindhi holdout. It pins
source identities and creates deterministic selection previews without downloading
audio, running models, changing frozen V1 evidence, or authorizing fine-tuning.
The immutable [audio-acquisition readiness amendment](docs/EVAL-VOICE-CORPORA-V2-ACQUISITION.md)
pins the verified South Asian English dataset ID, classifies UrduSpeech transcript-field
differences, audits cross-subset speaker labels and checkpoint exposure, and keeps the
gate `BLOCKED` until rights, adjudication, and selected manifests are complete.

```powershell
python scripts/prepare_text_evaluation.py preregister
python scripts/prepare_text_evaluation.py verify
python scripts/prepare_text_evaluation.py query-status
python scripts/freeze_text_query_tooling.py --verify-only
```

## Build canonical text documents (no retrieval)

Use Python **3.12** (Unicode 15.0.0) and verified database configuration from `.env`:

```powershell
python scripts/build_product_text_v1.py
# Optional: also verify the existing frozen fixture's ingestion lineage.
python scripts/build_product_text_v1.py --verify-khaadi-lineage
```

The read-only command builds `artifacts/product_documents/product-text-v1.jsonl`, its
deterministic manifest/checksums and verification evidence. It includes non-archived draft
Products for evaluation; it does not activate listings or implement search. PostgreSQL
remains business truth. No Listing, Inventory, image or external-ref dependency exists in
the canonical builder/loader. Missing optional Color is omitted, not inferred.

## Repository structure

```text
src/
  sahulat_api/             # Optional internal visual-only HTTP adapter
  sahulat_database/        # Frozen migrations, schema and integrity verification
  sahulat_visual/          # Locked Visual Retrieval V1
  sahulat_text/            # Text Retrieval V1 feature boundary
    contracts.py           # Stable product-ID retrieval contracts
    ingestion/             # Canonical write inputs, PostgreSQL adapter, fixture mapping
    documents/             # product-text-v1 construction
    retrievers/
      lexical/             # PostgreSQL FTS baseline
      dense/               # Dense-text baseline
      hybrid/              # Text-only RRF baseline
    evaluation/            # Protocol/human-input validation; metrics runners remain future
    service/               # Application-facing orchestration
tests/
  unit|integration|model/  # Locked visual regression tests
  text/unit/               # Text contract and feature tests
configs/                   # Versioned evaluation/runtime configuration
docs/                      # Protocols, ADRs, integration, architecture
reports/                   # Human-readable and machine-readable evidence
scripts/                   # Offline data/evaluation utilities
```

The text package must return product IDs and retrieval evidence only. A future
backend remains responsible for authentication, authorization, catalogue truth,
price/stock eligibility, and response enrichment.

OpenCLIP is the initial CPU serving choice recorded in
[ADR-ML-001](docs/ADR-ML-001-visual-encoder-selection.md). FashionCLIP has a small
numerical quality advantage in the executed paired benchmark; OpenCLIP had lower
warm latency. This is a deployment trade-off, not a universal model-superiority
claim. See [comparison](reports/visual_model_comparison.md) and
[evaluation protocol](docs/EVAL-VISUAL-V1.md) for evidence and limitations.

## Setup

The base/Visual package supports Python 3.11–3.13; `product-text-v1` builds require
Python 3.12 / Unicode 15.0.0. This workspace uses Python 3.12. Use a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev,ml]'
```

If PowerShell activation is disabled, use `.venv\Scripts\python.exe` in place of
`python`. On Linux/macOS activate with `source .venv/bin/activate`.
Fast checks only require `python -m pip install -e '.[dev]'`; no model downloads.
Important direct dependencies are pinned in `pyproject.toml`. A resolved environment
snapshot is saved in reports after successful installation. CUDA installation may
require a PyTorch wheel compatible with the host driver: record the exact resolved
version/device and rerun both benchmarks after any runtime change.

The executed Windows CPU environment is pinned in `requirements-validated.txt`:
`python -m pip install -r requirements-validated.txt`, then `python -m pip install -e .`.
This lock is an environment snapshot, not a claim of cross-platform wheel availability.
It pins the verified Windows CPython 3.12 CPU wheel directly from the official
PyTorch host, including its SHA-256, to avoid the mirror failure observed here.
Model tests passed using the local
checkpoint cache with `HF_HUB_OFFLINE=1`; set that variable after initial downloads
for offline benchmark execution.

Model downloads require access to Hugging Face; the data importer uses Kaggle's
public download API. No credentials are embedded or required by the public importer.
If access is denied, obtain the dataset yourself under its distribution terms and
pass `--archive`. Models and data are ignored by Git. Do not commit large weights.

## Dataset and frozen split

```powershell
python scripts/prepare_khaadi.py
python -m sahulat_visual audit-dataset --config configs/eval_visual_v1.yaml --output reports/dataset_audit.json
python -m sahulat_visual freeze-eval --config configs/eval_visual_v1.yaml --output reports/dataset_audit.json
```

The importer validates the v1 archive checksum, safely extracts into
`data/raw/khaadi`, reads `Khaadi_Data/khaadi_data.csv` and writes
`data/khaadi/manifest.json` and `source.json`. The audit reports all exclusions.
The frozen split is `artifacts/eval_visual_v1/split.json`. Preserve it with the audit
and YAML before model comparison; benchmark runs validate rather than generate it.
YAML paths resolve relative to the config file. CLI manifest/root paths resolve
relative to the working directory. No machine-specific absolute paths are required.

For another catalogue, provide an explicit JSON array:

```json
[
  {"image_id": "SKU123/front", "product_id": "SKU123", "image_path": "SKU123/front.jpg"},
  {"image_id": "SKU123/back", "product_id": "SKU123", "image_path": "SKU123/back.jpg"}
]
```

Paths must stay within `--root`; product IDs are authoritative metadata. Files are
validated by decoded content, not filename extension. Missing labels and corrupt
images are audited before indexing. An image becoming invalid/changed after audit
fails the build/run rather than silently altering the population.

## Benchmark both candidates

```powershell
python -m sahulat_visual benchmark-visual --model openclip --config configs/eval_visual_v1.yaml --output artifacts/benchmarks/openclip
python -m sahulat_visual benchmark-visual --model fashionclip --config configs/eval_visual_v1.yaml --output artifacts/benchmarks/fashionclip
python -m sahulat_visual compare-models --openclip artifacts/benchmarks/openclip/results.json --fashionclip artifacts/benchmarks/fashionclip/results.json --output reports/visual_model_comparison.md
```

Run candidates sequentially on the same otherwise idle device; `--device cpu`
can force CPU. The benchmark freezes batch size/workers in YAML; environment
batch settings apply to catalogue builds, not override benchmark controls.
Results contain all six image-level metrics, latency distributions, identities,
dependency/device/source metadata, audit, split, per-query rankings, failures and a
gallery-only index. `compare-models` rejects mismatched protocol/dataset/split hashes.
These are new-split results; the historical query/gallery artifact was not supplied.

Review `failures.json` with query images and matching catalogue images before
assigning categories. Every incorrect P@1 or incomplete Recall@5 is retained;
do not cherry-pick. High R alone can limit Recall@5. Empty categories mean
**unreviewed**, not an inferred visual explanation. See the protocol for formulas,
timing scopes and known leakage limitations.

Generate local visual review cards with:
`python scripts/review_failures.py --benchmark artifacts/benchmarks/openclip --root data/raw/khaadi --output artifacts/benchmarks/openclip/review.html`.
The display selects the first 20 incorrect P@1 queries by ID. It does not remove
queries, change metrics, or automatically assign subjective labels.

## Build catalogue index and query

```powershell
python -m sahulat_visual build-visual-index --model openclip --manifest data/khaadi/manifest.json --root data/raw/khaadi --dataset-version khaadi-v1 --output artifacts/catalogue-openclip.npz
python -m sahulat_visual query-image --model openclip --index artifacts/catalogue-openclip.npz --image data/raw/khaadi/Khaadi_Data/images/ACA231001/image_0.jpg --top-k 5
```

Use `--model fashionclip` and a separate output for FashionCLIP. The full catalogue
build contains all audited views, suitable for serving. A query using an indexed
catalogue image is a smoke test, **not** an evaluation of unseen-query quality.

## Python service

```python
from dataclasses import asdict
from pathlib import Path
from sahulat_visual.config import Settings
from sahulat_visual.encoders import create_encoder
from sahulat_visual.index import InMemoryVectorIndex
from sahulat_visual.retrieval import VisualRetrievalService

settings = Settings.from_env()
encoder = create_encoder(settings)  # once per service process
index = InMemoryVectorIndex.load(Path("artifacts/catalogue-openclip.npz"))
service = VisualRetrievalService(encoder, index, settings.image_top_k)
results = service.search(Path("query.jpg"), top_k=settings.product_top_k)
response = [asdict(result) for result in results]
```

Safe decode → checkpoint-specific preprocessing → frozen encoder → normalized
vector → cosine image neighbors → MAX per product → unique ranked products.
Query/catalogue use the same encoder. Service results are dataclasses containing
IDs, float scores and best-matching paths, not tensors. Neighbors expand until
enough unique products are found or the catalogue is exhausted, including boundary
ties for deterministic ordering. Fewer products than requested is valid only when
the catalogue contains fewer unique products.

Cosine scores are similarity values, not calibrated probabilities.

The NPZ index uses no pickle, validates dimensions and full encoder identity, and
is atomically replaced on disk. It is intended for controlled, locally generated
artifacts, not untrusted uploaded NPZ files. It stores float32 vectors, image/product
metadata, model/revision/preprocessing/embedding version, dataset version and creation
time. Never mix incompatible vector spaces. Full exact search is O(ND), suitable
for a baseline; validate a pgvector/ANN adapter against it before scaling.

## Configuration and integration

See `.env.example`: `VISUAL_MODEL`, `VISUAL_DEVICE`, `VISUAL_BATCH_SIZE`,
`VISUAL_NUM_WORKERS`, `VISUAL_PRODUCT_TOP_K`, `VISUAL_IMAGE_TOP_K`, `VISUAL_CACHE_DIR`.
Values come from process environment; `.env` is not automatically loaded.
Embedding versions are derived from immutable weights plus preprocessing and
relevant dependency identities; an arbitrary environment label cannot bypass
compatibility validation. Model selection is centralized in one factory.

Catalog Core PostgreSQL migrations, canonical fixture ingestion and read-only text document
construction are implemented in separate database/text packages. The locked visual package
still uses a `VectorIndex` protocol and [HTTP/pgvector contract](docs/http-integration.md)
as its integration boundary; no pgvector adapter is implemented.
The optional `sahulat_api` adapter now exposes internal health/readiness and image search,
without changing Visual V1. See [Visual HTTP V1](docs/API-VISUAL-V1.md) for pinned asset setup,
upload/concurrency limits, safe errors and explicit external-to-canonical ID resolution.
Install `.[api,api-test,dev]` and use `python -m sahulat_api --port 8000` after provisioning
the required process settings/cache. The CLI binds loopback only; it is not an authenticated
public API and does not open PostgreSQL or load `.env`.
The actual parent backend must own authentication and enrich product IDs. No
upload persistence or second identity system is introduced.

## Validation

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -m 'not model and not slow and not database'
$env:RUN_DATABASE_TESTS='1'
python -m pytest tests/database
$env:RUN_MODEL_TESTS='1'
python -m pytest -m model
```

CI runs fast unit/integration tests without ML dependencies. Model tests are opt-in
and may download large pretrained weights. Test doubles are explicitly synthetic
and their outputs never establish benchmark performance. Database/projection/fixture tests
use isolated temporary databases after Migration 001; synthetic endpoint and canonical-ID
integration tests now cover the separate visual HTTP adapter. Text retrieval remains blocked
pending genuine human query/relevance freezes; no HTTP route exposes text evaluation data.
See `reports/product_text_v1_validation.md` for current document-gate verification and
`reports/validation.md` for
checks actually executed in this workspace and unresolved environment failures.
