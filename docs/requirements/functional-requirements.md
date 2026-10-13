# Functional requirements (system)

This is the repository's implementation and acceptance matrix for the modules
listed in [`docs/fyp/modules.md`](../fyp/modules.md). It records current code
status, not approval of a customer production launch. ML benchmark protocols
and frozen evidence remain under `ml-pipeline/docs/`.

| Module | Implemented boundary | Next acceptance gate |
| --- | --- | --- |
| Vendor and customer identity | Cookie login, active role/membership checks, customer profiles/addresses, development registrations, and admin approval APIs use separate database capabilities. | Integrate OTP/email verification before enabling registration outside development; run deployment-level authentication checks. |
| Vendor catalog and listings | Authorized product detail, paginated overview, product/variant/listing creation and editing, category selection, private image upload, commercial/stock/offer settings, and owner/manager publication guards. | Apply migration 005 and grants, run database integration smokes, and validate S3-compatible storage before deployment outside local development. |
| Customer text search | The public catalog search route serves PostgreSQL lexical FTS over eligible products. The UI's semantic mode currently uses this lexical path; dense/hybrid RRF remains Python-side research work. | Freeze genuine human queries and relevance labels, evaluate dense/hybrid retrieval, then approve any replacement serving path. |
| Customer image search | The public search route proxies the pinned internal visual service; the current visual index remains an evaluation fixture. | Ingest real vendor images, build a versioned index, resolve external IDs, and validate eligible live-listing filtering before launch. |
| Customer voice search | The public search route can proxy configured voice transcription into product search. English/Urdu have a service contract; independent Sindhi/Pashto evidence remains unavailable. | Provision pinned weights, measure CPU latency and target-user quality, then collect and freeze independent Sindhi/Pashto recordings before enabling those languages. |
| Offers, orders, checkout, payments | Backend migrations define offers, one-vendor orders, item snapshots, reservations, and payment/refund event boundaries. Transaction-safe APIs implement decisions, idempotent COD checkout, reservation release/consume, history, and fulfillment. UI screens still use preview adapters. | Apply and verify migrations 004/005 on PostgreSQL 18 plus pgvector, run role and upgrade preservation checks, connect the UI, then integrate a payment provider. |
| Platform administration | Active platform admins can list users/vendors and change statuses through a dedicated capability role; changes are audited. Local bootstrap creates a private test admin only. | Apply migration 005 and admin grants, exercise cross-role authorization, and define production admin provisioning. |
| Vendor Business Assistant | Read-only catalog/stock/publication question API and UI with evidence links. | PostgreSQL-backed authorization and failure-mode tests, operational readiness, and provisioned vendor accounts. Sales analytics depend on commerce data. |

No evaluation fixture may appear as a live customer product. A product's
publication prerequisites are vendor-facing diagnostics; they are not by
themselves a customer visibility or purchase authorization decision.
