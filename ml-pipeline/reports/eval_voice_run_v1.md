# EVAL-VOICE-RUN-V1

Gate status: GREEN. Execution evidence and final regression validation: VERIFIED.
This report contains actual decoder/scoring evidence, not estimated model results.

## Authority and dataset integrity

The accepted execution policy is [EVAL-VOICE-V1](../docs/EVAL-VOICE-V1.md), with
unchanged [configuration](../configs/eval_voice_v1.json) and existing
[VOICE-STT-FOUNDATION-V1 adapters](../docs/VOICE-STT-FOUNDATION-V1.md).
The isolated [run boundary](../docs/EVAL-VOICE-RUN-V1.md) is implementation documentation,
not a protocol amendment or model-selection decision.

| Identity | Verified value |
| --- | --- |
| Dataset | FLEURS-VOICE-V1 / FROZEN |
| Samples | 200; exactly 50 en, 50 ur, 50 sd, 50 ps |
| Manifest SHA-256 | `e2efd78d0af8fe8ecc2c6483ab7db0ff9dba6763fd148be58bbc6c4fd05499e4` |
| Semantic dataset SHA-256 | `7ab3516ef5a1bcc735bfb833f24c818015970b5bfc7bc4b138579c7c11d059a2` |
| Protocol registry checksum | `28c98d02effdefd46cc87e67f2d7c99512246ce553709b246b9848f9d142eb17` |
| Source lock SHA-256 | `8d455480cffd08d82616dab1e878c6f5b3b481cdbc08e412c6ac1b461cc65664` |
| FLEURS revision | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` |
| Canonical bundle | `artifacts/voice_evaluation_v1/`; 410 files, including the manifest and its 409 indexed files |

Full verification ran before execution, before each model, after each completed model and
on result verification. It checks every audio identity/hash, published reference, declared
language, lineage, source subset selection, conversion parity, external registries and frozen
normalization/scoring policy. No preparation/freeze regeneration was performed in this gate.
The frozen acquisition descriptor retains its historical `model_results: NOT_RUN` field;
it is deliberately not rewritten. The new run artifacts separately record both models as
`EXECUTED`, preserving the preregistered dataset checksum.

## Models and environment

| Model | Repository | Exact revision | Primary checkpoint SHA-256 |
| --- | --- | --- | --- |
| Whisper large-v3 | `openai/whisper-large-v3` | `06f233fe06e710322aca913c1bc4249a0d71fce1` | `a8e94b85976e5864ba3e9525c7e6c83b2a1eca42d4b797a0c7c24d778e40fd95` |
| MMS-1B-All | `facebook/mms-1b-all` | `3d33597edbdaaba14a8e858e2c8caa76e3cec0cd` | `0f1d95ce43d27e03d5d8dd56c697c805460f967c793dd2cbec2e8e8012deda98` |

Required public safetensors/config/tokenizer assets were acquired and whole-file verified
before inference. Four exact MMS language heads were included. Network range retries occurred
only in acquisition, not model inference, and used the same pinned assets. No pickle weights,
other revision, fallback model, dependency installation or dependency upgrade was used.

Both fresh model processes report the same environment:

- Windows / AMD64; `AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD`; 16 logical CPUs.
- CPU / float32; PyTorch intra-op and inter-op thread counts both 8.
- Python 3.12.10; Unicode 15.0.0; NumPy 2.2.6.
- torch 2.10.0+cpu; transformers 4.57.6; huggingface_hub 0.36.2;
  safetensors 0.7.0; tokenizers 0.22.2.

The existing model-specific preprocessing/decoding is unchanged. Whisper uses declared
`en/ur/sd/ps`, task `transcribe`, greedy deterministic decoding (`do_sample=False`,
`num_beams=1`, `max_new_tokens=256`, no timestamps). MMS uses its frozen CTC argmax path
and `eng/urd-script_arabic/snd/pus` mappings respectively. Same prepared PCM16 waveform;
no conversion, resampling, VAD, denoising, translation or transcript correction during execution.

## Primary WER/CER

Each language uses micro edit errors divided by reference words/codepoints. Primary scoring
uses the existing frozen view: NFC/control/whitespace normalization, casefold, Unicode
punctuation-to-space, whitespace collapse. CER includes normalized spaces. There is no second
NFC transformation after casefold. All failures remain in denominators as full reference
deletions; no success-only accuracy and no clamping. Percentages below are display rounding;
machine artifacts retain full counts and unrounded rates.

| Language | Model | Word errors / reference words | WER % | Character errors / reference characters | CER % | Success / failed |
| --- | --- | --- | ---: | --- | ---: | --- |
| English | Whisper | 53 / 1,194 | 4.4389 | 122 / 6,961 | 1.7526 | 50 / 0 |
| English | MMS | 158 / 1,194 | 13.2328 | 338 / 6,961 | 4.8556 | 50 / 0 |
| Urdu | Whisper | 300 / 1,447 | 20.7326 | 484 / 6,601 | 7.3322 | 50 / 0 |
| Urdu | MMS | 421 / 1,447 | 29.0947 | 637 / 6,601 | 9.6501 | 50 / 0 |
| Sindhi | Whisper | 1,214 / 1,196 | 101.5050 | 5,049 / 5,548 | 91.0058 | 47 / 3 |
| Sindhi | MMS | 288 / 1,196 | 24.0803 | 484 / 5,548 | 8.7239 | 50 / 0 |
| Pashto | Whisper | 1,178 / 1,304 | 90.3374 | 2,051 / 5,892 | 34.8099 | 50 / 0 |
| Pashto | MMS | 563 / 1,304 | 43.1748 | 998 / 5,892 | 16.9382 | 50 / 0 |

The only overall accuracy aggregate is the preregistered equal-language macro of the four
per-language micro rates, not a pooled word/character denominator:

| Model | Macro WER % | Macro CER % | Successful / failed / total |
| --- | ---: | ---: | --- |
| Whisper | 54.2535 | 33.7251 | 197 / 3 / 200 |
| MMS | 27.3957 | 10.0419 | 200 / 0 / 200 |

Whisper has lower WER/CER on this English and Urdu subset; MMS has lower WER/CER on this
Sindhi and Pashto subset and a lower equal-language macro rate. These are released-model
benchmark observations, not production approval or a claim of equal unseen training exposure.
No confidence intervals, new weighting, tuning or significance claim is added.

## Failures and attempts

Both base loads and all language preparation/head loads succeeded. Whisper recorded exactly
three scored `inference_failed` errors, all Sindhi:

- `fleurs_sd_in_11479113766193837723`
- `fleurs_sd_in_14561229053886069169`
- `fleurs_sd_in_5554880600795493994`

Their stage is `scored_call`; decoder/transcript unavailable fields are null, not fabricated
text. They retain measured failed-call STT time and full-reference-deletion scoring. The
typed code does not establish a finer root cause; this report does not invent one.
Sindhi WER above 100% is valid edit-count evidence and remains unclamped.

Exactly one first-seeded-selected warmup per language/model was used, excluded from primary
scores and warm latency distributions. Whisper's Sindhi warmup failed with `inference_failed`;
the other three Whisper and all four MMS warmups succeeded. The failed warmup was not replaced
or retried. The same selected sample later received its single scored call, as preregistered.
There were 400 scored calls plus 8 mandated unscored warmups, with zero inference retries.

Two existing opt-in adapter smoke tests use a separate one-record English input selected
before any model output (`smoke-selection.json`). These are unscored regression checks only,
not new benchmark attempts, transcript replacement or an additional 200-sample evaluation.
Their final status is included in validation below.

## Latency observations

All 50 attempted scored calls per language/model, including Whisper's three failures, are
timed. Loads and warmups are excluded. Values are seconds below for readability; original
STT milliseconds are preserved. RTF is STT seconds divided by that sample's audio seconds.

| Language | Model | Mean STT s | Median STT s | p95 STT s | Mean RTF | Median RTF | p95 RTF |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| English | Whisper | 155.177 | 25.201 | 36.703 | 15.447 | 2.650 | 4.780 |
| English | MMS | 21.976 | 11.814 | 23.106 | 2.395 | 1.078 | 1.333 |
| Urdu | Whisper | 46.975 | 44.679 | 67.405 | 4.951 | 4.738 | 6.348 |
| Urdu | MMS | 10.122 | 9.641 | 16.219 | 1.029 | 1.012 | 1.215 |
| Sindhi | Whisper | 79.518 | 67.702 | 135.404 | 6.930 | 6.507 | 9.945 |
| Sindhi | MMS | 108.147 | 14.620 | 24.505 | 12.048 | 1.224 | 1.436 |
| Pashto | Whisper | 47.938 | 43.774 | 69.818 | 3.935 | 3.949 | 5.256 |
| Pashto | MMS | 23.610 | 10.959 | 21.687 | 2.095 | 0.927 | 1.233 |

Important operational limitation: elapsed-time stalls affected this run. Retained successful
observations include Whisper English 5,792.782 s and 718.783 s, MMS Sindhi 4,676.024 s,
MMS Pashto 589.800 s and MMS English 504.850 s. Their cause was not independently established;
system suspension/scheduling interruptions cannot be ruled out. No observation was removed,
trimmed, retried or corrected. Means/RTF are particularly affected. These are actual elapsed
observations on a non-isolated Windows workstation, not validated steady-state service latency,
an SLO or evidence for a deployment choice. Medians/p95 are reported under the same fixed policy,
not used to hide or replace the means. No pooled/weighted cross-language latency score is added.

Fresh-process base loads were 25.146 s for Whisper and 26.643 s for MMS, entirely separate
from scored latency. These are cached-weight loads, not network downloads or a cleared
filesystem-cache experiment. MMS language-head loads were en 120.736 ms, ur 144.127 ms,
sd 101.528 ms, ps 71.626 ms. Whisper language preparation is a no-op, not another weight load.

| Language | Whisper unscored warmup s / status | MMS unscored warmup s / status |
| --- | --- | --- |
| English | 45.124 / SUCCESS | 20.150 / SUCCESS |
| Urdu | 38.362 / SUCCESS | 5.761 / SUCCESS |
| Sindhi | 126.252 / FAILED | 27.630 / SUCCESS |
| Pashto | 37.660 / SUCCESS | 6.279 / SUCCESS |

## Reproducibility and artifacts

`scripts/run_voice_evaluation.py run` completed with exit 0 and `EVIDENCE_VERIFIED`.
`verify` independently completed with exit 0, without constructing/calling a model or
rewriting any result. It recomputes the frozen corpus identities, normalized transcripts,
per-record checksums/scores, language/macro summaries, semantic hashes, implementation
fingerprints, warmup structure and checksum-anchored comparative manifest.

| Evidence | SHA-256 |
| --- | --- |
| Whisper result file | `ec6a5ec25f684c7afc9a0313e5da0813da94b1b8d92543f9dc57c09820cb86df` |
| Whisper semantic results, excluding timing | `9777432a5c5f677dcff4aa11aad155602d1ba39eed0eea9b3628ca18a16791ed` |
| MMS result file | `f617a2c63d64962e914b82f149afb8b3a4c9d3bc3eca3ae44605ac06d7b1c6db` |
| MMS semantic results, excluding timing | `d0ea5a892d15a75aa215374fa03a66630db9ba60c45074328c7be4cd5f649059` |
| Comparative manifest file | `1748308d5dacda3efd3b6bb2492605984ed13752803743e67fef5ee7fda5f056` |
| Comparative manifest payload checksum | `bdc8ff350f378decfc280857a2f5a1e98c97a75fc6c6a66e1fa62975a2fcb1d9` |
| Final validation file | `21dc1c099758fff5b646a9b5cf23212e146140aba1da43a977de68170395817f` |

The hashes anchor this actual run, not bit-identical neural inference across hardware.
Canonical serialization/provenance checks are deterministic. Timings/operational observations
are excluded from semantic result hashes but included in actual result-file hashes.
The persistent exclusive execution marker and completed checkpoints/results prohibit repeating
the standard scored run; verification is the unchanged-run operation. Monitoring connection
timeouts did not restart a model or sample. Checkpoints are crash evidence only, not inputs for
automatic resume/retry; complete model files and the comparative manifest are the final evidence.

## Validation

- New isolated run/acquisition/CLI tests: 40 passed using synthetic fixtures only.
- Pre-execution full repository regression: 806 passed, 4 opt-in model tests skipped;
  includes all 91 database-marked tests. No synthetic fixture is benchmark evidence.
- Final full suite with two real voice adapter smoke tests enabled: 808 passed, 2 skipped,
  2 existing deprecation warnings, exit 0; duration 249.70 seconds. The skipped tests are
  existing opt-in visual pretrained tests, not voice paths. Both real voice smoke tests passed.
- All 91 database-marked tests passed within that full suite. Voice unit/benchmark/dataset/run
  tests and existing fixture ingestion, visual adapter and bridge regressions passed unchanged.
- Ruff: PASS. Formatting: PASS, 167 Python files already formatted.
- Default mypy: PASS, 72 source files. Explicit voice/integration/new-script mypy: PASS,
  33 source files. Dependency validation (`pip check`): PASS.
- Full frozen corpus verification after final regression: PASS with the original manifest hash.
- Evidence verification: PASS. All 408 run JSON files passed byte-exact canonical
  JSON round-trip checks, with validation/manifest file counts and hashes agreeing.
  These checks require no additional neural calls.

Executed commands (using the existing project virtual environment):

```powershell
python scripts/run_voice_evaluation.py run
python scripts/run_voice_evaluation.py verify
python scripts/prepare_voice_evaluation.py verify
python -m pytest -q tests/voice/test_run.py tests/voice/test_run_acquisition.py tests/voice/test_run_cli.py
$env:RUN_DATABASE_TESTS='1'
$env:RUN_VOICE_MODEL_TESTS='1'
$env:HF_HOME=Join-Path (Get-Location) '.cache/voice/huggingface'
$env:HF_HUB_OFFLINE='1'
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN='1'
$env:VOICE_SMOKE_MANIFEST=Join-Path (Get-Location) 'artifacts/eval_voice_run_v1/smoke-input.json'
$env:VOICE_SMOKE_AUDIO_ROOT=Join-Path (Get-Location) 'artifacts/voice_evaluation_v1'
python -m pytest -q --tb=short
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m mypy src/sahulat_voice integration scripts/acquire_voice_models_v1.py scripts/run_voice_evaluation.py
python -m pip check
```

All mandatory checks pass. There is no remaining operational dependency for this gate;
the timing stalls and dataset/training limitations above remain evidence limitations,
not concealed or repaired benchmark defects. Model selection/production suitability is not
established and remains outside this gate.

## Complete file inventory

Added source/test/documentation files:

- `src/sahulat_voice/runs/__init__.py`
- `src/sahulat_voice/runs/execution.py`
- `src/sahulat_voice/runs/scoring.py`
- `scripts/acquire_voice_models_v1.py`
- `scripts/run_voice_evaluation.py`
- `tests/voice/test_run.py`
- `tests/voice/test_run_acquisition.py`
- `tests/voice/test_run_cli.py`
- `docs/EVAL-VOICE-RUN-V1.md`
- `reports/eval_voice_run_v1.md`

Modified: only the voice-status paragraph/link in `README.md`. Existing adapters, audio,
transcript, scoring scaffold, frozen protocol/configuration/corpus and all teammate-owned
text/labeling/FTS/backend modules are unchanged.

Generated under `artifacts/eval_voice_run_v1/`:

- `model_acquisition.json`: pinned model assets, sizes and whole-file/source identities.
- `smoke-input.json`, `smoke-selection.json`: pre-output unscored regression input/provenance.
- `execution.started.json`: persistent dataset/run identity and repeat-run guard.
- `whisper.json`, `mms.json`: all 200 scored records each, raw/normalized transcript identities,
  failures, scoring, environment, source fingerprints and load/warmup observations.
- `whisper/samples/<sample_id>.json`: exactly 200 crash checkpoints for the frozen IDs.
- `mms/samples/<sample_id>.json`: exactly 200 crash checkpoints for the same frozen IDs.
- `manifest.json`: verified comparative result-file/semantic hashes and summaries.
- `validation.json`: final validation status, test/static totals, identities and non-contamination checks.

There are 408 run files including the final validation record. Runtime weights and resumable
range fragments are in ignored `.cache/voice/`, outside benchmark/evaluation canonical artifacts.
No secrets, DSNs, signed download URLs or machine-specific absolute paths are in the evidence.
Repository artifact/cache ignore conventions remain unchanged; no Git commit/push was performed.

## Limitations, boundaries and stopping point

FLEURS is published read speech, not genuine Sahulat commerce-query speech. Locale coverage is
en_us, ur_pk, sd_in and ps_af only. Published read-script references are not newly annotated
verbatim transcriptions or new individual-consent assertions. As preregistered, MMS identifies
FLEURS among training/fine-tuning sources; common zero-shot/unseen-domain conditions are not
established, and Whisper training overlap cannot be ruled out. Fifty samples per language is
a limited matched test subset; no speaker-cluster confidence claim is made. CPU timings have
the explicit operational-stall limitation above. Neural repeatability across hardware was not
tested by rerunning these samples.

MMS remains CC-BY-NC-4.0 research comparison only. No production winner/selection/deployment
was declared. No samples were replaced, references modified, preprocessing changed, protocol
amended, tuning/training conducted, or outputs manually corrected. No voice-to-search integration,
STT HTTP API, streaming, VAD, denoising, translation/transliteration, LLM correction, Search,
FTS, BM25, vectors, dense retrieval, RRF, Commerce, frontend, authentication, RAG or public
deployment was implemented. No teammate-owned human-query/labeling/adjudication work changed.
Stop after this evidence gate.
