# Frontend to backend API

The Next.js app targets `NEXT_PUBLIC_BACKEND_URL` and sends cookie credentials
to the ASP.NET API. Configure `Frontend__Origin` to the exact UI origin. The
browser never calls Python ML services directly.

## Identity and public marketplace

- `POST /api/v1/auth/customer-registrations` - Development-only local customer registration. OTP replaces this activation shortcut in the later identity milestone.
- `POST /api/v1/auth/vendor-registrations` - Development-only pending vendor registration; a local operator or platform admin must approve it.
- `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`. `me` returns active platform roles and vendor memberships; `platform_admin` also receives the UI-facing `admin` alias.
- `GET /api/v1/catalog/products`, `GET /api/v1/catalog/products/{productId}`, and the nested image route - bounded public reads of eligible active listings on published products.
- `/api/v1/catalog/search` is the single browser-facing search boundary for lexical text discovery plus optional image and voice ML requests. Image/voice paths return `503` when their configured internal services are unavailable.
- Public storefront links use `/shop/{vendorSlug}`. Legacy `/vendor/{slug}` storefront URLs redirect there.
- `GET/PUT /api/v1/account/profile` and `POST/PUT /api/v1/account/addresses` - authenticated customer profile and delivery addresses.
- `GET/POST /api/v1/offers`, `GET /api/v1/offers/{offerId}`, `POST .../withdraw`, and `POST .../accept-counter` - customer offer lifecycle.
- `GET/POST /api/v1/orders`, `GET /api/v1/orders/{orderId}`, and `POST /api/v1/orders/{orderId}/cancel` - one-vendor checkout, idempotent order creation, inventory reservation, history, and bounded cancellation.

## Vendor operations

- `GET/POST /api/v1/vendors/{vendorId}/catalog/products` - paginated product overview and editor-only draft creation.
- Product-nested category, variant/listing creation and editing, commercial details, stock, image, publication, and guarded publish routes support the vendor catalog workflow.
- `POST /api/v1/vendors/{vendorId}/assistant/queries` - read-only vendor catalog and stock questions with evidence.
- `GET /api/v1/vendors/{vendorId}/commerce/summary` - pending offer, open order, and stock exception counts.
- `GET /api/v1/vendors/{vendorId}/commerce/analytics?periodDays=30` - owner/manager-only metrics from completed paid orders, kept separate by currency.
- `GET /api/v1/vendors/{vendorId}/commerce/offers` and `PUT .../offers/{offerId}/decision` - vendor-scoped offer review, counter, acceptance, and rejection.
- `GET /api/v1/vendors/{vendorId}/commerce/orders` and `PUT .../orders/{orderId}/status` - vendor-scoped fulfillment transitions with reservation consume/release.
- `GET/PUT /api/v1/vendors/{vendorId}/settings` - store profile and marketplace-wide offer preference for owners/managers.

## Platform administration

- `GET /api/v1/admin/summary` - aggregate platform counts and recent audited activity.
- `GET /api/v1/admin/users` and `PUT /api/v1/admin/users/{userId}/status`.
- `GET /api/v1/admin/vendors` and `PUT /api/v1/admin/vendors/{vendorId}/status`; activating a pending vendor also activates its pending memberships and users.
- Every query checks an active `platform_admin` role in PostgreSQL and uses a dedicated non-superuser runtime capability.

All private routes recheck active users, roles, and vendor memberships in SQL.
Writes use bounded bodies, rate limits, parameterized SQL, server-side
authorization, audit/outbox records where relevant, and structured errors.
Responses containing private state use `Cache-Control: no-store`.

Checkout currently accepts `cash_on_delivery` only. Payment/refund event tables
reserve the later provider integration boundary; no external payment provider is
enabled. The frontend screens remain on preview adapters until their service
integration is completed.

Migrations 004/005 and capability grants are applied only through explicit
scripts. API startup never performs DDL.

Deployment probes use `GET /health/live` for process liveness and
`GET /health/ready` for the primary PostgreSQL connection.
