# Backend ↔ ML API boundary

Backend `Infrastructure/ML` calls Python HTTP services. Contract files:

- `shared/api-contracts/ml/visual-http-v1.openapi.json`
- `shared/api-contracts/ml/voice-http-v1.openapi.json` (internal transcription only)
- Future: `text-http-v1` and customer-facing search contracts

Frontend uses only backend REST endpoints documented in `frontend-backend.md`.
The backend `MlInferenceClient` implements the internal visual multipart and
voice WAV contracts. Configure `MlServices:VisualBaseUrl`, `VisualSourceSystem`,
`VisualModel`, `VisualEmbeddingVersion`, and `VoiceBaseUrl` before using it
in an authenticated backend workflow. The client is registered for dependency
injection but has no public route. It checks response contract,
model identity, source namespace, bounded response size, and voice input hash.
Use HTTPS for remote services; HTTP is accepted only for loopback development.

Visual IDs remain external identifiers and must be resolved against canonical catalog records,
then filtered for publication and availability. The current image index is an
evaluation fixture, not a live vendor catalog. The voice service returns text
only and currently permits English and Urdu. Sindhi and Pashto need independent
validation and a serving decision. Neither ML endpoint is browser-accessible.
