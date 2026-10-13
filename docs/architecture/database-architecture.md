# Database architecture

**Backend** owns production commerce schema (users, vendors, products, listings, inventory, offers, orders).

**ML pipeline** owns research and index tables (e.g. lexical FTS table, dense prototype vectors) via `ml-pipeline/database/migrations/`.

Both may connect to the same PostgreSQL instance in development; migration ownership must not be merged blindly.
