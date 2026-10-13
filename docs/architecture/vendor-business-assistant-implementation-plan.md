# Vendor Business Assistant: implementation plan

Status: assistant and commerce foundations implemented; deployment verification remains pending.

## Product role and release boundary

The first release is a **vendor-facing, read-only business assistant** inside the vendor area. It helps an authenticated vendor member understand and manage that vendor's own catalog. The backend, not a model, decides identity, vendor scope, data access, calculations, and whether an answer is supported. A customer-facing shopping assistant would be a separate product role and API. This is a locked architecture rule.

| It will do in the first release | It will not do in the first release |
| --- | --- |
| Answer listing, price, availability, and stock questions from current authorized records, with source links and an "as of" time. | Claim sales, revenue, profit, conversion, or customer behavior without transaction and cost data. |
| Flag specific catalog issues, such as active listings with unknown stock or draft products awaiting publication requirements. | Create, edit, publish, pause, discount, reserve stock, or place orders from chat. |
| Explain which records support a response and say when data is unknown or stale. | Read another vendor's data, private customer records, raw evaluation datasets, or the entire database. |
| Offer navigation to existing vendor workflows. | Run model-written SQL, execute arbitrary tools, make unsupported forecasts, or silently invent currency/stock. |

Initial language support should follow the implemented UI and tested query set. Voice input and multilingual output are later adapters, not a prerequisite for this release. A model is optional: start with intent parsing for a small documented set of questions and deterministic queries/templates. Add an LLM only if evaluation shows that natural-language coverage needs it; keep the same authorized read tools and validate every generated claim against structured evidence. Do not make sales or deployment claims from ML prototype results.

## Existing state and constraints

- `backend/` is a .NET 10 layered API with cookie identity, PostgreSQL persistence, vendor catalog and assistant routes, public catalog, customer commerce, vendor fulfillment, and admin endpoints.
- `frontend/` contains the full screen inventory plus live vendor catalog and assistant pages; most customer commerce and admin screens still need service adapter integration.
- `20260910_001_catalog_core_v1.sql` already defines `iam`, `catalog`, `inventory`, `integration`, and `audit`, including users, vendor memberships, product/variant/listing data, inventory balances, an outbox, and an audit log. Preserve this migration and its data. Existing migration 002/003 artifacts are ML-owned search prototypes, not commerce tables.
- Backend migration 005 defines offers, orders, item snapshots, reservations, and payment/refund event boundaries. No reconciled production commerce data or trustworthy sales facts exist yet. The Khaadi import remains an evaluation fixture. Visual results are retrieval candidates, not commercial authorization or publication status. Text retrieval has no completed official relevance evaluation; voice-to-search is not served.
- Business schema changes belong to the backend owner. Before adding them, reconcile the existing checksum-verified SQL migration history with an EF Core baseline. Keep one authoritative chain for business DDL; leave ML-owned `search` prototype tables and frozen migration 001 unchanged. Record the baseline and ownership procedure in a dedicated decision document before the first new business migration.

Implementation now includes the stateless assistant, catalog editing/publication, public catalog reads, development registrations, customer accounts, offers, COD checkout, inventory reservations, orders, vendor fulfillment, and role-gated administration. Cookie authentication uses the canonical user ID and SQL rechecks active roles/memberships. OTP, external payments, cache, ML integration, deployment database verification, and frontend service adapter integration remain later gates.

## Architecture

```text
Vendor UI -> ASP.NET API -> authenticated assistant use case
                           -> vendor-scoped read services -> canonical PostgreSQL
                           -> answer composer -> response + evidence
```

The API accepts a vendor context only after verifying active user, active membership, permitted role, and active vendor. Every repository method takes that verified context and filters by `vendor_id` in SQL; it never relies on a prompt or client-provided ID alone. Use `Application/Features/Assistant` for intents, authorization-aware use cases, and response composition; `Infrastructure/Persistence` for database access; `Api` for HTTP and DI; `frontend/src/features/vendor-assistant` for the UI. Keep database queries bounded and parameterized. If a language model is added later, give it only typed, allowlisted tool results and require server-side evidence checks before returning a factual answer.

Permission policy: active `owner`, `manager`, `staff`, and `viewer` members may ask first-release catalog and stock questions for their own vendor. Reserve future revenue, payment, refund, and customer-related intents for `owner` and `manager` until the commerce access policy is approved. Suspended/revoked memberships and inactive vendors receive no assistant data. Check permissions again on every request and evidence-link open, including for an existing conversation.

