# Frontend architecture

The main UI is a Next.js App Router application under `frontend/src/app`.
`marketplace-ui.tsx` provides the shared customer, vendor, and admin preview
screens through the validated catch-all route. Backend-connected vendor pages
remain explicit routes so they take precedence over preview routes.

All API access goes through `src/services/backend-client.ts`. No direct ML base URLs in the browser.

## Screen inventory

| Area | Routes | Data boundary |
| --- | --- | --- |
| Customer discovery | `/`, `/search`, `/product/{id}`, `/shop/{vendorSlug}` | Public catalog and multimodal search APIs are connected; ML-backed modes return `503` when their services are unavailable |
| Customer account and commerce | `/login`, `/register`, `/profile`, `/offers`, `/offers/{id}`, `/checkout`, `/orders` | Account, offer, COD checkout, reservation, and order APIs exist; screens still use preview state |
| Vendor operations | `/vendor`, `/vendor/inventory`, `/vendor/offers`, `/vendor/orders`, `/vendor/analytics`, `/vendor/settings` | Commerce summary, offers, and fulfillment APIs exist; analytics remains illustrative pending reconciled data |
| Vendor live catalog | `/vendor/catalog`, `/vendor/{vendorId}/products/{productId}` | Authenticated PostgreSQL-backed catalog, images, publication, stock, and availability |
| Vendor access and assistant | `/vendor/register`, `/vendor/assistant` | Development registration plus authenticated, vendor-scoped assistant API |
| Platform administration | `/admin`, `/admin/vendors`, `/admin/users` | Role-gated user/vendor administration APIs exist; screens still use preview state |

Preview screens may use browser-local state for interaction, but must never be
presented as persisted backend data. ML features remain represented as UI states
until the backend exposes approved inference contracts and evaluated models.
