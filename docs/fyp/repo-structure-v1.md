# REPO-STRUCTURE-V1

**Status:** COMPLETE (2026-09-26)

## Definition of done

| Item | Status |
| --- | --- |
| Root `sahulat-ai/` monorepo | Done |
| Legacy ML workspace → `ml-pipeline/` | Done |
| Python package names / imports unchanged | Done |
| ML unit gate (`engineering_text_prototype_status --verify-unit`) | PASS (after `pip install -e .[dev,api,api-test]`) |
| ML fast pytest (`not model/slow/database`) | 806 passed (2 voice-alt failures on this host; investigate separately) |
| `frontend/` skeleton | Done |
| `backend/` solution skeleton | Done |
| `infrastructure/`, `shared/`, root `docs/` | Done |
| Root README, `.gitignore`, `.env.example` | Done |
| CI split (`ml.yml`, `backend.yml`, `frontend.yml`) | Done |
| Benchmark artifacts preserved under `ml-pipeline/artifacts/` | Done |

## Post-move verification (operator)

```powershell
cd C:\Users\LENOVO\Desktop\sahulat-ai\ml-pipeline
$env:TMP = "$PWD\.pytest_tmp"
$env:TEMP = $env:TMP
.\.venv\Scripts\python.exe scripts\engineering_text_prototype_status.py --verify-unit
.\.venv\Scripts\python.exe scripts\text_eval_coordinator_status.py
.\.venv\Scripts\python.exe -m pytest -m "not model and not slow and not database"
```

## Notes

- Open Cursor workspace on **`sahulat-ai`** (or `ml-pipeline` for ML-only work).
- Old path `Desktop\ml pipelinw` is retired; content lives in `ml-pipeline/`.
- Frontend CI requires `frontend/package-lock.json` after first `npm install`.