Treat question text as untrusted input. It cannot grant permissions, change vendor context, or alter system rules. Keep raw question and answer retention limited; redact secrets and personal data from logs. Assign a request/correlation ID and record selected intent, evidence IDs, outcome, latency, and model/version only when applicable.

## Release map

| Release | Product scope | Data prerequisite |
| --- | --- | --- |
| 1 - Vendor Business Assistant | Catalog, listing, availability, stock, and publication questions | Existing canonical vendor/catalog/inventory tables, authentication, vendor isolation |
| 2 - Commerce Foundation | Orders, offers, payments, and refunds as business workflows | Approved commerce lifecycle and additive migrations |
| 3 - Sales & Analytics Assistant | Sales, revenue, order counts, best sellers, offer analytics, and refunds | Reconciled Release 2 transactions and metric definitions |

## Data model and migration plan

No new assistant-owned catalog, order, or customer tables are required for the first release. Read the canonical tables through vendor-scoped application queries. If conversation persistence is included, its first business migration should add only the following assistant state, after the migration-ownership baseline is settled:

| Table | Essential fields and constraints | Purpose |
| --- | --- | --- |
| `assistant.conversations` | `id uuid PK`, `vendor_id FK`, `created_by_user_id FK`, `status` (`active`, `closed`), `created_at`, `updated_at`; index `(vendor_id, created_by_user_id, updated_at DESC)` | Server-owned vendor scope and lifecycle. |
| `assistant.messages` | `id uuid PK`, `conversation_id FK`, `sender` (`user`, `assistant`), `body text` with length cap, `created_at`, `request_id uuid`, `intent_code`, `outcome_code`; index `(conversation_id, created_at, id)`; unique `(conversation_id, request_id)` for user messages with a request ID | Ordered conversation history and safe retry handling. Store no model chain of thought or SQL text. |
| `assistant.message_evidence` | `message_id FK`, `entity_type` allowlist, `entity_id uuid`, `observed_at timestamptz`, `source_version` where available, composite uniqueness | Trace factual claims to authorized records. Reauthorize referenced entities when opening evidence links. |

Use `RESTRICT` for vendor/conversation ownership and deliberate retention deletion for messages/evidence; do not cascade delete business records. Foreign keys, bounded text, status checks, timestamp defaults, and a unique request ID per conversation prevent malformed and duplicated turns. `updated_at` changes in application transactions. Store no prompt secrets or full record snapshots. Agree on a retention period and access/export/delete policy before enabling persisted conversations. If persistence is not needed for the first vertical slice, ship stateless request/response first and defer these tables rather than create unused data.

The later **commerce milestone** needs its own workflow contract before any migration. Proposed minimum schema (field names and lifecycle states must be frozen in that contract):

| Table | Required shape | Integrity rule |
| --- | --- | --- |
| `commerce.orders` | `id`, `vendor_id`, `public_order_number`, `status`, `placed_at`, `created_at`, `updated_at`, `currency`, `subtotal`, `discount_total`, `total` | Unique order number per vendor; non-negative monetary values; one order currency; no customer PII in assistant projections. |
| `commerce.order_items` | `id`, `order_id`, `listing_id`, `product_id`, `variant_id`, immutable item name/SKU/unit price/currency, `quantity`, `discount_total`, `line_total` | Positive quantity; non-negative amounts; item snapshot and listing ownership must match order vendor at write time. |
| `commerce.payment_events` | `id`, `order_id`, `provider`, `provider_event_id`, `event_type`, `amount`, `currency`, `occurred_at` | Unique provider event ID; immutable, idempotently ingested events; payment totals reconciled to order state. |
| `commerce.refund_events` | `id`, `order_id`, optional `order_item_id`, `provider_refund_id`, `amount`, `currency`, `occurred_at` | Unique provider refund ID; cumulative refunds cannot exceed captured payment and item scope is checked. |

Use foreign keys, vendor-scoped indexes on `(vendor_id, placed_at, id)`, order-item indexes on `order_id` and `listing_id`, and suitable payment/refund lookup indexes. Decide whether orders can contain multiple vendors before freezing the order aggregate; this proposal assumes **one vendor per order**, which makes tenancy and settlement unambiguous. Define order state transitions, cancellation/refund semantics, payment status/source, inventory reservation and release, idempotent external events, and time-zone/currency treatment. Define offers and discounts only when their approval and validity rules are known. Add transaction-safe writes, audit/outbox events, and vendor-scoped reporting projections after that contract. Revenue means a specifically defined sum over eligible paid, non-refunded order items in one currency or explicitly separated currencies; never add unlike currencies. Profit requires actual cost data. Conversion requires a defined traffic and attribution source. These metrics stay unavailable until their sources and reconciliation tests exist.

