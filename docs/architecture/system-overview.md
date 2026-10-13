# System overview

```text
Browser (Next.js frontend)
        │
        ▼
ASP.NET Core backend  ── PostgreSQL / Redis
        │
        ├── Business: users, vendors, products, listings, offers, orders
        │
        └── ML HTTP clients (Visual / Text / Voice)
                    │
                    ▼
            Python ml-pipeline services
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   sahulat_visual  sahulat_text  sahulat_voice
```

Frontend never calls ML services directly.
