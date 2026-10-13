# Local development

1. `scripts/setup-dev.ps1`
2. Copy the root `.env.example` to `.env`, set a local `POSTGRES_ADMIN_PASSWORD`, then run `docker compose up -d postgres redis`. This starts a fresh PostgreSQL 18/pgvector environment with a persistent named volume; it does not run migrations. See `infrastructure/postgres/README.md` before reusing any existing PG16 data.
3. Review `scripts/apply-platform-migrations.ps1` in plan mode, then run it with `-Apply` to apply or verify canonical migrations 001/002/003 plus backend baseline 004 and commerce migration 005 explicitly.
4. Backend + frontend + ML services per layer READMEs
5. `scripts/verify-all.ps1`

For the already-running local Windows PostgreSQL service and the `sahulat_ai_dev`
URL in `ml-pipeline/.env`, run `scripts/verify-local-catalog-db.ps1 -Apply`
after migrations 001-005, then apply `backend/database/seeds/initial_apparel_categories.sql`
with `psql -v ON_ERROR_STOP=1`. `scripts/bootstrap-local-vendor.ps1` is plan-only;
`-Apply` creates six least-privilege API logins plus local test vendor and admin accounts.
Its generated credentials are stored in the ignored
`backend/.local-runtime-secrets.json` file with local-user access. This is
development data, never a production shared login. Run
`scripts/run-local-vendor-api.ps1` to start the API with those credentials.
In Development, `/vendor/register` creates a pending user, vendor, and owner
membership. The applicant cannot sign in yet. Review the application and run
`scripts/approve-local-vendor.ps1 -Email applicant@example.local` in plan mode,
then add `-Apply` to mark that local account and vendor active. This local
operator step also marks the email verified; it is not an email verification
service and must not be used as a production approval process.
`scripts/run-local-vendor-api.ps1` stores uploaded images under the ignored
`backend/.local-media/` directory. The API serves them only through an
authorized image endpoint; the directory is not a public static path. This
local option is accepted only in Development. Local image records and files
must stay together; switching this database to S3 requires migrating those
objects first.

For S3-compatible storage, set `Media__Provider=S3` plus
`Media__S3__Endpoint`, `Media__S3__Region`, `Media__S3__Bucket`,
`Media__S3__AccessKey`, and `Media__S3__SecretKey` in the backend process
environment. Without either storage option, image upload returns `503`.
