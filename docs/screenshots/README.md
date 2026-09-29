# How these screenshots are produced

Recorded so the next person recapturing them gets a consistent set rather than
a mix of widths, themes and datasets — which is what the previous set had
become.

## What is shown

Every shot is the app running against **demo data**, in a throwaway local stack
with **no tenant credentials configured at all**. No Graph call is possible, so
nothing here touches a real tenant and no real person's activity appears. The
six people in the shots are the fictional Avanoso cast from
`scripts/seed_demo.py`.

## The recipe

1. Bring up a local stack with its own database, on a machine with Docker
   Compose:

   ```bash
   cp .env.example .env         # API_PORT=8001, DB_PORT=5433
   # set SECRET_KEY, FERNET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD
   # leave every Entra/Azure field empty
   docker compose build api worker
   docker compose up -d
   ```

2. Seed the demo data. This also binds the local admin account to a seeded
   directory user, which is what makes the personal pages reachable without
   Entra sign-in:

   ```bash
   docker compose exec api python scripts/seed_demo.py --reset
   ```

3. Sign in as the admin account and drive a browser at **1440 px wide**. That
   width is deliberate: it is an ordinary laptop, and it is the width the
   Tenant users table was trimmed to fit (see the comment in
   `frontend/src/pages/UsersPage.tsx`). A wider window hides column-overflow
   problems rather than revealing them.

4. Capture each page at viewport height, not `fullPage` — a full-page capture
   of a long form produces an unreadable strip in a README.

5. For the dark variants, use the **Light/Dark toggle in the sidebar** rather
   than setting `localStorage.ccr_theme` directly. Setting storage by hand
   leaves React's theme state stale, so the toggle in the screenshot says the
   wrong thing.

## Checks worth doing before you keep a shot

- **Charts render fully.** Recharts' `ResponsiveContainer` occasionally paints
  a chart before it has measured its width, which produces a series crammed
  into the left third of the axis. It looks like missing data and is not.
  Re-navigate and re-shoot; compare against the API response if unsure.
- **Tables fit their card.** In the console:

  ```js
  const t = document.querySelector('table'), c = t.closest('div');
  ({ table: t.scrollWidth, container: c.clientWidth });
  ```

  If `table > container` the rightmost column is cut off, and on Tenant users
  that is the Licence column — the one people opened the page for.
- **No real identifiers.** Everything visible should be `@avanoso.com`.

## The set

| File | Page | Theme |
|---|---|---|
| `login.png` | Sign-in | light |
| `overview.png` / `overview-dark.png` | Overview | both |
| `briefing.png` / `briefing-dark.png` | Executive briefing | both |
| `personal.png` / `personal-dark.png` | Your activity | both |
| `tenant-users.png` / `tenant-users-dark.png` | Tenant users | both |
| `consumption.png` | Consumption | light |
| `usage.png` | Usage | light |
| `settings.png` | Settings | light |
| `about.png` | About | light |

The four screens that changed most in the consistency pass carry both themes,
because dark mode is where the bug they were fixing lived: the old bespoke card
used the same colour as the page background, so every card was invisible.
