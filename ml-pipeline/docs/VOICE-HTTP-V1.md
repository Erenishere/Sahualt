# Voice HTTP V1

Status: **internal serving code implemented; customer production launch blocked**.
This adapter does not change the frozen voice decoding, normalization, FLEURS
results, or alternative-model comparisons. Its versioned contract is
`configs/api/voice-http-v1.openapi.json`.

## Serving boundary

`sahulat_api.voice` serves the existing `sahulat_voice` Whisper adapter on CPU.
The model revision is pinned in `sahulat_voice.contracts`; startup requires
`HF_HUB_OFFLINE=1`, locates the cached `model.safetensors` at that revision,
checks its whole-file SHA-256 against the verified checkpoint, and loads the
model before readiness succeeds. Missing or different weights keep readiness
at 503. The service never downloads a model, accepts a model name from a
request, or falls back to MMS. MMS is excluded from this commercial-use path
because its published license is CC BY-NC 4.0.

The supplied CLI binds only `127.0.0.1`, one worker, no access log, and no
trusted proxy headers. There is no browser CORS or authentication. Put an
authenticated, rate-limited backend gateway in front of this service before
any customer access. Do not expose the loopback adapter publicly.

`POST /api/v1/transcriptions` accepts a raw `audio/wav` body and an explicit
`X-Voice-Language` header. The current serving codes are `en` and `ur`.
`AI_VOICE_LANGUAGES` defaults to `en,ur`; the runtime rejects Sindhi and
Pashto configuration until an independent evidence review and model decision.
The underlying evaluation adapters still declare all four languages. The
existing voice validator requires mono, PCM16, 16 kHz, 0.1 to 30 seconds, at
most 2 MiB. Streaming upload
bytes, declared length, upload duration, media/encoding, and one CPU inference
admission are bounded. A disconnected request keeps its admission slot until
the underlying synchronous model call finishes. There is no queue or retry.

Successful responses return normalized text, declared language, model and
revision, exact audio SHA-256, and transcript checksum. Raw audio, paths,
decoder raw text, and latency observations are not returned or persisted.
Responses include `Cache-Control: no-store`. Errors have a fixed
`{"error":{"code":"...","message":"..."}}` shape and do not expose model
exceptions or local paths. Liveness is separate from model readiness.

## Local, internal smoke

Provision the pinned Whisper assets in the local Hugging Face cache first.
This checkout currently has no cached Whisper checkpoint, so a real-model
smoke cannot succeed until assets are supplied. From `ml-pipeline/`:

```powershell
& .\.venv\Scripts\python.exe -m pip install -e '.[ml,api]'
$env:HF_HUB_OFFLINE = '1'
$env:AI_VOICE_MODEL = 'whisper'
$env:AI_VOICE_LANGUAGES = 'en,ur'
& .\.venv\Scripts\python.exe -m sahulat_api.voice_cli --port 8001
```

Then check `GET http://127.0.0.1:8001/health/ready`. A successful
transcription requires a real, consented WAV recording in the validated
format and an explicit language code. Do not use frozen evaluation audio as a
serving smoke or rewrite historical evidence. Synthetic tests inject a fake
adapter and do not assert model accuracy or service latency.

## Launch gates still open

- English and Urdu: independent target-user audio, measured CPU latency and
  resource use, error handling, and acceptable quality thresholds are not
  established. FLEURS WER/CER is evaluation evidence, not a production SLO.
- Sindhi and Pashto: independent human recordings and a commercially usable,
  sufficiently accurate model decision are missing. The current Whisper
  FLEURS results are poor for both; MMS is noncommercial, and BuzzASR's
  FLEURS overlap makes that comparison reference-only.
- Voice-to-product search: transcript-to-text retrieval and backend catalog
  visibility are not implemented or evaluated. This endpoint transcribes
  only; it does not search or create orders.
- Public access: the backend gateway, abuse limits, user consent, retention
  policy, deployment isolation, and operational SLO tests remain to be
  completed before customer exposure.
