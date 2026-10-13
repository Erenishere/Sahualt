# Sahulat AI frontend

Next.js App Router skeleton. Feature modules live under `src/features/`.

```powershell
npm install
npm run dev
```

Set `NEXT_PUBLIC_BACKEND_URL` to the ASP.NET API origin. Do not configure ML service URLs in the browser.

The customer marketplace (`/`, `/search`, `/product/{uuid}`, `/offers`, `/checkout`, `/orders`, `/login`, `/register`, `/profile`) calls the ASP.NET API for catalog search, product images, auth, offers, and cash-on-delivery orders. Image and voice search UIs still fall back to catalog text search until ML routes exist. The in-app vendor portal under `/vendor/listings` remains a local prototype; real vendor workflows use `/vendor/catalog` and `/vendor/assistant`.

The `/vendor/assistant` page uses the backend's cookie login and only offers catalog/stock prompts. `/vendor/catalog` lists authorized products and publication prerequisites from the backend. Owner, manager, and staff members can create draft products when the dedicated catalog writer is configured. Images, variants, listings, and publication are not available in this form. Set the API's `Frontend__Origin` to this app's exact origin (for example `http://localhost:3000`) and keep `NEXT_PUBLIC_BACKEND_URL` pointed at the same API that issued the cookie. Vendor accounts and runtime database roles must be provisioned before signing in.
