# Copilot instructions — M365 Copilot Cowork Reporter

## What this project is

A self-contained, containerised collector and dashboard for **Microsoft 365 Copilot Cowork**.
Cowork has no single reporting API, so this joins several sources into one durable store:

| Signal | Source | Mode |
|---|---|---|
| Azure spend by resource group | Cost Management Query API | Automated (app-only) |
| Cowork events / resources touched | Purview audit (`CopilotInteraction`) | Automated (app-only) |
| Org context (dept, cost centre) | Microsoft Graph `/users` | Automated (app-only) |
| Cowork tasks / adoption | Admin centre Cowork usage report | CSV upload |
| Copilot credit consumption | Admin centre Cost Management | CSV upload |

## Stack (do not substitute without being asked)

- **API / engine:** Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, httpx, MSAL,
  APScheduler, Pydantic v2, psycopg v3.
- **Database:** PostgreSQL 16, schema via Alembic.
- **Frontend:** React + Vite + TypeScript + Tailwind + **Recharts**.
- **Packaging:** Docker + docker-compose; azd + Bicep → Azure Container Apps.

## Consumption vs Usage — MANDATORY

These are **separate resources and must never be blended into a single measure**. They join on
**user**, never on resource group — dollars and task counts answer different questions.

- **Consumption** = Azure spend + Copilot credit consumption.
- **Usage** = Cowork tasks, active days, adoption.

## Cowork identification in Purview audit

A `CopilotInteraction` record is Cowork when `CopilotEventData.AppHost == "cowork"` **or**
`AppIdentity == "Copilot.M365Copilot.CoworkChat"`. Audit answers *who / when / what-touched* —
never task volume or cost. **Never store prompt text.**

## Permissions

Graph application permissions: `AuditLogsQuery.Read.All` and `User.Read.All`, admin-consented.
Azure RBAC: `Cost Management Reader` on each subscription in scope.

> `AuditLogsQuery.Read.All` has been enforced since April 2026. The legacy `AuditLog.Read.All`
> silently returns zero Copilot records — never suggest it.

## Collectors

- Cost **restates** as charges settle: the cost collector does a rolling-window replace of the
  trailing N days each run. Keep it idempotent and self-healing.
- Audit events **upsert on their ID**, so backfill is safe to re-run. Backfill is chunked into
  monthly windows.
- CSV uploads replace rows for the matching report period / export scope.

## Security & auth

- Admin password gate by default; optional Entra SSO grants viewer access, or administrator
  access to members of `app_config.admin_group_id` (evaluated per request, fails closed when
  unset — see `api.auth.is_admin`). Sign-in is
  run by the app itself (`api/oidc.py`, OIDC auth-code + PKCE via MSAL), not by the hosting
  platform, so it works identically on and off Azure.
- The client secret is **Fernet-encrypted at rest and write-only in the API** — it can be set and
  replaced, never read back. Never log it or return it in a response.
- Never commit secrets. `.env`, `.azure/` and `*.local` are gitignored.

## UI conventions

This repo follows the shared Copilot solution UI standard used across the sibling reporters
(Usage Reporter, Prompt Analyser, Agent Quality Reporter):

- Blue Tailwind `brand` 50–950 palette; `.card` / `.input` / `.btn-primary` / `.btn-secondary`.
- Dark mode is authored with `dark:` variants **on the element** — never blanket
  `.dark main .x` descendant overrides.
- 240px left sidebar, solid `bg-brand-600` active nav pill, content `max-w-[1600px]`.
- Split-panel login; page titles `text-2xl font-bold`; card headings
  `text-sm font-semibold text-slate-700 dark:text-slate-200`.
- Recharts is the default charting library.
- Buttons say **Run now**, **Save**, **Test connection** — not "Refresh", "Sync" or
  "Save settings".

## Don't

- Don't blend Consumption and Usage into one number.
- Don't call unsupported internal admin-centre APIs — CSV export is the supported path.
- Don't store prompt text.
- Don't auto-seed or auto-wipe demo data; both are explicit user actions.
- Don't add a second charting library without a documented reason.
