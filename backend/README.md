# Sahulat AI backend

ASP.NET Core solution (`SahulatAI.slnx`). Layers:

- `src/SahulatAI.Api`
- `src/SahulatAI.Application/Features/`
- `src/SahulatAI.Domain`
- `src/SahulatAI.Infrastructure` (includes `ML/` HTTP client boundary)

```powershell
dotnet run --project src/SahulatAI.Api
```

The canonical catalog schema is managed by explicit SQL migrations under `ml-pipeline/database/migrations/`; API startup does not migrate the database.

## Backend capabilities

The API exposes public catalog reads, customer accounts and addresses, offers,
idempotent cash-on-delivery checkout, orders, inventory reservations, vendor
fulfillment, platform administration, vendor catalog management, and the
Vendor Business Assistant. Vendor settings and owner/manager analytics read
reconciled commerce records and keep currencies separate. Commerce uses one vendor per order. External payment,
OTP, cache, and ML model integration remain later milestones.

Use dedicated non-superuser connection strings for `AssistantReader`,
`IdentityReader`, optional `CatalogWriter`, development-only
`RegistrationWriter`, `CommerceWriter`, and `AdminWriter`. Missing optional
writers return `503`; API startup never migrates the database.

## Vendor Business Assistant

The stateless `POST /api/v1/vendors/{vendorId}/assistant/queries` endpoint handles active/draft listings, draft products, low/unknown stock, product listing details, and publication checks. Sales and order questions return `unsupported`. The endpoint does not create assistant or commerce tables; it reads the existing catalog-core schema.

Configuration is supplied through environment variables (never commit credentials): `ConnectionStrings__AssistantReader`, `ConnectionStrings__IdentityReader`, and `Frontend__Origin`. Outside development, `DataProtection__KeysPath` must point to durable protected key storage so session cookies survive restarts. The backend verifies the existing Argon2id hash in `iam.users` and issues an HttpOnly, same-site session cookie. Every assistant request rechecks the user's active vendor membership and vendor status in PostgreSQL; the catalog SQL also includes the membership predicate. Browser POST requests require the configured frontend `Origin`.

Example request after `POST /api/v1/auth/login` has established a browser session:

```http
POST /api/v1/vendors/{vendorId}/assistant/queries
Origin: http://localhost:3000
Content-Type: application/json
Cookie: sahulat_session=<session cookie>

{"question":"Which products are low in stock?"}
```

Product-specific questions also accept `productId`. The endpoint returns a structured `answer`, `intent`, `outcome`, `evidence`, and `correlationId`; it never lets question text choose the vendor. No database migration is run by API startup.

Evidence links open `GET /api/v1/vendors/{vendorId}/catalog/products/{productId}` in the Next.js vendor UI. This read-only endpoint rechecks active membership on every request, returns a bounded product/listing snapshot, and uses `404` for records outside the authorized vendor. Unknown stock remains unknown rather than being displayed as zero.

`GET /api/v1/vendors/{vendorId}/catalog/products` returns a bounded, UUID-cursor page of non-archived products and their publication prerequisites for the authenticated vendor. The Next.js `/vendor/catalog` page displays these facts, creates drafts, and links to product details. Customer search eligibility is a separate future gate.

`POST /api/v1/vendors/{vendorId}/catalog/products` creates a draft with a required name and description. Only active `owner`, `manager`, or `staff` members may call it; SQL checks the same permissions again at insert time. Set `ConnectionStrings__CatalogWriter` to a dedicated non-superuser login granted `sahulat_catalog_writer` from `database/provisioning/vendor_catalog_writer.sql`. Category, variant/listing, private image upload, stock and availability editing, and guarded owner/manager publication routes support the local catalog workflow. Unknown stock remains distinct from zero, and a stock update cannot reduce on-hand quantity below reservations.

The role scripts in `database/provisioning/` define separate reader, catalog,
registration, commerce, and admin capabilities. A database administrator must
provision dedicated logins and review effective privileges; the API does not
apply grants. Development registration routes support local testing. Actual
OTP/email verification remains unimplemented.

## Local demo catalog

`scripts/seed-demo-catalog.ps1` imports the guarded `SAHULAT-3-DEMO-STORES-V1`
archive into local `sahulat_ai_dev`. It creates one isolated owner account per
vendor and keeps every product, variant, and listing in draft state with unknown
inventory by default. Product images are normalized into `backend/.local-media`;
vendor credentials are written to the ignored `backend/.local-demo-vendor-secrets.json`.

```powershell
# Validate only
.\scripts\seed-demo-catalog.ps1 -ArchivePath <archive.zip>

# Idempotent local import
.\scripts\seed-demo-catalog.ps1 -ArchivePath <archive.zip> -Apply

# Optional local storefront preview; demo products remain unavailable
.\scripts\seed-demo-catalog.ps1 -ArchivePath <archive.zip> -Apply -ClientFacing

# Remove only the deterministic demo dataset
.\scripts\seed-demo-catalog.ps1 -ArchivePath <archive.zip> -Purge
```

The script rejects non-local databases. `-ClientFacing` is an explicit local-only
preview mode: it publishes the demo records for the customer catalog, preserves
their demo/unverified descriptions, and marks availability as `unavailable`
because no real inventory evidence exists.
