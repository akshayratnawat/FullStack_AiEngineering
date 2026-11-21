# Document Copilot — Guided Build

Build a production-style **RAG application** from scratch: analysts ask plain-English questions about SEC filings and get answers with citations to the exact filing and passage. You will build it **step by step with an AI coding assistant**, and understand every line.

> **Status:** work in progress. Steps are added in the order the project is actually built. Anything not yet written is listed in the [roadmap](#roadmap).

---

## How to use this guide

Every step has the same shape:

| Block | What it gives you |
| ----- | ----------------- |
| **Goal** | The one thing this step achieves. |
| **Why** | Why the project needs it, so you are not copying blindly. |
| **Prompt the AI** | The exact prompt to give your AI coding assistant (Claude Code, Cursor, etc.). |
| **What you should get** | The result to expect, including a reference solution you can compare against. |
| **Verify** | A command and the output that proves it worked. |
| **Check your understanding** | Questions a learner actually asked, with answers. Try to answer before reading. |
| **Common mistakes** | Things that went wrong on the real build, and the fix. |

**Working rhythm (important):**

1. Do **one** step at a time. Don't ask the AI for "the whole backend".
2. Before you accept anything the AI wrote, ask it to **explain what it did and why**.
3. Run the **Verify** block. Only then tick the step and move on.
4. Never paste real keys or passwords into an AI chat. Edit `.env` files yourself in your editor.

**Your AI's output will differ in wording from the reference solutions.** That is fine. Compare the behaviour and the checks, not the exact text.

---

## What you are building

**The problem.** Financial analysts spend about half their week opening SEC filings, scanning for sections, copy-pasting passages and comparing year over year. That intake work is boring, necessary and repetitive.

**The product.** An internal chatbot where an analyst can:

- ask questions in plain English about filings in the corpus,
- get an answer that cites the specific filing and passage,
- see the underlying passage and verify it in one click,
- log in with email, and see their own past conversations.

**The rule that shapes everything: trust.** The bot must never invent facts, must always cite, and must say "not enough evidence" when the corpus can't answer. A wrong but confident answer is worse than no answer.

Full brief: [docs/problemStatement.md](docs/problemStatement.md). Target design: [docs/architecture.md](docs/architecture.md).

**Stack (fixed for this project):**

| Layer | Technology |
| ----- | ---------- |
| Backend | Python 3.12+, FastAPI, Pydantic v2 |
| Frontend | Vite + React + TypeScript, Tailwind, shadcn/ui |
| Database + auth | Supabase (Postgres, `pgvector`, full-text search, email auth) |
| Migrations | SQLAlchemy models + Alembic |
| LLM + embeddings | OpenAI |
| Agent layer | PydanticAI |
| Hosting | Railway |

---

## Part 0 — Before you write code

### Step 0.1 — Install the tools

**Goal:** have `uv` (Python project manager) at version 0.13 or newer.

**Why:** `uv` creates the virtual environment, pins dependencies and runs commands. The backend's `pyproject.toml` uses two settings, `exclude-newer = "7 days"` (never install a package version younger than a week, a defence against compromised releases) and `add-bounds = "exact"` (pin exact versions). Old uv versions do not know these settings and **silently ignore them**, which quietly breaks the safety rule.

**Do it** (no AI needed):

```bash
# Install (Windows PowerShell):
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Update an existing install:
uv self update
```

**Verify:**

```bash
uv --version     # expect 0.13 or newer
```

**Common mistakes**

- **Windows: `uv self update` fails with "The process cannot access the file '...uvx.exe' because it is being used by another process."** Something (an editor extension or an MCP server) is running uv in the background. Close that program, or stop the `uv` / `uvx` processes, then update again.
- **A warning like `unknown field add-bounds`** means your uv is too old. Update it.

### Step 0.2 — Create the external accounts and keys

**Goal:** a Supabase project and an OpenAI API key, with the values written down somewhere safe.

**Why:** Supabase holds the database and handles login; OpenAI produces embeddings and answers. Everything from the database step onward needs them.

**Do it:** follow [docs/guides/supabase-setup.md](docs/guides/supabase-setup.md) for Supabase (account, project, Project URL, keys, connection string). For OpenAI, create a key at platform.openai.com/api-keys and **enable billing**; requests fail without it.

**What you should have by the end:**

| Value | Looks like | Secret? |
| ----- | ---------- | ------- |
| Supabase Project URL | `https://<project-ref>.supabase.co` (no `/rest/v1/` on the end) | No |
| Supabase publishable key | `sb_publishable_...` | No (browser-safe) |
| Supabase secret key | `sb_secret_...` | **Yes, backend only** |
| Database connection string | `postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres` | **Yes** |
| OpenAI API key | `sk-...` | **Yes** |

**Common mistakes** (all from the real build)

- **Pasting the "API URL" as the project URL.** The dashboard shows `https://<ref>.supabase.co/rest/v1/`. Remove `/rest/v1/`; the client libraries add it themselves.
- **Old key names.** Newer Supabase dashboards say **Publishable key** (formerly *anon*) and **Secret key** (formerly *service_role*). They go into the variables still called `..._ANON_KEY` and `..._SERVICE_ROLE_KEY`.
- **Connection string on the transaction pooler (port 6543).** Database migrations later need a direct or session connection (port 5432). If the direct connection fails because your network has no IPv6, use the **Session pooler** string instead.
- **Secret key in the frontend.** Never. Only the publishable key may reach the browser.

### Step 0.3 — Set up the repository and the AI's rules file

**Goal:** a git repository with the project skeleton, and a rules file your AI assistant reads automatically.

**Why:** an AI assistant makes far better decisions when the repo tells it the stack, the conventions and the things to avoid. This project keeps those rules in a file at the repo root and in each service folder, so every prompt in this guide starts from the same ground rules.

**What the rules files contain** (summary; the files themselves are in the repo):

- The **fixed stack** and "don't propose alternatives without a stated reason".
- A **dependency policy**: write it yourself unless the library is genuinely hard to get right; justify every new runtime dependency.
- **Configuration rule**: one settings module per service is the only place that reads environment variables; fail fast if something required is missing.
- **Code style**: small obvious functions, no premature abstraction, validate only at boundaries, comments explain *why* not *what*.
- **Backend rules** ([backend/CLAUDE.md](backend/CLAUDE.md)): async request handlers, SQLAlchemy + Alembic for schema, tests required for ingestion, retrieval, citation extraction and grounding.
- **Frontend rules** (`frontend/CLAUDE.md`): plain React SPA (not Next.js), pnpm only, no HTTP library beyond `fetch`, no frontend tests.

**Which file name the AI reads:** Claude Code reads `CLAUDE.md`, not `AGENTS.md`. Other tools (Cursor, Codex) read `AGENTS.md`. This project uses `CLAUDE.md`. If you want both, keep `AGENTS.md` as the real file and create a `CLAUDE.md` that contains the single line `@AGENTS.md`.

**Verify:** start your AI assistant in the repo root and ask: *"What stack and dependency policy does this project use?"* It should answer from the rules file without being told.

### Step 0.4 — Branching

**Goal:** never build directly on `main`.

**Do it:**

```bash
git checkout -b develop main        # create develop from main and switch to it
```

Work on `develop`. When a step is done and checked, merge it into `main`.

### Step 0.5 — Download the sample SEC filings

**Goal:** a local folder of real 10-K annual reports (the corpus the app will answer questions about), plus a `manifest.json` describing every file.

**Why:** the whole product is "answers grounded in source documents". Having real filings on disk early lets you look at the raw material (HTML, tables, sections) before designing parsing and chunking, which is where answer quality is won or lost. The script uses only the Python standard library, so it needs no backend setup and can run before anything else.

**Prompt the AI**

```text
Write data/download.py, a standard-library-only Python 3.12 script (no pip packages) that
downloads recent 10-K filings from SEC EDGAR.

Config at the top of the file, each with a one-line comment:
- USER_AGENT: SEC requires one that identifies the requester (name + email). Use a clear
  placeholder I will replace.
- TICKERS: AAPL, MSFT, NVDA, AMZN, GOOGL, JPM, META, TSLA
- FILINGS_PER_COMPANY = 5
- OUTPUT_DIR = a "downloads" folder next to the script
- CLEAR_OUTPUT_DIR = True (wipe previous downloads so each run starts clean)
- COMPANY_CIKS: a dict from ticker to 10-digit CIK. EDGAR identifies companies by CIK,
  not ticker. Look the CIKs up from EDGAR itself; do not guess them.

Behaviour:
- For each ticker, fetch https://data.sec.gov/submissions/CIK<cik>.json. Older filings
  live in extra paginated files listed under filings.files, so fetch those too and stop
  early once enough filings are found.
- Keep only form "10-K", for the last FILINGS_PER_COMPANY completed years. Bucket by the
  fiscal period end (reportDate), falling back to filingDate.
- Download each filing's primary document from the EDGAR Archives URL (accession number
  without dashes, CIK without leading zeros).
- Save to downloads/<year>/<ticker>_<form>_<filingDate>_<accession><ext>.
- Sleep 0.2 s between downloads to stay under SEC's 10 requests/second limit.
- Write downloads/manifest.json: source, generated_at_utc, form, downloaded_count, and
  per filing: ticker, cik, form, filing_date, report_date, accession_number,
  primary_document, source_url, local_path (relative to downloads/).
- Small functions, a module docstring explaining the output layout, and short comments
  that explain WHY, not WHAT. Make sure the downloads folder is gitignored (keep a
  .gitkeep so the folder exists in git).

Run it with `uv run data/download.py` and show me the output.
```

**What you should get:** `data/download.py` (about 150 lines) and, after running it, this layout:

```text
data/downloads/
├── 2021/  aapl_10-k_<date>_<accession>.htm, msft_..., ...
├── 2022/
├── 2023/
├── 2024/
├── 2025/
└── manifest.json
```

With the 8 tickers and 5 years, expect **40 filings**. The file names and years depend on each company's fiscal calendar, so folders can hold a different number of files each.

**Before you run it:** open the script and replace the placeholder `USER_AGENT` with your own name and email. SEC asks for an identifying contact and can block anonymous clients.

**Verify**

```bash
uv run data/download.py
# Downloading AAPL filings... (one line per ticker)
# Downloaded 40 filing(s) to .../data/downloads
```

Then check the manifest: `downloaded_count` should be 40, and every `local_path` should point to a file that exists.

**Check your understanding**

- *Why CIKs and not tickers?* EDGAR's APIs are keyed by CIK (Central Index Key). The ticker is only our label, so the script keeps a ticker-to-CIK map.
- *Why fetch extra "paginated" submission files?* The main response lists only recent filings; older ones are in separate files named under `filings.files`.
- *Why bucket by `reportDate`?* A 10-K filed in early 2024 describes fiscal year 2023. The period end date puts the filing in the year it describes.
- *Why `time.sleep(0.2)`?* SEC allows at most 10 requests per second; this keeps us well under it.
- *Why is `downloads/` gitignored?* The files are large and can be re-created by the script. The `manifest.json` is just as reproducible.

**Common mistakes** (both happened on the real build)

- **`HTTP Error 404: Not Found` partway through.** A ticker's CIK in `COMPANY_CIKS` was wrong, so EDGAR had no such submissions file. When we added JPM, META and TSLA with incorrect CIKs, the run died at JPM. The correct 10-digit values are JPM `0000019617`, META `0001326801`, TSLA `0001318605`. To find any company's CIK, search the company on sec.gov/edgar/searchedgar/companysearch. **Never guess a CIK.**
- **Forgetting to add a new ticker to `COMPANY_CIKS`.** Every ticker in `TICKERS` needs an entry, or the script fails with a `KeyError`.
- **Leaving the placeholder `USER_AGENT`.** It can work for a while and then be rejected. Use your real contact.
- **`CLEAR_OUTPUT_DIR = True` deletes the previous run.** Set it to `False` if you want to keep earlier downloads.

---

## Part 1 — The backend

Work from the `backend/` folder unless a step says otherwise.

### Step 1 — Install the backend dependencies

**Goal:** declare every library the backend will use, pinned to exact, at-least-a-week-old versions.

**Why:** later steps import these libraries. Declaring them once, with exact versions in `pyproject.toml` and a lock file, makes the project reproducible: everyone gets identical versions.

**Prompt the AI**

```text
We're setting up the Python backend in backend/ using uv. Read backend/CLAUDE.md first.

1. Run `uv sync` to create the virtual environment.
2. Add these runtime dependencies with `uv add`: fastapi, uvicorn, pydantic,
   pydantic-settings, httpx, structlog, openai, supabase, pydantic-ai, sqlalchemy,
   alembic, "psycopg[binary]", pgvector.
3. Add dev dependencies with `uv add --dev`: pytest, ruff, ipykernel.

Rules: use uv only (no pip). The pyproject.toml already sets exclude-newer = "7 days"
and add-bounds = "exact", so don't change those. After it finishes, explain in one
sentence per package what it is for in this project.
```

**What you should get:** `pyproject.toml` with every package pinned using `==`, a `uv.lock` file, and a `.venv/` folder. Dev tools sit in a separate `[dependency-groups]` section, so they are not deployed.

| Package | Role in this project |
| ------- | -------------------- |
| `fastapi`, `uvicorn` | The web framework and the server that runs it. |
| `pydantic`, `pydantic-settings` | Data validation, and typed settings loaded from the environment. |
| `httpx` | Outbound HTTP calls. |
| `structlog` | Structured logging. |
| `openai` | LLM answers and embeddings. |
| `supabase` | Supabase Python client (database access and auth). |
| `pydantic-ai` | Typed orchestration of the LLM agent. |
| `sqlalchemy`, `alembic` | Describing the schema in code, and migrations that apply it. |
| `psycopg[binary]` | Postgres driver. |
| `pgvector` | Vector column support for similarity search. |
| `pytest`, `ruff` (dev) | Test runner, and linter/formatter. |
| `ipykernel` (dev) | Lets Jupyter notebooks (and VS Code's notebook support) run code inside the backend's environment. Used later to inspect chunks and try queries. |

**Verify:**

```bash
uv run python -c "import fastapi, pydantic_settings; print('ok')"
```

Expected: `ok`.

**Check your understanding**

- *What does `uv sync` do?* It makes the `.venv/` match `pyproject.toml` and `uv.lock`: creates the environment if missing, installs the locked packages, removes extras.
- *What is the difference between `uv sync`, `uv add` and `uv run`?* `sync` installs what is already declared. `add` declares and installs a new package. `run` executes a command inside the environment (and syncs first if needed).
- *What does `--dev` do?* It records the package in a separate group that is not installed in production.
- *What does `ipykernel` do?* A notebook needs a "kernel" to run each cell. `ipykernel` is the Python kernel, so with it in `backend/.venv` you can open a notebook, pick that environment, and run `from app.config import settings`. It is dev-only, so production doesn't carry it.
- *What are `pytest` and `ruff` for?* `pytest` runs your tests (does the code behave?). `ruff` lints and formats (is it written cleanly?).

**Common mistakes**

- **`unknown field add-bounds` warning, or `>=` ranges instead of `==`.** Your uv is too old (Step 0.1).
- **`No solution found ... was published after the exclude newer time`.** A package was added by an old uv that ignored the 7-day rule. Remove the offending dependencies and re-add them with the current uv.

### Step 2 — Create the `.env` file

**Goal:** a local, git-ignored file holding your secrets and settings.

**Why:** secrets must never live in code or in git. The app reads them from the environment at startup. `.env.example` is the committed template (placeholders only); `.env` is your private copy (real values).

**Do it yourself** (do not give real keys to the AI):

```bash
cp .env.example .env
```

Then open `backend/.env` in your editor and fill in:

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=sb_publishable_...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
DATABASE_URL=postgresql://postgres:<url-encoded-password>@db.<project-ref>.supabase.co:5432/postgres
OPENAI_API_KEY=sk-...
```

Optional, with defaults: `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`, `OPENAI_EMBEDDING_DIMENSIONS=1536`, `ALLOWED_ORIGINS=http://localhost:5173`.

If your database password contains special characters, URL-encode them (`@` becomes `%40`, `#` becomes `%23`).

**Verify:** `git status` must **not** list `.env`. To be sure it is ignored: `git check-ignore -v backend/.env` should print a rule.

**Check your understanding**

- *Why is `.env` safe from git but `.env.example` is not ignored?* The root `.gitignore` ignores `.env` and `.env.*` but explicitly allows `.env.example`, because the template with placeholders belongs in the repo.

**Common mistakes**

- **Renaming `.env.example` instead of copying it.** Git then sees the template as deleted. Use `cp`, or restore it with `git restore backend/.env.example`.
- **Putting a secret in `.env.example`.** It is committed; it must hold placeholders only.

### Step 3 — Write the settings module `app/config.py`

**Goal:** one module that loads and validates all environment config, used by the whole backend.

**Why:**

- **Single source of truth.** Every other file does `from app.config import settings`. Nobody calls `os.getenv` anywhere else.
- **Fail fast.** A missing variable stops the app at startup with a clear error, instead of crashing mid-request when a user triggers the first call.
- **Typed.** `openai_embedding_dimensions` is a real integer, not the text `"1536"`.
- **Safe printing.** Secrets wrapped in `SecretStr` show as `**********` in logs and tracebacks.

**Prompt the AI**

```text
Create backend/app/config.py. Read backend/CLAUDE.md first; its configuration rules apply.

Requirements:
- Use pydantic-settings (BaseSettings) in a class called Settings, and export one
  instance: `settings = Settings()`.
- Load backend/.env using an ABSOLUTE path built from __file__ (so it works no matter
  which directory the process starts in). Ignore extra variables in .env.
- Required fields (no defaults, so startup fails if missing): supabase_url (plain str),
  and supabase_anon_key, supabase_service_role_key, database_url, openai_api_key
  (all SecretStr, because they are secrets).
- Optional fields with defaults: openai_embedding_model="text-embedding-3-small",
  openai_embedding_dimensions=1536 (note it must match the pgvector column size),
  allowed_origins="http://localhost:5173" (comma-separated string).
- A `cors_origins` property that splits allowed_origins on commas, strips whitespace
  and drops empty entries, returning list[str].
- Do not read or print my .env file; it contains secrets.
- Comments: only where the reason isn't obvious. Crisp, one line, explain WHY not WHAT.

When done, explain to me: what model_config is and where it is used, what SecretStr
does, and why required fields have no default.
```

**What you should get:** a file close to the reference below. Compare behaviour, not exact wording.

```python
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path, so .env is found no matter where the process is started from.
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """All environment config for the backend. Field `foo_bar` reads env var `FOO_BAR`."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Fields without a default are required: startup fails if they are missing.
    # SecretStr hides the value in logs and tracebacks; use .get_secret_value() to read it.
    supabase_url: str
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr
    database_url: SecretStr  # direct/session connection (it contains the DB password)
    openai_api_key: SecretStr

    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536  # must match the pgvector column size

    # Comma-separated browser origins allowed to call the API (CORS).
    allowed_origins: str = "http://localhost:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


# Created once at import; every module does `from app.config import settings`.
settings = Settings()
```

**Why each part exists**

| Part | Why |
| ---- | --- |
| One `Settings` class | A single source of truth; adding or renaming a variable is a one-file change. |
| Fields with no default | Fail fast on missing config. |
| `SecretStr` | Hides keys and the database URL from logs and tracebacks. |
| `model_config` | A special attribute name that pydantic reads automatically when it builds the class. `env_file` says where `.env` is; `extra="ignore"` skips variables you haven't declared. |
| Absolute `ENV_FILE` | A plain `".env"` only works when started from `backend/`; this works from tests, notebooks and the editor's run button. |
| `cors_origins` property | `.env` can only store text, so origins are one comma-separated string; this converts it to the list FastAPI's CORS setting needs. |
| `settings = Settings()` at the bottom | Creates the object once, at import. The checks run right then. |

**Verify** (from `backend/`):

```bash
uv run python -c "from app.config import settings; print(settings.openai_api_key, settings.cors_origins)"
```

Expected: `********** ['http://localhost:5173']`. If a required value is missing you get a validation error naming the field.

**Check your understanding**

- *Where is `model_config` used? We never call it.* Pydantic looks for an attribute with exactly that name when the class is created. `SettingsConfigDict` is only a typed dictionary so your editor can autocomplete the option names. Rename it and `.env` stops loading.
- *Why `SecretStr` for `database_url` but a plain `str` for `supabase_url`?* The database URL contains the password; the Supabase project URL is public.
- *Why no `OPENAI_EMBEDDING_API_KEY` field?* Nothing uses it until the embedding step, so it is added then. Add a setting when a feature needs it.

**Common mistakes**

- **Settings load works in the terminal but fails in the editor or in tests.** The `.env` path was relative. Use the absolute `ENV_FILE`.
- **Asking the AI to "check the .env file".** It would read your secrets. Tell it not to open `.env`.

### Step 4 — Harden the settings with two validators

**Goal:** reject two classes of config mistake at startup with a clear message.

**Why:** "not empty" is not the same as "correct". Two mistakes happened in practice or are certain to:

1. **Placeholders left in.** Copy `.env.example`, forget to edit a line, and `sk-your-openai-api-key` passes the required-field check. The failure then appears much later as a confusing OpenAI or Supabase error. Better to stop at startup.
2. **Transaction pooler used for the database.** Alembic migrations need a session connection. Supabase's transaction pooler (port 6543) breaks them. The session pooler (port 5432) is fine and is the documented fallback when the direct connection fails over IPv4, so it must **not** be blocked.

Deliberately *not* added: URL-format checks or key-prefix checks. A malformed value fails loudly at first use, and extra rules are over-engineering at this stage.

**Prompt the AI**

```text
In backend/app/config.py add two pydantic field validators. Keep the existing behaviour.

1. reject_placeholders: for supabase_url, supabase_anon_key, supabase_service_role_key,
   database_url and openai_api_key, raise a ValueError if the value contains "your-"
   (case-insensitive). Every placeholder in .env.example contains "your-". Handle both
   plain str and SecretStr values. The error message must name only the field, NEVER
   include the value.

2. reject_transaction_pooler: for database_url, parse it with urllib.parse.urlparse and
   raise a ValueError if the port is 6543. Do NOT block other "pooler" hosts: the
   session pooler on port 5432 is allowed. Say in the message to use port 5432.

Put "your-" and 6543 in named module-level constants with a one-line comment each.
Then write a throwaway script OUTSIDE the project that checks: valid values pass, the
session pooler on 5432 passes, a placeholder in url/key/database_url is rejected with
the right message, 6543 is rejected, and cors_origins turns " http://a.com , ,http://b.com "
into ['http://a.com', 'http://b.com']. Run it and show me the output.
```

**What you should get:** two methods added to `Settings`, plus two constants at the top of the file.

```python
from urllib.parse import urlparse

from pydantic import SecretStr, ValidationInfo, field_validator

# Every placeholder value in .env.example contains this (e.g. "your-project-ref").
PLACEHOLDER_MARKER = "your-"
# Supabase transaction pooler port; Alembic migrations need a session connection.
TRANSACTION_POOLER_PORT = 6543

# ...inside class Settings:

    @field_validator(
        "supabase_url",
        "supabase_anon_key",
        "supabase_service_role_key",
        "database_url",
        "openai_api_key",
    )
    @classmethod
    def reject_placeholders(cls, value: str | SecretStr, info: ValidationInfo) -> str | SecretStr:
        # Catches a copied .env.example whose values were never filled in.
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if PLACEHOLDER_MARKER in raw.lower():
            # Name the field only; never echo the value.
            raise ValueError(f"{info.field_name} still has its .env.example placeholder")
        return value

    @field_validator("database_url")
    @classmethod
    def reject_transaction_pooler(cls, value: SecretStr) -> SecretStr:
        # Only the transaction pooler port is blocked; the session pooler (5432) is fine.
        if urlparse(value.get_secret_value()).port == TRANSACTION_POOLER_PORT:
            raise ValueError(
                "database_url uses the transaction pooler (port 6543); "
                "use the direct or session connection (port 5432)"
            )
        return value
```

(Add the `import` lines to the existing imports at the top of the file.)

**Verify:** the AI's throwaway script should print a pass line for each of these cases: valid values accepted, session pooler (5432) accepted, placeholder URL / OpenAI key / database URL each rejected with a message naming the field, transaction pooler (6543) rejected, and the origins list cleaned correctly. Then re-run the Step 3 check command; it must still print `********** ['http://localhost:5173']` with your real `.env`. That also proves your own `.env` has no placeholders and isn't on port 6543.

**Check your understanding**

- *Why not reject every host containing "pooler"?* The session pooler is the documented fix when the direct connection fails over IPv4 and it supports migrations. Only the transaction pooler (6543) breaks them.
- *Why must the error message not include the value?* A startup error often ends up in logs; echoing a key there would leak it.
- *Why didn't we validate more (URL format, key prefixes)?* Validate at boundaries only where a mistake is likely and costly. Other mistakes fail loudly on first use.
- *Where does `model_config` / the validator run?* Validators run when `Settings()` is created, i.e. at import of `app.config`.

**Common mistakes**

- **Writing the check as a test that imports `app.config`.** `settings = Settings()` runs at import and needs real env values, so a test would fail on any machine without your `.env`. Tests should build `Settings(_env_file=None, ...)` with fake values instead (this comes in the testing step).

### Step 5 — The FastAPI entrypoint `app/main.py`, and an import check

**Goal:** a running web server with one `/health` endpoint, proving that every installed library and the settings module load together.

**Why:**

- **A tiny working server first.** Every later feature (auth, chat, search) is a route added to this app. Proving the foundation works with one trivial endpoint makes later failures easier to locate.
- **Importing `app.config` here is deliberate.** It makes the server validate all environment config at startup, so a bad `.env` stops the app immediately.
- **CORS.** The browser app will run on `http://localhost:5173` and the API on `http://localhost:8000`. Browsers block calls between different origins unless the API explicitly allows them. The allowed list comes from `settings.cors_origins`.
- **`/health`.** A cheap "is it alive" check. Hosting platforms such as Railway use the same idea later.

**Prompt the AI**

```text
Create backend/app/main.py. Read backend/CLAUDE.md first.

- A FastAPI app titled "Document Copilot".
- Add CORSMiddleware using settings.cors_origins from app.config (allow all methods
  and headers). Do not read environment variables directly.
- One route: GET /health, an async def, returning {"status": "ok"}.
- At the bottom, an `if __name__ == "__main__":` block that imports uvicorn and runs
  the app, so `python app/main.py` also starts the server (docs/guides/backend-setup.md
  promises this). Add a one-line comment saying auto-reload needs the uvicorn command.
- Comments: only where the reason isn't obvious; short, explain WHY not WHAT.

Then verify, and show me the output of each:
1. Import every library listed in pyproject.toml, plus app.main, and report ok/FAIL for each.
2. Call /health in-process with FastAPI's TestClient.
3. Start the real server on a spare port (not 8000) for a few seconds, call /health with
   curl, and also send a CORS preflight (OPTIONS) with the header
   `Origin: http://localhost:5173`. Make sure the server is stopped afterwards.
Do not open or print my .env file.
```

**What you should get:**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings  # importing this also validates all env config

app = FastAPI(title="Document Copilot")

# The browser app runs on another origin (localhost:5173), so the API must allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    # Liveness check: lets you (and Railway later) confirm the server is up.
    return {"status": "ok"}


if __name__ == "__main__":
    # Lets `uv run python app/main.py` start the server. For auto-reload while
    # developing, use `uv run uvicorn app.main:app --reload` instead.
    import uvicorn

    uvicorn.run(app)
```

**Verify** (from `backend/`):

```bash
# 1. Every dependency and the app import cleanly:
uv run python -c "import fastapi, uvicorn, pydantic, pydantic_settings, httpx, structlog, openai, supabase, pydantic_ai, sqlalchemy, alembic, psycopg, pgvector; from app.main import app; print('ok', app.title)"

# 2. Run the server:
uv run uvicorn app.main:app --reload
```

(Once Step 6 is done you can also start it with `uv run python app/main.py`; this one has no auto-reload.)

Then open <http://127.0.0.1:8000/health> in a browser. Expected: `{"status":"ok"}`. FastAPI also generates interactive docs at <http://127.0.0.1:8000/docs>. Stop the server with `Ctrl+C`.

A header check from another terminal (the frontend's origin must be allowed):

```bash
curl -i -X OPTIONS http://127.0.0.1:8000/health -H "Origin: http://localhost:5173" -H "Access-Control-Request-Method: GET"
# expect: access-control-allow-origin: http://localhost:5173
```

**Check your understanding**

- *What does `uvicorn app.main:app` mean?* Run the server (`uvicorn`) using the variable `app` found in the module `app.main` (the file `app/main.py`).
- *Do I need the `if __name__ == "__main__":` block to run the server?* No. `uvicorn app.main:app` imports the file and never reaches that block. The block only matters for starting the server with `python app/main.py`, where Python runs the file as a script (`__name__` is then `"__main__"`). When the file is imported, the block is skipped.
- *Why doesn't the block use `reload=True`?* Reload needs uvicorn to start a second process, which requires the app as an import string (`"app.main:app"`). Keeping the block simple and using the uvicorn command for reload avoids that.
- *What does `--reload` do?* It restarts the server automatically when you save a file. Use it in development only.
- *Why `async def` for the route?* The backend rules say request handlers are async, so waiting on the database or OpenAI later doesn't block other requests.
- *Why does the import of `app.config` matter if `main.py` never uses it except for CORS?* It runs the validation. A missing or placeholder value stops the server before it serves anything.
- *Why can `from app.config import ...` work when `app` isn't an installed package?* Running from `backend/`, Python (and uvicorn) put the current folder on the import path. Step 6 adds the packaging that makes it work from any folder.

**Common mistakes**

- **`python app/main.py` runs and exits with no server.** The `if __name__ == "__main__":` block is missing; without it the file only defines the app. (This was a real omission on the first build.)
- **`python app/main.py` says `No module named 'app'`.** The package isn't installed yet: do Step 6, then `uv sync`.
- **Running from the wrong folder.** Start the server from `backend/`, not from the repo root, or `app.main` can't be found.
- **Port 8000 already in use.** Pick another with `--port 8001`.
- **A validation error on startup.** That is the settings check working; read the field name in the message and fix `backend/.env`.

### Step 6 — Make `app` an installed package (`pyproject.toml` build settings)

**Goal:** `from app.config import settings` works from *any* folder, notebook or tool, not just when you happen to be standing in `backend/`.

**Why:** until now it only worked because Python looks in the current folder first. Start from somewhere else (a Jupyter notebook, a test runner, an editor's run button, a script in another folder) and you get `ModuleNotFoundError: No module named 'app'`. Telling uv to build and install our own `app/` folder into the virtual environment fixes this permanently.

**Prompt the AI**

```text
In backend/pyproject.toml add the build settings so the local `app` folder is installed
into the virtual environment as a package:

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

Then run `uv sync`. Prove it worked with a before/after test: from a folder OUTSIDE
backend/ (for example your home folder), run backend/.venv's python with
`import app.config`. Show it failing before the change and working after. Don't open
or print my .env file. Explain what each of the three lines does.
```

**What you should get:** these sections in `backend/pyproject.toml`, placed after `[project]`:

```toml
# Build settings: they make uv install our own `app/` folder into the virtual
# environment as a package, so `from app...` imports work from any folder
# (notebooks, tests, editor run buttons), not just from backend/.
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# Which folder to package; hatchling can't guess it from the project name.
[tool.hatch.build.targets.wheel]
packages = ["app"]
```

**What each line does**

| Line | Meaning |
| ---- | ------- |
| `[build-system]` | Tells tools how to build this project into an installable package. Without it, uv treats the backend as a plain collection of scripts and installs nothing from it. |
| `requires = ["hatchling"]` | The build tool needed to do the building. `hatchling` is a small, widely used Python build backend. It is fetched only for building, not at runtime. |
| `build-backend = "hatchling.build"` | The entry point of that tool that uv should call. |
| `[tool.hatch.build.targets.wheel]` | Settings for hatchling when it makes a "wheel" (the standard installable package file). |
| `packages = ["app"]` | Which folder to package. Hatchling normally guesses from the project name (`document-copilot-backend`), finds no matching folder and fails, so we name `app` explicitly. |

After `uv sync`, uv installs `document-copilot-backend` into `.venv` in **editable** mode: it adds a link to your `app/` folder, not a copy. Edits to your code take effect immediately, with no reinstall.

**Verify**

```bash
cd backend
uv sync                      # builds and installs the project; look for "+ document-copilot-backend==0.1.0"
cd ~                         # go somewhere unrelated
<path-to>/backend/.venv/Scripts/python -c "from app.config import settings; print('import ok')"
```

(On macOS/Linux the interpreter path is `backend/.venv/bin/python`.) Expected: `import ok`. Before this step, the same command prints `ModuleNotFoundError: No module named 'app'`.

**Check your understanding**

- *Why add a build system to an app that is never published?* We don't publish it. Installing it into the environment is the cheap, standard way to make the `app` folder importable everywhere, so we don't need to hand-set `PYTHONPATH`.
- *Why did `uv.lock` change a lot?* The lock file is regenerated to include the project itself and the resolved build requirements. Review it, then commit it with `pyproject.toml`.
- *What is a wheel?* The standard packaged form of a Python project that installers use.
- *What is "editable"?* The environment points at your source folder instead of copying it, so changes are live.

**Common mistakes**

- **Wrong folder name in `packages`.** It must be the folder that actually holds the code (`app`). If hatchling can't find it, the build fails with an error naming the expected files.
- **Forgetting `uv sync` after editing `pyproject.toml`.** The change only takes effect once the project is rebuilt and installed.
- **Putting an `__init__.py` question here.** It works without one (Python treats `app` as a namespace package), though adding an empty `app/__init__.py` is the more conventional, explicit choice.

---

## Part 3 — The chat shell (backend)

### Step 7 — Threads, a streaming endpoint with a stubbed reply, and saving

**Goal.** Four routes, all behind sign-in: list threads, create a thread, load a thread's messages, and `POST /chat/stream`, which streams a canned assistant reply and saves the exchange when it ends. Another user's thread gives `403`.

**Why.** This is the vertical slice every later phase plugs into. Retrieval and the real agent will replace only the stub; the stream format, ownership checks and saving stay as built here. Doing it with a fake reply first means the chat UI can be built and tested before any LLM cost or retrieval bug is involved.

**Prompt the AI.**

> Add the chat backend for Phase 3. Routes: `GET /threads`, `POST /threads`, `GET /threads/{id}/messages`, `POST /chat/stream` (body `{threadId, messages}` in AI SDK UI-message format; stream the AI SDK UI message stream over SSE). Use `get_current_user` on every route. Use the user-scoped Supabase client for normal reads and writes so RLS applies; use the service client only to find a thread's owner (return 404 if missing, 403 if it is someone else's) and to create the `users` row. The assistant is a stub that streams a canned reply word by word. Save the user message and assistant message in one insert after the last text chunk and before `finish`; if saving fails, send an error event instead of `finish`. Name a new thread from the first 60 characters of its first question. Keep the files small: `database/chats.py`, `chat/messages.py`, `chat/streaming.py`, `chat/orchestrator.py`, `api/chat.py`. Add unit tests with an in-memory fake store; no network or database.

**What you should get.**

| File | Job |
| ---- | --- |
| `app/database/chats.py` | `ChatStore`: every chat read/write, plus the ownership lookup |
| `app/chat/messages.py` | AI SDK message ↔ stored row conversion; pulls the new question out of the request |
| `app/chat/streaming.py` | Writes the SSE events: `start`, `text-start`, `text-delta`…, `text-end`, `finish`, `[DONE]` |
| `app/chat/orchestrator.py` | One turn: the stub reply, then saving |
| `app/api/chat.py` | The four routes and the 403/404 check |
| `app/main.py` | Registers the router; creates the service client once at startup |

The key idea in `api/chat.py`: everything that can fail with a real HTTP status (401, 403, 404, 422) is checked **before** the `StreamingResponse` is returned. Once streaming starts the status is already `200`, so later failures can only be sent as an error event.

**Verify.**

```bash
cd backend
uv run pytest -q          # 34 passed
uv run ruff check app tests
uv run uvicorn app.main:app --port 8000
curl -i localhost:8000/threads                                 # 401 "Missing bearer token."
curl -i -H "Authorization: Bearer nope" localhost:8000/threads # 401 "Invalid or expired token."
```

Not yet verified live: a real signed-in call (`POST /threads`, then `/chat/stream`) against Supabase. That needs a real account's token and is the first thing to try when the chat UI exists.

**Check your understanding.**

- *Why not just use the user-scoped client for the 403 check?* RLS hides other people's rows, so a thread owned by someone else looks exactly like one that does not exist, and you would return 404. The service client can see who owns it.
- *Why save after streaming instead of before or during?* A dropped connection must not leave half an answer in the database. Saving before `finish` (not after `[DONE]`) lets a failed save surface as an error event.
- *Why does the server keep only the last message from the request?* The SDK resends the whole conversation each time, but earlier messages are already stored, and the stored copy is the one to trust.
- *Why do we create the `users` row ourselves?* Nothing does it at sign-up, `chat_threads` has a foreign key to it, and signed-in users can only read that table, so the service client creates it on the first thread.

**Common mistakes.**

- **Assuming the models' defaults apply.** The id (`uuid4`) and `updated_at` (`onupdate`) defaults live in the SQLAlchemy models, but this code writes through the Supabase API, which bypasses them. Without an explicit id the insert fails, and `updated_at` never changes.
- **Saving both messages in one statement without timestamps.** Both rows get the same database `now()`, so their order is undefined. Set `created_at` explicitly: question first, answer after.
- **Testing a server on `localhost`.** If another process already listens on that port on IPv6, `curl localhost:PORT` talks to it instead of uvicorn. Use `127.0.0.1` and a fresh port.
- **Hand-writing the SSE event names from memory.** They differ between AI SDK major versions; re-check them against the installed `ai` package when the frontend chat is added.

### Step 8 — The chat UI (frontend)

**Goal.** A sidebar of past conversations, a "New chat" button, and a chat screen that streams the stub reply and shows saved history after a reload, all behind the sign-in guard.

**Why.** It is the screen every later phase fills in: retrieval, citations and source passages all render inside this message list.

**Prompt the AI.**

> Build the Phase 3 chat UI. Install `ai` and `@ai-sdk/react` and **read their installed type definitions before writing code** (the API changes between major versions). Routes inside `ProtectedRoute`: `/` (empty state) and `/chat/:threadId`, sharing a layout with a sidebar. Sidebar: thread list (title or "New chat"), New chat button (creates the thread through `POST /threads`, then opens it), email and sign out. Chat screen: load stored messages from `GET /threads/:id/messages`, then `useChat` with a `DefaultChatTransport` pointed at `${VITE_API_BASE_URL}/chat/stream` with the Supabase bearer token and `body: { threadId }`. Show "Thinking…" while waiting, a cursor while streaming, a Stop button, and readable errors for 401/403/404 and network failures. No test runner; verify with `tsc`, lint and build.

**What you should get.**

| File | Job |
| ---- | --- |
| `src/lib/chat.ts` | Thread calls through `api`, the stream transport (it cannot use `api`: the SDK makes its own request), and `describeError` |
| `src/components/chat/ChatLayout.tsx` | Layout route; owns the thread list and refreshes it after each reply |
| `src/components/chat/ThreadSidebar.tsx` | List, New chat, email, sign out |
| `src/components/chat/ChatThread.tsx` | Loads history, shows loading/403/404 states |
| `src/components/chat/ChatSession.tsx` | `useChat` itself, one per thread (`key={threadId}`) |
| `src/components/chat/MessageList.tsx`, `MessageInput.tsx` | Display with auto-scroll; Enter sends, Shift+Enter is a new line |
| `src/pages/ChatHomePage.tsx`, `ChatThreadPage.tsx` | Route-level pages |

**Verify.**

```bash
cd frontend
pnpm tsc --noEmit && pnpm lint && pnpm build
```

The real check is manual, signed in: New chat → send a message → watch the reply stream → reload → the conversation is still there, and the sidebar title is your first question. Before that, the wire format was checked by running the real SDK `Chat` class in Node against the real FastAPI routes (fake user and store): status went `submitted → streaming → ready` with no error and the reply assembled correctly.

**Check your understanding.**

- *Why can't the stream use `api.post`?* `api` waits for a whole JSON response; the SDK needs to read the response as it arrives, so it does its own `fetch`. It reuses `getAccessToken` for the same token.
- *Why `key={threadId}` on the chat?* `useChat` keeps its state per mounted component. A new key throws the old state away, so one thread's messages never leak into another.
- *Why load history before mounting `useChat`?* The hook takes its starting messages once. Mounting it before the history arrives would start the chat empty.

**Common mistakes.**

- **Writing SDK code from memory.** The installed packages were `ai` 7 and `@ai-sdk/react` 4, newer than most tutorials. Reading the `.d.ts` files first took minutes and avoided guessing event names.
- **Testing on `localhost` against a server bound to `127.0.0.1`** (or the reverse). Pin the host (`--host 127.0.0.1`) and use that address in the URL.
- **Calling a state-setting function from `useEffect`.** The linter flags it; do the fetch inside the effect with a `cancelled` flag so leaving the page cancels it.

---

## Part 4 — The corpus and retrieval (backend)

### Step 9 — Chunk, embed and store the filings

**Goal.** Every filing in `source_documents` is split into chunks, each chunk is embedded, and the rows are stored in `document_chunks` with the section and filing details. Re-running never embeds (or pays for) a chunk twice.

**Why.** Retrieval can only find what is stored as small, embedded, searchable pieces. A whole 10-K is far too big to send to a model, and one vector per filing would blur everything together.

**Prompt the AI.**

> Add chunk ingestion. `app/embeddings.py`: an async client for the Azure OpenAI v1 API (the plain OpenAI SDK pointed at the resource URL; `model` is the Azure *deployment name*) and `embed_texts`, which returns one vector per text and fails loudly if the size is not 1536. `ingest/chunking.py`: split a filing's Markdown into chunks of at most 512 tokens, keeping tables intact, and record each chunk's section headings. `ingest/ingest_chunks.py`: read `source_documents`, chunk and embed in batches, insert rows with `chunk_index`, `section`, `token_count`, `embedding` and `chunk_metadata` (ticker, form, fiscal year, filing date, accession number, headings). Never send `search_vector`: Postgres generates it. Skip chunks already stored for a document. Flags: `--dry-run`, `--accession`, `--chunk-index`, `--force`. Add unit tests for chunking and embeddings with no network.

**What you should get.**

| File | Job |
| ---- | --- |
| `app/embeddings.py` | Embedding client and `embed_texts`; used by ingestion now and by retrieval for the question |
| `ingest/chunking.py` | Markdown → `Chunk` objects (content, section, headings, token count) |
| `ingest/ingest_chunks.py` | The script: chunk, embed, insert, skip what is stored |
| `app/config.py` | Gains `azure_openai_endpoint` (required, placeholder-checked) |

**Verify.** Do it small before doing it big:

```bash
cd backend
uv run python ingest/ingest_chunks.py --dry-run --accession 0000320193-25-000079   # 130 chunks, max 512 tokens
uv run python ingest/ingest_chunks.py --accession 0000320193-25-000079 --chunk-index 49
uv run python ingest/ingest_chunks.py --accession 0000320193-25-000079 --chunk-index 49  # "skipped 1 already stored"
uv run python ingest/ingest_chunks.py                                                    # everything
```

The one-chunk run stored Apple's FY2025 iPhone revenue table (485 tokens, 1536-number vector, section "Item 7. Management's Discussion…", `search_vector` filled in by Postgres). The full run finished with 40 filings and **11,240 chunks**, about 1.1M tokens billed on the final run.

**Check your understanding.**

- *Why test one chunk first?* A wrong deployment name, key or column fails on the first call. Finding that out on one chunk costs nothing; finding it out 5,000 chunks in costs money.
- *Why store `ticker`, `fiscal_year` and the rest inside every chunk?* Retrieval filters and citations need them, and it saves a join on every search.
- *Why is `search_vector` never sent?* It is a generated column; Postgres rebuilds it from `content` on every insert, so it can never drift out of sync.
- *How does a re-run know what to skip?* It lists the `chunk_index` values already stored for the document and embeds only the rest.

**Common mistakes.**

- **Using the model name where Azure wants the deployment name.** `OPENAI_EMBEDDING_MODEL` must be the name you gave the deployment.
- **A missing `AZURE_OPENAI_ENDPOINT`.** Settings fail on startup, so even `--dry-run` refuses to start. The client accepts the URL with or without the trailing `/openai/v1`.
- **Treating a crash as a restart.** The first full run died on a network error (`httpx.ReadError`) in the middle of an insert. Because chunks are skipped when already stored, re-running the same command finished the job and billed only the rest.
- **Piping a long run through `tail`.** The output only appears when the command ends, so you see nothing while it works. Redirect to a log file instead.

### Step 10 — Hybrid retrieval: semantic search, keyword search, fusion

**Goal.** `retrieve(engine, client, question, top_k, ticker, fiscal_year)` returns the best passages for a question: each with its fused score and the chunks on either side of it.

**Why.** Meaning search finds a passage worded differently from the question; keyword search finds exact terms such as "iPhone" or a figure. Each misses what the other catches, so both run and their rankings are merged.

**Prompt the AI.**

> Add retrieval under `app/retrieval/`. `queries.py`: a pgvector cosine-distance search over `document_chunks.embedding`, a full-text search over `search_vector`, and a fetch of chunks by (document, index); each returns a small `ChunkHit` dataclass and takes optional `ticker` and `fiscal_year` filters. `fusion.py`: Reciprocal Rank Fusion in plain Python, no library. `retriever.py`: embed the question, run both searches concurrently, fuse them, keep the top `top_k`, and attach neighbouring chunks. The Supabase API client cannot order by vector distance, so add `app/database/engine.py` with an async SQLAlchemy engine on `DATABASE_URL`. Unit tests with no network or database.

**What you should get.**

| File | Job |
| ---- | --- |
| `app/database/engine.py` | `create_search_engine()`: async engine for the retrieval queries |
| `app/retrieval/queries.py` | `semantic_search`, `keyword_search`, `get_chunks`, `or_tsquery` |
| `app/retrieval/fusion.py` | `reciprocal_rank_fusion`; `RRF_K = 60` |
| `app/retrieval/retriever.py` | `retrieve` and the `Passage` result |

**Verify.**

```bash
cd backend
uv run pytest tests/retrieval -q       # 6 passed
uv run ruff check app tests
```

Live, against the full corpus: "What was Apple's iPhone net sales revenue?" (ticker AAPL) returned the Item 7 MD&A chunks, and "How much revenue came from data center for NVIDIA?" (ticker NVDA) returned the Data Center revenue passages first. These were checked by eye, not by an automated test; an evaluation set comes later. To try your own questions, run `uv run python scripts/try_retrieval.py "your question" --ticker NVDA`; `app/retrieval/README.md` has the flow diagram and every default (top 8, 30 candidates per search, 1 neighbour each side, `RRF_K` 60).

**Check your understanding.**

- *Why does RRF use ranks, not scores?* Vector distances and text-search ranks are on different scales. Ranks are comparable, so there is nothing to normalise. A chunk found by both searches beats one found by only one.
- *What is `RRF_K = 60`?* It softens the gap between neighbouring ranks (`1 / (60 + rank)`). 60 is the value from the original paper; change it only if an evaluation shows a reason.
- *Why OR the keywords?* Postgres's usual query helpers AND every word, so one word the filing never uses returns nothing. ORing the words and ranking with `ts_rank_cd` suits a question-shaped query. Keeping only letters and digits also stops user text from injecting query syntax.
- *Why fetch neighbours?* A table or an explanation often runs across two or three chunks; the hit alone can cut it off.

**Common mistakes.**

- **Forgetting `greenlet`.** SQLAlchemy's async mode needs it. Install `sqlalchemy[asyncio]`, not plain `sqlalchemy`.
- **Running async psycopg on Windows' default event loop.** It fails with "cannot use the ProactorEventLoop". Use `SelectorEventLoop` for local scripts; Linux (Railway) is unaffected.
- **Searching all companies at once.** A question like "which company had supply-chain risk?" with no ticker returned only JPMorgan risk-management sections: the query matched "risk", and JPM has several times more chunks than the others. Filter by ticker, or search each company separately and compare.
- **Putting `-` or `&` characters from user text into a text-search query.** Always build the query from sanitised words, never from raw input.

## Part 5 — The document agent (backend)

### Step 11 — The agent's tools (`app/assistant/tools.py`)

**Goal.** Three bounded tools the agent can call to read the filings: `search_filings(query, ticker, fiscal_year)`, `read_chunk(chunk_id)` and `read_surrounding_chunks(chunk_id, window)`. Every passage a tool returns is recorded in `deps.retrieved`.

**Why.** The model can only read through these tools, so it cannot invent SQL. Recording what was returned makes citation checking exact: later, a citation is accepted only if its chunk id was actually shown to the model this turn.

**Prompt the AI.**

> Add `app/assistant/tools.py` with three PydanticAI tools. `search_filings` wraps `retrieve()` (with `neighbor_window=0`) and takes `ticker` as a `Literal` of the 8 tickers, so a made-up company is rejected before the database. `read_chunk` and `read_surrounding_chunks` (window 1 to 3) reuse `queries.get_chunks`, plus one new query `get_chunk_by_id` in `app/retrieval/queries.py`. Each tool returns numbered passages with the chunk id and filing metadata (ticker, form, fiscal year, filing date, section), and records every returned chunk in `ctx.deps.retrieved`. An unknown chunk id raises `ModelRetry` so the model can correct itself. Unit tests with a faked retriever and faked queries; no database, model or network.

**What you should get.**

| File | Job |
| ---- | --- |
| `app/assistant/deps.py` | `DocumentAgentDeps`: the engine, the embedding client, and the per-turn `retrieved` dict |
| `app/assistant/tools.py` | `search_filings`, `read_chunk`, `read_surrounding_chunks`, `Ticker`, `MAX_WINDOW = 3` |
| `app/retrieval/queries.py` | New `get_chunk_by_id` |
| `tests/assistant/test_tools.py` | Filters passed through, `retrieved` filled, unknown id retried, ticker enum, window bounds |

**Verify.**

```bash
cd backend
uv run pytest tests/assistant/test_tools.py tests/retrieval/test_queries.py -q   # 17 passed
uv run ruff check app tests
```

The bad-ticker check asserts that the tool's schema lists exactly the 8 tickers; PydanticAI enforces that list when the model calls the tool, so the test does not call the tool with a bad value.

**Check your understanding.**

- *Why record chunks in `deps.retrieved`?* The grounding validator will accept a citation only if its chunk id is in that dict. The model cannot cite a passage no tool showed it.
- *Why is `retrieved` created fresh each turn?* One turn's evidence must not leak into the next, or an old chunk could justify a new answer.
- *Why `neighbor_window=0` in search?* Search replies stay small. The model asks for surrounding text with `read_surrounding_chunks` only when a result looks cut off.
- *Why `ModelRetry` for an unknown id, not an error?* The message goes back to the model, which can then use an id from a search result instead of the whole run failing.

**Common mistakes.**

- **Letting tools hit the database with free-form input.** Keep the parameters typed and bounded (`Literal` ticker, `window` between 1 and 3).
- **Returning text without recording it.** A tool that skips `present()` shows the model a passage that the validator will later refuse to accept as a citation.
- **Clamping the window start.** Near the start of a document, `chunk_index - window` goes negative; the range starts at 0.

### Step 12 — The agent (`app/assistant/agent.py`)

**Goal.** `create_agent()` returns a PydanticAI agent that searches with the three tools and must answer as a `GroundedAnswer`. `answer_question()` runs one question and returns the answer with the passages it cites.

**Why.** A retry is cheap and fixes most citation slips, so the model gets one chance to repair its citations before the question is refused. Per-question caps keep cost and runaway tool loops predictable.

**Prompt the AI.**

> Add `app/assistant/agent.py`. `create_agent(model=None)` builds `Agent(model, deps_type=DocumentAgentDeps, output_type=GroundedAnswer, instructions=<instructions.md>, tools=[the three tools], retries={"output": 1, "tools": 1})`. Add an output validator that calls `grounding.validator.validate` against `ctx.deps.retrieved` and turns a `GroundingError` into `ModelRetry` with its message. `answer_question(agent, deps, question, history)` runs the agent with `UsageLimits` (model requests, tool calls, total tokens, all from settings) and returns the answer plus the cited `SourcePassage`s. Tests use PydanticAI's `FunctionModel` with a scripted model and a faked retriever, and must test the grounding contract, not only the plumbing.

**What you should get.**

| File | Job |
| ---- | --- |
| `app/assistant/agent.py` | `create_agent`, the grounding output validator, `answer_question` with usage limits |
| `app/assistant/instructions.md` | The product contract sent to the model on every turn |
| `tests/assistant/test_agent.py` | The grounding contract and the caps, with a scripted fake model |

**Verify.**

```bash
cd backend
uv run pytest tests/assistant -q       # 43 passed
uv run ruff check app tests
```

The tests cover: a grounded answer passes and carries its passages; an honest "not enough evidence" answer passes without citations; an uncited answer is retried once and accepted when fixed (and the retry message names the problem); an invented chunk id is rejected after exactly one retry; citing without ever searching is rejected; the model is sent the instructions and exactly the three tools; a model that searches forever is stopped by the tool-call cap.

**Check your understanding.**

- *Why validate in code, not trust the prompt?* The prompt asks for honest citations; the validator proves them. It compares each cited chunk id with what the tools returned this turn, whatever the model says.
- *Why does the retry message list every broken rule?* So one retry can fix them all.
- *Why a cap on tool calls?* A model can loop on searches. The cap ends it with `UsageLimitExceeded`, which the chat layer turns into a "try a narrower question" reply.
- *Why `FunctionModel`, not a real model?* The tests must run with no network and still exercise the retry behaviour, which needs a model that returns scripted, deliberately bad answers.

**Common mistakes.**

- **Testing only that the agent runs.** A fake model that always answers well proves nothing about grounding. Script a bad answer and assert it is retried and then rejected.
- **Letting history supply evidence.** Earlier answers carry no chunk ids, so they give context only. The agent must search again to cite.

### Step 13 — Run the agent in the chat turn, and stream its sources (`app/chat/orchestrator.py`)

**Goal.** `run_turn` loads the thread's history, runs the agent, streams the validated answer a word at a time, then sends a `data-citations` part carrying the sources, and saves the exchange before `finish`.

**Why.** This is the only place the chat flow changes: the stubbed reply is replaced by the agent. Streaming the sources lets the UI show the exact passage behind each `[n]` marker, and saving them means a reloaded thread shows the same sources.

**Prompt the AI.**

> In `app/chat/orchestrator.py`, replace the stubbed reply with `answer_question`. Stream the answer text as today, then send a `data-citations` data part: one entry per citation with its `[n]` marker and the passage (ticker, form, fiscal year, filing date, accession number, section, exact excerpt). Save the same part in the assistant message's `parts`. Keep the title logic and the rule that the turn is saved before `finish`. A grounding failure or a cap hit streams a plain explanation, saved with a `data-turn-failed` marker so the question stays in the thread but out of later history. A service failure sends an `error` event and saves nothing. Send no citations part when there are no sources. Tests with a fake agent run.

**What you should get.**

| File | Job |
| ---- | --- |
| `app/chat/orchestrator.py` | `run_turn`: history, agent, stream, citations, save |
| `app/chat/streaming.py` | `ui_message_stream` takes `data_parts`, sent after `text-end` and before the save |
| `app/chat/messages.py` | `citation_parts` and `CITATIONS_PART_TYPE = "data-citations"`; `to_model_history` turns stored messages into the agent's context |
| `app/api/chat.py` | `get_agent` (shared) and `get_agent_deps` (fresh per request, so `retrieved` starts empty) passed into `run_turn` |
| `app/main.py` | The lifespan builds the search engine, embedding client and agent once, and disposes the engine on shutdown |
| `app/config.py` | `agent_max_tool_calls` (15), `agent_max_model_requests` (20), `agent_max_total_tokens` (500,000), `agent_history_messages` (10) |
| `app/assistant/instructions.md` | New section: earlier messages are context only and cannot be cited; markers restart at `[1]` each answer |
| `scripts/ask.py` | Chat with the agent in the terminal and see the sources behind each answer (real model and database, nothing saved) |

The stream for a cited answer is: `start`, `text-start`, `text-delta` (many), `text-end`, `data-citations`, then the save, then `finish` and `[DONE]`.

**Verify.**

```bash
cd backend
uv run pytest -m "not integration" -q  # 137 passed
uv run ruff check app tests
```

New tests: a cited answer streams `data-citations` between `text-end` and `finish`, with the marker and exact excerpt; the saved parts are the text plus the same citations part that was streamed; an answer with no sources sends and saves no citations part; a grounding failure sends no sources; `ui_message_stream` orders data parts before the save.

**Check your understanding.**

- *Why are the sources sent after the text?* The passages are known only once the agent has finished and the answer is validated, so there is nothing to send while the text streams.
- *Why does a grounding failure save an explanation, not nothing?* The user's question stays in the thread and nothing unsupported is shown. A service failure is different: it is not the question's fault, so nothing is saved and the user simply retries.
- *Why the `data-turn-failed` marker?* Without it, the explanation would be replayed to the model as if it were an earlier answer.
- *Why keep the excerpt in the saved part?* It is the text as it was when cited, so the thread stays correct even if a filing is re-ingested later.

**Common mistakes.**

- **Sharing one `DocumentAgentDeps` across requests.** The agent, engine and client are built once, but the deps (and their `retrieved` dict) are made per request. Otherwise one user's evidence could justify another user's citation.
- **Replaying failed exchanges as history.** `to_model_history` drops a failed question and its explanation as a pair, and starts and ends the history on a user and an assistant message.
- **Dropping the passages the agent returns.** The first version of this step discarded them, so the answer streamed with `[1]` markers and no way to see what `[1]` was.
- **Sending an empty citations part.** An answer that cites nothing should have no `data-citations` part at all.
- **Saving after `finish`.** The client would show a message that was never stored.
- **Frontend not yet updated.** The UI ignores unknown `data-` parts, so nothing breaks, but the sources do not show until the citations step is added to the chat UI.

### Step 14 — Save the sources, and check the stream format (`app/database/chats.py`)

**Goal.** Each cited answer is saved with its sources in two places: inside the message's `parts` (so a reloaded thread shows them) and as `message_citations` rows (so they can be queried). The stream's citation chunk is checked against the installed AI SDK.

**Why.** The UI needs the sources live and after a reload. The rows copy the excerpt and section at answer time, so an old answer keeps showing what it cited even if a filing is re-ingested and its chunks are replaced (`chunk_id` becomes null, the snapshot stays).

**Prompt the AI.**

> First check the data-part chunk shape against the installed `ai` package in `frontend/node_modules`. Then extend `ChatStore.save_turn` with an optional `citations` list. After the two messages are inserted, insert one `message_citations` row per source: `chunk_id`, `citation_index` (the `[n]` marker), `excerpt`, `section`, `page` as null. If that insert fails, delete the two messages (their citations cascade) and re-raise, so an error means nothing was stored. The orchestrator passes the streamed sources to `save_turn`. Tests: the rows built, the order of the requests with a fake Supabase client, and a save-then-reload round trip with the fake store.

**What you should get.**

| File | Job |
| ---- | --- |
| `app/database/chats.py` | `citation_rows` and the extended `save_turn` |
| `app/chat/orchestrator.py` | Passes `citations=` to `save_turn` |
| `tests/database/test_chats.py` | Rows, request order, cleanup on failure |
| `tests/conftest.py` | `FakeStore.save_turn` also keeps the messages, so a test can reload the thread |

**Verify.**

```bash
cd backend
uv run pytest -m "not integration" -q  # 142 passed
```

Stream format: in `frontend/node_modules/ai` (7.0.173) the data chunk is `{type: "data-<name>", id?, data, transient?}` with any `data-` prefix accepted. Our `{"type": "data-citations", "data": [...]}` matches. Check this again whenever the `ai` package is upgraded; chunk names have changed between major versions.

**Check your understanding.**

- *Why store sources in `parts` and in rows?* `parts` is what the UI reloads, with no joins. The rows are for questions such as "which answers cited this passage?".
- *Why copy the excerpt instead of joining to the chunk?* Re-ingesting replaces chunks. The foreign key is `ON DELETE SET NULL`, so the old answer keeps its text.
- *Why not one transaction?* The Supabase API is one request per call, so the citation insert cannot join the message insert. The cleanup delete restores "saved together or not at all".
- *Why save the thread update last?* A failed save then leaves the thread's order and title unchanged.

**Common mistakes.**

- **Trusting the chunk name from memory.** Read it from the installed package.
- **Leaving the exchange behind when the citation insert fails.** The user sees an error, asks again, and the thread now holds the question twice.
- **Using the user client for the cleanup.** It is correct: row-level security lets users delete only their own messages, which is all the cleanup needs.

### Step 15 — Wire it into the app (`app/main.py`, `app/api/chat.py`)

**Goal.** The search engine, the embedding client and the agent are created once at startup and shared by every request. Each request gets its own `DocumentAgentDeps` around them and passes it to `run_turn`.

**Why.** Engines and clients hold connection pools, so building them per request would pay that cost every time. The evidence dict is the opposite: it must start empty each turn, or one user's retrieved passages could justify another user's citation. This follows the pattern `service_client` already used.

**Prompt the AI.**

> In the `lifespan` in `app/main.py`, create the search engine (`create_search_engine()`), the embedding client and the agent once and keep them on `app.state`; dispose the engine on shutdown. In `app/api/chat.py` add two dependencies: `get_agent`, which returns the shared agent, and `get_agent_deps`, which builds a fresh `DocumentAgentDeps` per request from the shared engine and client. Pass both into `run_turn`. psycopg's async mode cannot run on Windows' default event loop, so make `python -m app.main` start uvicorn on the selector loop; leave Linux alone. Test that requests share the engine and client but not `retrieved`.

**What you should get.**

| File | Job |
| ---- | --- |
| `app/main.py` | Lifespan builds and disposes the shared pieces; `__main__` starts uvicorn on the selector loop |
| `app/api/chat.py` | `get_agent` (shared) and `get_agent_deps` (fresh per request), injected into the stream endpoint |
| `tests/api/test_wiring.py` | The agent is the startup one; engine and client are shared; `retrieved` is not |

**Verify.**

```bash
cd backend
uv run pytest -m "not integration" -q  # 144 passed
uv run python -m app.main               # then, in another terminal:
curl http://127.0.0.1:8000/health       # {"status":"ok"}
```

The server logs "Application startup complete" with the real `.env`, and shutting it down logs "Application shutdown complete" (the engine is disposed first).

**Check your understanding.**

- *Why is the agent shared but the deps are not?* The agent holds no per-user state. The deps hold `retrieved`, which is per turn.
- *Why does the Windows fix live in `__main__` only?* Railway runs on Linux, which has no such problem, so the production start command stays plain.
- *Why dispose the engine on shutdown?* It closes the pool's connections cleanly instead of leaving them for the database to time out.

**Common mistakes.**

- **Starting with plain `uvicorn app.main:app` on Windows.** It uses the Proactor loop, and the first retrieval query fails with "cannot use the ProactorEventLoop". Use `python -m app.main` (or `--reload`, which uses the selector loop).
- **Port 8000 already in use.** A second server fails to bind with "only one usage of each socket address", yet the old one still answers `/health`, so a health check can pass while your new code is not the one running. Check what is listening first.
- **Building the deps once at startup.** Every turn would then share one `retrieved` dict.

---

## Roadmap

Steps still to be written into this guide, in build order (from [docs/architecture.md](docs/architecture.md)):

| # | Step | Status |
| - | ---- | ------ |
| 0 | Download the sample SEC filings (10-K corpus) | **Written (Part 0, Step 0.5)** |
| 1a | Backend: install dependencies, `.env`, `config.py`, validators | **Written (Part 1, Steps 1-4)** |
| 1a | Backend: FastAPI entrypoint with `/health`, import check | **Written (Part 1, Step 5)** |
| 1a | Backend: install `app` as a package (hatchling build settings) | **Written (Part 1, Step 6)** |
| 1a | Backend: tests for the settings module and `/health` | Next |
| 1b | Frontend scaffold (Vite, React, TypeScript, Tailwind, shadcn/ui) | Planned |
| 2 | SQLAlchemy models + Alembic setup | Planned |
| 3 | First migration (pgvector, documents, chunks, chats, citations) | Planned |
| 4 | Supabase Auth in the frontend + token verification in FastAPI | Planned |
| 5 | Shared frontend API client | Planned |
| 6 | Chat endpoint with a stubbed reply | **Written (Part 3, Step 7)** |
| 7 | Chat UI | **Written (Part 3, Step 8)** |
| 8 | Ingestion: Markdown, chunking, embeddings | **Written (Part 4, Step 9)** |
| 9 | Semantic search (pgvector) | **Written (Part 4, Step 10)** |
| 10 | Keyword search + Reciprocal Rank Fusion | **Written (Part 4, Step 10)** |
| 11 | PydanticAI document agent: tools | **Written (Part 5, Step 11)** |
| 11 | PydanticAI document agent: agent, grounding retry, usage caps | **Written (Part 5, Step 12)** |
| 11 | Chat turn runs the agent and streams its sources | **Written (Part 5, Step 13)** |
| 11 | Agent wired into the app (lifespan, dependencies, Windows event loop) | **Written (Part 5, Step 15)** |
| 11 | Document agent: deps, outputs, model, instructions | Built (steps 1 to 3 of the agent work); not yet written up |
| 12 | Citation validation and grounding | Validator built; sources streamed and saved (**Part 5, Step 14**) |
| 13 | Final UI: citations, source passages, errors | Planned |
| — | Evaluation set, then deploy on Railway | Planned |

---

## Maintenance note (for whoever extends this guide)

- Add each new step **after** it has been built and verified, never before.
- Keep the same blocks: Goal, Why, Prompt the AI, What you should get, Verify, Check your understanding, Common mistakes.
- Put real mistakes and real learner questions in the last two blocks; they are the most valuable part.
- Keep reference code in sync with the actual files in the repo.
