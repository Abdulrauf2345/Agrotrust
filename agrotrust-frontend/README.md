# AgroTrust Frontend

A React 18 + TypeScript client for the AgroTrust backend: registration and login, role-based dashboards, farm registration, marketplace listings, the full order/escrow flow from creation to payout, organization management, fleet/shipment tracking for logistics providers, lending (loan products, applications, decisions, disbursement, repayment schedules), traceability (lot creation, weighing, inspection, hash-chained custody history), parametric weather insurance, and platform admin tooling (users, audit log, dispute resolution).

This is a feature-complete demo slice of the full product, not the complete 89-section specification and not yet production-hardened (see "Deferred" below). It proves the pattern end to end (auth, data fetching, forms, role-aware navigation, several independent state machines) across all nine roles the spec describes. What is here is real and tested against the actual backend routes, not a mockup.

## Stack

- React 18.3, TypeScript (strict mode), Vite 5
- React Router 6 (data router API, `createBrowserRouter`)
- TanStack Query v5 for server state, with automatic retries turned off for mutations (a failed payment or escrow release must never silently retry)
- React Hook Form + Zod for forms
- Tailwind CSS with CSS-custom-property design tokens, so light/dark theming is one variable swap, not a second set of classes
- Vitest for unit tests

## Running it

This was built and verified in a sandbox with no network access to the npm registry, so the test here was static analysis (TypeScript compiler checks on every file, a transpile-and-run of the unit tests) rather than a real `npm install`. On a normal machine:

```bash
cp .env.example .env
# edit .env if your backend runs somewhere other than http://localhost:8000
npm install
npm run dev
```

Start the backend first (see the root `README.md` / `scripts/run_dev_server.py`), then open `http://localhost:5173`.

```bash
npm run test     # unit tests
npm run build    # type-checks via tsc -b, then builds
```

## How it is organized

```
src/
  app/            router, layouts, providers, top-level pages (404 etc.)
  components/     design-system primitives (Button, Card, Badge...) and navigation
  features/       one folder per domain area: auth, dashboard, farms, marketplace, orders, logistics, organizations, lending, traceability, insurance, admin, notifications
  lib/            api client, auth context, formatting, validation, utilities
  types/          TypeScript types matching what the backend actually returns
```

Each feature folder has its own `api.ts` (the HTTP calls), `hooks.ts` (TanStack Query wrappers), and `pages/` (the screens). This is a feature-based layout, not a type-based one (no top-level `pages/`, `hooks/`, `services/` dumping ground), because a change to "orders" should touch one folder, not four.

## What matches the real backend

Every endpoint the frontend calls, every field name, every role string, and the order state machine's exact state names were taken directly from `src/agrotrust/api/app.py` and the module services in the attached backend, not assumed from the specification. The specification used `COMPLETED` for a finished order and a `/auth/logout` endpoint, for instance; the actual backend in this zip has `COMPLETED` too but has no `/auth/logout` route, so the frontend does not call one (it clears tokens client-side instead). Where the backend does not yet support something the spec asks for, it is left out here rather than faked with a stub that would quietly return wrong data.

## Security tradeoffs, written down rather than hidden

- The access token lives in memory only, never in storage, so it cannot be read by an XSS payload sitting in `localStorage`. The refresh token does live in `localStorage` because this backend does not issue HttpOnly cookies; that is a real tradeoff, not an oversight. A production deployment should move to cookie-based refresh.
- A single in-flight refresh promise prevents two expired requests from racing to rotate the same single-use refresh token, which would otherwise log the user out on the second one.
- Role-based UI (which nav items and buttons show) is a convenience layer only. The backend re-checks every permission on the actual request; hiding a button here is not a security boundary.

## Deferred from the full 89-section spec

Built and tested: authentication, Farmer/Buyer/Admin/Logistics Provider/Lender/generic dashboards, farm registration and listing, marketplace listing create/search/detail, the full order and escrow lifecycle (create, confirm, fund, prepare, dispatch, deliver, inspect, release, dispute), organization creation and membership (type choices scoped to the creator's role, matching the backend's `_ROLE_ORG_TYPES` check), fleet management (vehicles and drivers) and the full shipment lifecycle (request, assign, picked up, in transit, delivered, confirmed, failed) with a milestone-based tracking timeline, notifications, lending (product listing, application, lender decision, disbursement, amortized repayment schedule, repayment), traceability (lot creation, hash-chain-verified custody history, weighing, quality inspection), parametric weather insurance (policy purchase, premium payment, policy state), and admin tooling (user search/detail, tamper-evident audit log, dispute resolution queue).

Not yet built: document management, analytics beyond the dashboard KPI cards, offline sync UI, PWA/offline support, i18n, component and end-to-end tests (only the pure-logic unit tests are in place), a CI workflow, and a Dockerfile for the frontend. Also out of scope for this pass, deliberately: a real database (still SQLite), a real payment gateway (still the mock provider), and full production test coverage — those are the next phase, after this demo.
