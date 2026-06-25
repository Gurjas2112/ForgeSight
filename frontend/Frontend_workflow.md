# Frontend Workflow — ForgeSight

A **Next.js 16 / React 19** (App Router, TypeScript, Tailwind 4) control-room UI. It renders the
governed copilot, the plant dashboard (including a 3D digital twin), and role-based auth. It talks to
the FastAPI backend over REST and to Supabase for authentication only.

- **Run:** `npm install && npm run dev` → http://localhost:3000
- **Build / deploy:** `npm run build` → Vercel ([`frontend/vercel.json`](vercel.json))
- **API base:** `NEXT_PUBLIC_API_URL` (Railway in prod, `http://localhost:8000` in dev) — [`lib/api.ts`](lib/api.ts)

---

## 1. App structure (routes)

| Route | File | Purpose |
|---|---|---|
| `/` | `app/page.tsx` | Landing — hero, features, model showcase. |
| `/login`, `/signup` | `app/login`, `app/signup` | Auth forms with **client-side validation** (see §3). |
| `/dashboard` | `app/dashboard/page.tsx` | Plant overview: KPIs, equipment tiles, live alerts, model scorecard. |
| `/dashboard/admin` | `app/dashboard/admin/page.tsx` | **Admin-only** system metrics (see §4). |
| `/dashboard/twin` | `app/dashboard/twin/page.tsx` | 3D digital twin (react-three-fiber). |
| `/dashboard/{evidence,work-orders,incidents,spares,reliability,leadership}` | … | Dashboard modules (live backend data). |
| `/equipment/[id]` | `app/equipment/[id]/view.tsx` | Equipment console + inline contextual copilot sidebar. |

Layouts: [`app/layout.tsx`](app/layout.tsx) (AuthProvider + Navbar + **global CopilotWidget**),
`app/dashboard/layout.tsx` (DashboardTabs).

---

## 2. State & data fetching

- **Auth state:** [`components/AuthProvider.tsx`](components/AuthProvider.tsx) — React Context
  (`useAuth() → {session, email, role, loading, signOut}`); role read from JWT `app_metadata`.
- **Route guard:** [`components/AuthGuard.tsx`](components/AuthGuard.tsx) — redirects to `/login` when
  auth is configured and there is no session.
- **API layer:** [`lib/api.ts`](lib/api.ts) — typed `fetch` wrappers; `authHeaders()` attaches the
  Supabase bearer token; types mirror the backend cards in [`lib/types.ts`](lib/types.ts).
- Fetching is `useEffect` + `useState` with `cache: "no-store"` (no React Query).

---

## 3. Authentication UI (validation & verification)

Login/signup use Supabase, with validation mirrored from the backend
([`lib/validate.ts`](lib/validate.ts)):

- **Email:** RFC-ish regex — invalid input is flagged inline before submit.
- **Password:** ≥8 chars with ≥1 letter and ≥1 number.
- **Signup** adds a **confirm-password** field and disables submit until all fields are valid; backend
  `409` (duplicate email) and other errors surface as messages.
- Login no longer pre-fills the password (only the demo email hint remains).

The backend re-validates everything (`SignupIn` with `EmailStr` + password rules) — the client checks
are for UX, the server is the source of truth.

---

## 4. Admin dashboard

`app/dashboard/admin/page.tsx` is gated two ways: an **Admin** tab appears in
[`components/DashboardTabs.tsx`](components/DashboardTabs.tsx) only when `role === "admin"`, and the
page itself redirects non-admins to `/dashboard`. It fetches `GET /admin/metrics|users|audit` and
renders live stat cards (accounts, conversations, knowledge corpus, work orders, governance audit, open
alerts, plant availability, feedback), the live model scorecard, an accounts table, and a recent-audit
feed. Every value is a live DB aggregate — nothing is hardcoded.

---

## 5. Copilot (global, fixed, with history)

The maintenance copilot is a **global floating widget**
([`components/CopilotWidget.tsx`](components/CopilotWidget.tsx)), mounted once in the root layout and
shown to authenticated users on every page:

- **Fixed position & height** — a launcher button (bottom-right) opens a `fixed`, fixed-height panel
  (`h-[600px] max-h-[80vh]`) whose message list is `flex-1 overflow-y-auto`. As the conversation grows
  it scrolls **internally**; the page length never increases.
- **Per-user history** — a history switcher lists the caller's past conversations (`GET /chat/sessions`)
  and restores any of them (`GET /chat/sessions/{id}/messages`), with each message showing a
  **timestamp**. The active session id is remembered in `localStorage` (keyed by user email) so a reload
  resumes the last conversation. A "new chat" button starts a fresh session.
- Renders the same typed cards (`components/Cards.tsx`), HITL approval panel, and evidence drawer as the
  equipment-page sidebar.

The equipment page keeps its inline, equipment-scoped copilot
([`components/Sidebar.tsx`](components/Sidebar.tsx)) for contextual investigation.

---

## 6. Key components

`Navbar` · `DashboardTabs` · `Cards` (typed agent cards) · `ModelScorecard` (live inference) ·
`SensorTrend` (Recharts) · `PlantTwin3D` (react-three-fiber) · `ui.tsx` (badges/pills/chips).

---

## 7. Build & verify

```bash
cd frontend
npm install
npx tsc --noEmit      # type safety
npm run build         # production build (run by Vercel)
npm run dev           # http://localhost:3000
```

Deployment and env vars: [`../README.md`](../README.md) (Deploy section). Backend contract:
[`../backend/Backend_workflow.md`](../backend/Backend_workflow.md).
