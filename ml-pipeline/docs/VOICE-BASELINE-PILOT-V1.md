# VOICE-BASELINE-PILOT-V1

This is a separate, first-party-only ASR pilot. It does not amend or replace
EVAL-VOICE-V1 or EVAL-VOICE-CORPORA-V2. It accepts fresh human recordings only
after the speaker's permission has been recorded and a human has verified the
reference transcript. It never downloads public audio, creates TTS speech,
fine-tunes a model, or changes a checkpoint.

The collection target is 30 recordings in each group (`ur`, Urdu-English
`ur_en`, Sindhi `sd`, Pashto `ps`), ideally from five self-attested native
speakers per group. Smaller samples are allowed and are reported as such. A
deterministic round-robin selection caps each frozen group at 30; selected
speaker pseudonyms and selection decisions are retained in the private frozen
manifest. Pseudonyms are labels, not verified identities.

## Model pins and scope

| Group | Pinned baseline(s) |
| --- | --- |
| Urdu | Whisper large-v3-turbo `openai/whisper-large-v3-turbo@41f01f3fe87f28c78e2fbf8b568835947dd65ed9` |
| Urdu-English mixed | Whisper large-v3-turbo, same pin |
| Sindhi | MMS-1B-All `facebook/mms-1b-all@3d33597edbdaaba14a8e858e2c8caa76e3cec0cd`; BuzzASR `BuzzASR/sindhi@8e85f09a5c0b17c635ffa8fd124b1efa56fcb5c7` |
| Pashto | MMS-1B-All, same pin; Pashto Ghag `Nasimbahar/pashto-ghag-whisper-medium-asr@ed20e00d47d0852ed24f07b4370c0bdac2e5f241` |

