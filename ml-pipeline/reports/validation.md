# Executed validation — 2026-09-06

Environment: Windows 11, Python 3.12.10, PyTorch 2.10.0+cpu, eight PyTorch threads.
Exact package versions: [environment.json](environment.json) and
`requirements-validated.txt`. No GPU, database, API host or Git checkout was present
in the supplied workspace. Source hash for both benchmark runs and the final package:
`0e797686bc6b051654f24927ca30961c862bdf0a3e8fbf3c9eafdff6820255e3`.
The source/config/environment snapshot is `visual_source_snapshot.zip`.

## VERIFIED

| Check | Executed result |
| --- | --- |
| `python -m ruff check .` | Pass |
| `python -m ruff format --check .` | 34 Python files formatted |
| `python -m mypy` | No issues in 24 package source files, with ML dependencies installed |
| `python -m pip check` | No broken requirements |
| Fast pytest selection | 63 passed, 2 deselected: 58 unit + 5 local integration |
| Pretrained pytest selection, `RUN_MODEL_TESTS=1` | 2 passed, 63 deselected |
| Combined executed tests | 65 passed; no failures, errors or skipped tests in the selected groups |
| Public Khaadi import | Archive hash verified; 400 products and 2,109 images |
| Dataset audit | 2,093 retained; 1 within-product duplicate and 15 conflicting images removed |
| EVAL-VISUAL-V1 split | 399 queries / 1,694 gallery; content and protocol hashes frozen |
| OpenCLIP benchmark | All 399 queries evaluated; 1,694 vectors, 512 dimensions |
| FashionCLIP benchmark | All 399 queries evaluated; identical audit/split/source/dependencies |
| Comparison + paired bootstrap | JSON and Markdown reports generated |
| Failure review | Every weak/error query saved; first five incorrect P@1 pairs per model visually reviewed |
| Full catalogue CLI build | 2,093 OpenCLIP vectors; index saved and reloaded |
| CLI sample query | 5 unique products, correct catalogue product first, float scores |
| FashionCLIP service parity | 5 unique products; product/image IDs and scores match saved benchmark ranking |
| CLI invalid `top_k=0` | Structured error and exit code 2 before model loading |
| Source/metadata review | Package source matches both executed source hashes; no developer-specific paths or credentials in code |

JUnit records: [fast-tests.xml](fast-tests.xml), [model-tests.xml](model-tests.xml).
The pretrained tests verify finite normalized 512-D features and batch/single-image
agreement for both real checkpoints. Lightweight test encoders are explicitly
fixtures; no synthetic performance is mixed with the model reports.

The full catalogue artifact is `artifacts/catalogue-openclip.npz`, identity
`openclip-vit-b32-1a25a446712b-af731563a693-v1`. It contains all audited products and
views; benchmark indexes contain only gallery views. The sample CLI query used
`ACA231001/image_0.jpg` and returned `ACA231001` first with score 1.0 and five
distinct product IDs. This self-match is a smoke test, not a quality benchmark.
Exact response: [sample_query.json](sample_query.json).

## Commands executed

Commands below assume the project virtual environment is active. On this Windows
workspace the equivalent `.venv\Scripts\python.exe` executable was used.

```powershell
python scripts/prepare_khaadi.py
python -m sahulat_visual freeze-eval --config configs/eval_visual_v1.yaml --output reports/dataset_audit.json
$env:HF_HUB_OFFLINE='1'
python -m sahulat_visual benchmark-visual --model openclip --device cpu --config configs/eval_visual_v1.yaml --output artifacts/benchmarks/openclip
python -m sahulat_visual benchmark-visual --model fashionclip --device cpu --config configs/eval_visual_v1.yaml --output artifacts/benchmarks/fashionclip
python -m sahulat_visual compare-models --openclip artifacts/benchmarks/openclip/results.json --fashionclip artifacts/benchmarks/fashionclip/results.json --output reports/visual_model_comparison.md
python -m sahulat_visual build-visual-index --model openclip --device cpu --manifest data/khaadi/manifest.json --root data/raw/khaadi --dataset-version khaadi-v1 --output artifacts/catalogue-openclip.npz
python -m sahulat_visual query-image --model openclip --index artifacts/catalogue-openclip.npz --image data/raw/khaadi/Khaadi_Data/images/ACA231001/image_0.jpg --top-k 5
python -m pytest -m 'not model and not slow and not database' --junitxml=reports/fast-tests.xml -q
$env:RUN_MODEL_TESTS='1'
python -m pytest -m model --junitxml=reports/model-tests.xml -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
```

## Boundaries and limitations

* The original historical split and exact checkpoint/metric implementation were
  unavailable. New-split benchmarks were executed; historical scores were not
  reproduced or substituted. The observed singleton may explain the historical
  one-image count gap if earlier experiments discarded singleton products, but
  that is an inference, not a verified historical method.
* CPU execution was verified. CUDA, MPS, XPU, Linux and other Python versions were
  not exercised. Host memory/peak RSS and a GPU memory/latency benchmark were not
  performed. Timing is one sequential run per model; thermal/background load was
  not controlled, and no production SLO is claimed.
* No PostgreSQL/pgvector or HTTP implementation was applicable to the empty
  workspace. The index protocol, Python service and HTTP integration contract are
  implemented/defined; database and endpoint tests remain inapplicable until the
  parent service is connected. There is no API startup command.
* Exact hashing does not exclude every perceptual near duplicate or establish
  absence of model pretraining overlap. Only five error pairs per model received
  visual annotations; other failures remain explicitly unreviewed. Causal model/
  background effects and customer-photo generalization are unproven.
* No fine-tuning, external deployment, Git commit, branch or push was performed.
  Git diff checks were unavailable because this directory is not a Git repository;
  source checks, lint, types, executed tests, and artifact/source-hash review were used.

Dependency downloads initially timed out. Both model checkpoint files were later
downloaded and SHA-256-verified. An alternate PyTorch mirror returned HTTP 403 even
outside the sandbox; the official `download.pytorch.org` CPU wheel succeeded and
its published checksum was verified. These setup failures were resolved before
the reported model tests and benchmarks; they are not hidden passing checks.
