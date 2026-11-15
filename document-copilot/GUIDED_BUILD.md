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
| 6 | Chat endpoint with a stubbed reply | Planned |
| 7 | Chat UI | Planned |
| 8 | Ingestion: Markdown, chunking, embeddings | Planned |
| 9 | Semantic search (pgvector) | Planned |
| 10 | Keyword search + Reciprocal Rank Fusion | Planned |
| 11 | PydanticAI document agent | Planned |
| 12 | Citation validation and grounding | Planned |
| 13 | Final UI: citations, source passages, errors | Planned |
| — | Evaluation set, then deploy on Railway | Planned |

---

## Maintenance note (for whoever extends this guide)

- Add each new step **after** it has been built and verified, never before.
- Keep the same blocks: Goal, Why, Prompt the AI, What you should get, Verify, Check your understanding, Common mistakes.
- Put real mistakes and real learner questions in the last two blocks; they are the most valuable part.
- Keep reference code in sync with the actual files in the repo.
