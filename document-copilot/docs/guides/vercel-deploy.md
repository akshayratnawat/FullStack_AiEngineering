# Deploying on Vercel

Two Vercel projects from this one repository: the **backend** (FastAPI, as a Vercel Function) and the **frontend** (the static Vite build). Do them in this order, because each needs the other's address.

## Before you start

- The code is ready: `backend/vercel.json`, `frontend/vercel.json`, and the `SEARCH_DATABASE_URL` setting are in the repo. Nothing in the code needs changing to deploy.
- Never put a real key in a file that is committed. Every value below goes into the Vercel dashboard (Project, Settings, Environment Variables).

## 1. Backend project

1. Vercel, **Add New, Project**, import the GitHub repo.
2. **Root Directory:** `document-copilot/backend`. Framework preset: **FastAPI** (Vercel finds the app at `app/main.py`; no `/api` folder is needed). Python 3.12 (the default) is fine.
3. **Environment variables** (Production):

| Name | Value |
| ---- | ----- |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | from Supabase, Project Settings, API |
| `DATABASE_URL` | the **direct** connection string (used for migrations only, but the app requires it to start) |
| `SEARCH_DATABASE_URL` | Supabase, **Connect, Transaction pooler** string (port **6543**). This is what the app's searches use. |
| `OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL` | your Azure OpenAI resource and deployment names |
| `LLM_ALLOWED_EMAILS` | the addresses allowed to ask live questions, comma-separated (for example your own). Required. |
| `ALLOWED_ORIGINS` | the frontend's address, for example `https://your-app.vercel.app` (add it after step 2, then redeploy) |

4. Deploy. Open `https://<backend>.vercel.app/health`: it should answer `{"status":"ok"}`.

**Why the transaction pooler:** each function instance opens its own database connections, and many can run at once. Supabase's session pooler allows only 15 clients in total (we hit that limit on one laptop). The transaction pooler is built for this. The app then keeps no pool of its own and turns off prepared statements, because the pooler hands each query to whichever database connection is free.

**Why `maxDuration` is 300:** an answer can take minutes and streaming time counts against a function's limit. 300 seconds is the most the Hobby plan allows; on Pro it can be raised to 800 in `backend/vercel.json`.

## 2. Frontend project

1. **Add New, Project**, the same repository again.
2. **Root Directory:** `document-copilot/frontend`. Framework preset: **Vite** (not "Other": the rewrite in `vercel.json` can be ignored under "Other").
3. **Environment variables** (they are baked into the build, so changing one means redeploying):

| Name | Value |
| ---- | ----- |
| `VITE_API_BASE_URL` | the backend's address from step 1 (no trailing slash) |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | the same public values as the backend's |
| `VITE_CONTACT_URL` | your LinkedIn or a `mailto:` link (the "Contact" button) |

4. Deploy, then go back to the backend project, set `ALLOWED_ORIGINS` to this frontend's address, and **redeploy the backend**.

## 3. Supabase settings

- **Authentication, URL Configuration:** set **Site URL** to the frontend's address and add it under **Redirect URLs**. Otherwise a confirmation email links to localhost.
- **Authentication, Sign In / Providers:** **Allow new users to sign up** must be on for visitors to register.
- **Confirm email:** off is fine for a demo only while every address in `LLM_ALLOWED_EMAILS` already has an account (nobody can register it first). Turn it on before adding an address that has not signed up yet. Supabase's built-in email sender allows only a few emails per hour, so real traffic needs your own mail provider.

## 4. Protect the model key (Azure)

The only limit that holds even if the code has a bug is the one on the provider side: set a **monthly budget with alerts** and a **tokens-per-minute quota** on the Azure OpenAI resource. Live questions are limited to the approved addresses in code, but a budget is the backstop.

## 5. Check it works

1. Open the frontend's address and sign up with a test address: you should land on the new-chat screen as a visitor.
2. Click a sample question: it should show the research steps and the answer with sources.
3. Type your own question as that visitor: the "by invitation" notice should appear.
4. Sign in as an approved address and ask a live question: the answer should stream.
5. Refresh on a chat page (`/chat/...`): it should reload, not show a 404.

## Things to know

- **Preview deployments:** each one has its own address, which is not in `ALLOWED_ORIGINS`, so the browser will refuse its calls to the backend. Test on the production address, or add the preview address to `ALLOWED_ORIGINS`.
- **Changing the stored sample answers** (`backend/app/demo/answers.json`) needs a redeploy; the file is read when the app starts.
- **First request after idle** is slower, because the app builds its clients at startup.
- **If the frontend install fails** with a pnpm error, Vercel is probably using a different pnpm version from the one used locally (pnpm 11). Pin it with a `packageManager` field in `frontend/package.json` and set `ENABLE_EXPERIMENTAL_COREPACK=1` as an environment variable.
- **Nothing here has been tested on Vercel yet.** The settings follow Vercel's and Supabase's documentation; the first deploy is the real test.