This checkout previously pinned Whisper large-v3, not large-v3-turbo. The pilot
therefore records a separate turbo revision from the official
[Hugging Face model repository](https://huggingface.co/openai/whisper-large-v3-turbo/tree/41f01f3fe87f28c78e2fbf8b568835947dd65ed9).
EVAL-VOICE-V1 keeps its original large-v3 pin. The other three pilot pins are
checked against the existing local model registries at freeze/run time. The
pilot runs CPU/float32, offline-only, deterministic transcription. MMS is
CC-BY-NC-4.0; this pilot is research-only and does not establish permission for
commercial/production deployment. Published training data is not a complete
exposure audit; text/phrase overlap stays unknown.

Urdu and mixed Urdu-English each have only one configured model, so those
groups cannot yield a head-to-head model winner. Sindhi and Pashto identify the
lowest pooled micro-WER, then micro-CER, among completed models. A tie remains a
tie. Any “strongest” result is descriptive of this small pilot only.

## Consent and recording workflow

The consent text in
[`forms/VOICE-BASELINE-PILOT-CONSENT-V1.md`](forms/VOICE-BASELINE-PILOT-CONSENT-V1.md)
is a draft, not legal or ethics approval. Obtain the required institutional or
research-ethics review before recruitment. Use pseudonymous IDs such as
`SPK_001`; do not put names, phone numbers, addresses, or signatures in the
recording manifest. Keep signed consent evidence and audio inside the private,
ignored `.local/voice_baseline_pilot_v1/` directory or an equivalently protected
location. The registry records only an evidence-file digest and reviewer
metadata. Do not publish audio or raw consent evidence.

1. Initialize the private workspace:

   ```powershell
   $env:PYTHONPATH = 'src'
   .\.venv\Scripts\python.exe scripts/voice_baseline_pilot_v1.py init
   ```

2. After consent is obtained and independently checked, place its evidence file
   in `.local/voice_baseline_pilot_v1/consent-evidence/`. Add a consent entry to
   `consent_registry.json`, following
   [`voice_baseline_pilot_v1_consent.example.json`](../configs/voice_baseline_pilot_v1_consent.example.json).
   The required permissions are private storage, local ASR processing, and
   aggregate research reporting. `public_audio_release` must remain false.
   Record the approved retention end date. De-identified transcript examples
   require a separate affirmative permission.

3. Record human speech directly as mono 16 kHz, PCM16 RIFF/WAV, 0.1–30 seconds.
   Use natural speech or a participant reading human-authored prompts; do not
   use TTS, voice conversion, public-corpus clips, synthetic speech, or model
   output. Avoid real personal/order information. Place files in
   `.local/voice_baseline_pilot_v1/audio/`.

4. Have a human transcribe and a different human verify the exact reference. A
   separate collection reviewer attests that each item is a fresh human
   recording, not TTS or third-party audio. Keep
   `reference_text` unchanged thereafter. Mark its script as `arabic`, `latin`,
   or `mixed`. For Roman Urdu, add a separate, human-verified
   `roman_urdu_reference`; it never replaces the original reference. Fill the
   sample row following
   [`voice_baseline_pilot_v1_recordings.example.json`](../configs/voice_baseline_pilot_v1_recordings.example.json).
   Include optional commerce annotations only after human review. An
   error-example excerpt is reportable only when both participant permission
   and a per-example human review are present. Specific error review happens
   only after model output exists; do not edit the frozen manifest to add it.

5. Enter SHA-256 digests without moving either file. PowerShell example:

   ```powershell
   (Get-FileHash .\.local\voice_baseline_pilot_v1\audio\UR_001.wav -Algorithm SHA256).Hash.ToLower()
   (Get-FileHash .\.local\voice_baseline_pilot_v1\consent-evidence\SPK_001.pdf -Algorithm SHA256).Hash.ToLower()
   ```

6. Validate, freeze, then run only after all consent/reference/audio checks pass:

   ```powershell
   $env:PYTHONPATH = 'src'
   .\.venv\Scripts\python.exe scripts/voice_baseline_pilot_v1.py validate
   .\.venv\Scripts\python.exe scripts/voice_baseline_pilot_v1.py freeze
   .\.venv\Scripts\python.exe scripts/voice_baseline_pilot_v1.py run
   # Review errors in the private run's error_example_reviews.json after inference.
   .\.venv\Scripts\python.exe scripts/voice_baseline_pilot_v1.py publish --run-dir .local/voice_baseline_pilot_v1/runs/<manifest-sha256>
   .\.venv\Scripts\python.exe scripts/voice_baseline_pilot_v1.py verify --run-dir .local/voice_baseline_pilot_v1/runs/<manifest-sha256>
   ```

`freeze` selects at most 30 recordings per group, round-robin over a stable
SHA-256 ordering of pseudonymous speakers and sample IDs. Selection does not
invent replacement samples. It reports eligible, selected, and over-cap
records. Any consent-registry change after freeze blocks inference until the
dataset is reviewed and frozen again. Frozen data, private predictions, and
consent evidence are kept under the ignored local workspace. The shareable
comparison report contains only aggregate metrics and individually approved
error examples. The error-review registry is created after inference and is
bound to the frozen manifest and observed model/sample error; its reviewer must
be different from the collection and transcript reviewers. Consent must remain
active and within its approved retention period at inference and example
publication time.

## Scoring

WER uses whitespace token Levenshtein edits divided by reference words. CER uses
codepoint Levenshtein edits divided by normalized reference codepoints,
including spaces. The versioned normalizer applies NFC, casefolding, digit
equivalence for Arabic/Persian digits, removal of thousands separators between
digits, punctuation-to-space, and whitespace collapse. It preserves Arabic
combining marks and does not transliterate between scripts. Script profile and
match rate are separate measures; optional Roman Urdu WER/CER is a separate
column.

Failures count as empty hypotheses (all reference words/characters are edits),
not as dropped samples. Latency is one scored call per recording; model-load and
an unscored first-sample warmup are reported separately. Commerce annotations
measure intent-cue retention, exact brand mention retention, and numeric price
amount recognition. Since the configured models only transcribe, intent cue
retention is not intent-classification accuracy; number words and currency
classification are not inferred.

The comparison report is `PILOT`, includes speaker/sample counts, failure rate,
WER/CER, latency and approved error examples, and never promotes a model to
production or replaces V1 evidence.