## API and user experience

- `POST /api/v1/vendors/{vendorId}/assistant/queries`: accepts a bounded question and optional conversation ID/request ID; returns answer text, intent, outcome (`answered`, `needs_clarification`, `unsupported`, `unavailable`), structured evidence (`entityType`, `entityId`, display label, `observedAt`, link), and correlation ID. Validate input, authenticate, authorize membership, enforce rate/size limits, and use stable structured errors. When conversations are persisted, idempotent retry is keyed by the request ID within the conversation.
- `GET /api/v1/vendors/{vendorId}/assistant/conversations/{id}` and paginated messages are needed only if conversation persistence ships. Authorize every read against current membership; a conversation ID is never an authorization token.
- Vendor UI shows answer, source links, timestamp, and clear unknown/unsupported states. It should allow a vendor to open the relevant product/listing page. No UI action should imply a business mutation was made.
- Release 1 suggested prompts: "Which products are low in stock?", "Show my active listings", "Which listings are still drafts?", "Which products have unknown stock?", and "Why can't this listing be published?" Revenue, order, and best-seller prompts belong to Release 3 UI only.
- The assistant reads the latest committed data for operational questions. For a multi-query answer, use one consistent database snapshot or report the actual observation times. Add a short freshness message when the source is delayed or unavailable.

## Delivery sequence and acceptance gates

1. **M1 - Authentication & Vendor Isolation.** Establish the business migration baseline without replaying 001, add PostgreSQL persistence, a non-superuser runtime DB role, authentication/session handling, active vendor-membership checks, and integration tests proving cross-vendor denial. CI must apply migrations to an empty database and upgrade a database already at migration 001 (and any existing ML search migrations) without data loss. No runtime schema mutation at startup.
2. **M2 - Vendor Catalog APIs.** Implement vendor-scoped catalog/listing/inventory read services and publication checks. Use explicit `NULL = unknown` semantics for stock and price/currency. Test draft/archived records, inactive memberships, missing inventory rows, and concurrent updates.
3. **M3 - Vendor Assistant V1.** Implement a small allowlisted intent set: listing lookup, low/unknown stock, active/draft listing counts, and publication blockers. Use deterministic SQL queries and answer templates with evidence. Add the question API and vendor UI. Test adversarial question text, cross-vendor identifiers, unknown facts, timeouts, and repeated request IDs.
4. **M3 release hardening.** Add bounded query execution, rate limits, request tracing, health/readiness, sanitized logs, backups/restore exercise, migration rollback strategy, data retention controls, and failure-mode responses. Measure p50/p95 API latency and error rate on realistic vendor data; set deployment SLOs from measured behavior rather than inventing targets.
5. **M4 - Commerce & Offer Workflow.** Approve order/offer/payment workflow, then add additive migrations, transaction-safe writes, and reconciliation tests.
6. **M5 - Sales Analytics.** Add vendor-scoped reporting and revenue/order intents with explicit periods, status definitions, currencies, refunds, and source links. Use human-reviewed examples and leakage/cross-tenant tests before enabling any generated sales narrative.
7. **M6 - Multilingual / Voice Assistant Input.** Evaluate deterministic intent coverage against a held-out vendor-question set. If necessary, add a constrained LLM answer composer behind the same read services, source validation, budget/time limits, and fallback. Voice transcription can feed the same API after a separate service contract and accuracy gate.

Release gate for the first assistant: authenticated vendor can ask every supported question and get an evidence-backed answer; unsupported sales questions explicitly state the missing data; cross-vendor reads and prompt-based bypasses fail; integration tests pass against a migrated PostgreSQL instance; UI handles loading/empty/error states; and operational checks are documented. Do not label the whole system production-ready before the authentication, database, authorization, and deployment gates pass.

## Decisions requiring product input

Vendor-only scope is confirmed. Before persistent chat or commerce work, choose a retention period, supported languages, order/payment workflow, whether checkout permits multiple vendors per order, and the precise sales metrics the product needs. These decisions do not block the read-only vendor vertical slice.
