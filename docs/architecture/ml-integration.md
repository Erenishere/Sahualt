# ML integration

- **Owner:** `backend/src/SahulatAI.Infrastructure/ML/`
- **Consumers:** `Application/Features/Search/` orchestrates text, image, and voice search.
- **Providers:** Python packages under `ml-pipeline/src/` (`sahulat_visual`, `sahulat_text`, `sahulat_voice`).

Database split:

| Layer | Migrations |
| --- | --- |
| Backend | `SahulatAI.Infrastructure/Persistence/Migrations/` — business schema |
| ML | `ml-pipeline/database/migrations/` — catalog core + search index prototypes + eval infra |

ML retrieval engineering is **frozen** at prototype depth until EVAL-TEXT-V1 label freeze. See `ml-pipeline/docs/ENGINEERING-TEXT-PROTOTYPE-V1.md`.
