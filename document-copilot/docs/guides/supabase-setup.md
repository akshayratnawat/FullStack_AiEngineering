# Supabase setup

We use Supabase for **Postgres** (users, chats, source documents, chunks, embeddings, and citations) and **Auth** (email sign-in only). You need one hosted Supabase project before wiring up `backend/` and `frontend/`.

## 1. Create an account

1. Go to [supabase.com](https://supabase.com) and sign up (GitHub or email).
2. Confirm your email if prompted.
3. You land in the [dashboard](https://supabase.com/dashboard). The free tier is enough for local development.

## 2. Create a project

1. Open [New project](https://supabase.com/dashboard/new).
2. Pick your organization (a personal org is created automatically on first signup).
3. Set a **project name** (e.g. `Document Copilot`).
4. Choose a **database password** — save it somewhere safe; you need it for direct DB access and `supabase link`.
5. Pick a **region** close to you.
6. Click **Create new project** and wait until status is healthy (~1–2 minutes).

## 3. Collect credentials

You need these values in backend and frontend env config. Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env`, then paste the values in. `.env` files are gitignored; never put real values in `.env.example`.

**Start here: open your project and click the `Connect` button in the top bar.** The Connect panel shows the project URL, the API keys and the database connection strings in one place, so you rarely need to hunt through Project Settings. (The older paths under **Project Settings** still work and are listed in the table as a fallback.)

Supabase renamed its keys in the newer dashboard. Old docs and our `.env.example` variable names still say "anon" and "service_role"; the new names map onto the same variables:

| Value | Where to find it | Looks like | Goes in |
| ----- | ---------------- | ---------- | ------- |
| **Project URL** | **Connect** panel, or **Project Settings** → **API** (may be labelled **Data API**) → "API URL" box. **Remove the trailing `/rest/v1/`.** | `https://<project-ref>.supabase.co` | `SUPABASE_URL` (backend), `VITE_SUPABASE_URL` (frontend) |
| **Publishable key** (formerly *anon / public*) | **Connect** panel, or **Project Settings** → **API Keys** → **Publishable key** → `default` | `sb_publishable_...` | `SUPABASE_ANON_KEY` (backend), `VITE_SUPABASE_ANON_KEY` (frontend) |
| **Secret key** (formerly *service_role*) | **Project Settings** → **API Keys** → **Secret keys** → `default` (click the eye icon to reveal) | `sb_secret_...` | `SUPABASE_SERVICE_ROLE_KEY` (**backend only**) |
| **Database connection string** | **Connect** panel → connection string / **URI** (see "Which connection string" below), or **Project Settings** → **Database** | see below | `DATABASE_URL` (backend) |
| **Database password** | What you set at project creation. The connection string shows `[YOUR-PASSWORD]` as a placeholder; reset the password under **Project Settings** → **Database** if lost. | — | Inside `DATABASE_URL`; URL-encode special characters (`@` → `%40`, `#` → `%23`) |
| **Project ref** | The first part of the Project URL, or the dashboard URL `supabase.com/dashboard/project/<ref>` | `abcdefghijklmnop` | CLI commands |

### Which connection string to use

The Connect panel offers three database connection options:

| Option | Host / port | Use for |
| ------ | ----------- | ------- |
| **Direct connection** | `db.<ref>.supabase.co:5432` | Preferred for Alembic migrations. On the free plan it is often **IPv6-only**, so it can fail on networks without IPv6 (common on home / Windows setups). |
| **Session pooler** | `aws-0-<region>.pooler.supabase.com:5432`, user `postgres.<ref>` | Fallback if Direct fails. Works over IPv4 and supports migrations. |
| **Transaction pooler** | `...pooler.supabase.com:6543` | **Do not use for migrations** (no session-level features). |

Try **Direct** first; if you get a connection error, switch `DATABASE_URL` to the **Session pooler** string.

### Which key is safe where

- **Publishable key** — safe in the browser (it is bundled into the frontend), because Row Level Security limits what it can do.
- **Secret key** — bypasses all access rules. Backend only. Never put it in git, the frontend, `.env.example`, screenshots or chat. If it leaks, rotate it in the dashboard.
- Only variables prefixed `VITE_` reach the browser, so keep secrets in `backend/.env` and never give them a `VITE_` prefix.

### Step by step

1. Open your project and click **Connect** in the top bar.
2. Copy the **Project URL** (no `/rest/v1/` on the end) and the **Publishable key**.
3. Pick a database connection string: **Direct** first, **Session pooler** if Direct fails. Replace `[YOUR-PASSWORD]` with your database password (URL-encoded).
4. Go to **Project Settings** → **API Keys** and reveal the **Secret key**.
5. Create the two `.env` files and paste the values in as shown below. Do this yourself in your editor; don't paste secrets into chat tools or commits.

`backend/.env` (can hold everything, including secrets):

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=sb_publishable_...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
DATABASE_URL=postgresql://postgres:<url-encoded-password>@db.<project-ref>.supabase.co:5432/postgres
```

`frontend/.env` (public values only; this file is bundled into the browser):

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_...
```

From the CLI you can also print API keys:

```bash
supabase projects api-keys --project-ref <your-project-ref>
```

> If a key is rejected as invalid later, check that the installed `supabase` Python / `@supabase/supabase-js` version supports the new `sb_publishable_` / `sb_secret_` key format.

## 4. Auth settings (email only)

This app uses email auth only — no Google/SSO.

1. Dashboard → **Authentication** → **Providers**.
2. Leave **Email** enabled.
3. For local dev, you may want **Authentication** → **Email** → disable "Confirm email" so sign-up works without inbox access (re-enable for production).

## 5. Database schema management

Document Copilot uses Alembic from the Python backend to manage database schema. Do not create production tables manually in the Supabase dashboard.

Alembic migrations create and update:

- the `vector` extension for `pgvector`
- source document and chunk tables
- embedding columns
- generated full-text search columns
- HNSW and GIN indexes
- chat and citation tables
- row-level security policies

Use the direct/session database connection string for Alembic. Do not use the transaction pooler connection string for migrations.

From `backend/`:

```bash
uv run alembic upgrade head
```

See [Backend setup](backend-setup.md) for the Alembic workflow.

## Next steps

- [Backend setup](backend-setup.md) — Python service + Supabase client
- [Frontend setup](frontend-setup.md) — React app + `@supabase/supabase-js`
