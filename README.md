# Chat Helpdesk — RAG-based AI Helpdesk

A helpdesk chat system that answers questions **only** from an internal
knowledge base, using Retrieval-Augmented Generation (RAG). If nothing in the
knowledge base is relevant enough, it says so and logs the question for a
human agent instead of guessing.

## What's inside

| Layer | Tech |
|---|---|
| Public chat UI | Next.js (App Router) + Tailwind CSS |
| Admin/agent panel | Same Next.js app, under `/admin/*` |
| Backend API | Python + FastAPI (async) |
| Database | SQLite — a single file, no separate DB server |
| Semantic search | `sqlite-vec` (vector similarity, cosine distance) |
| Keyword search | SQLite FTS5 (full-text, bm25-ranked) |
| AI (chat + embeddings) | OpenRouter (one API key, model configurable per use) |
| File storage | Local disk (`backend/uploads/`) |
| Containers | Podman Compose — the required way to run the app (see below) |

There is no local model runtime (no Ollama, no GPU needed) and no separate
database server to install — SQLite lives inside the backend container. You
do need Podman (or Docker) installed to build and run the two containers.

## How it's organized

```
backend/
  app/
    ai/          OpenRouter client (chat completions + embeddings)
    core/        settings (env), JWT/password security, role-based deps
    crud/        DB read/write functions, one module per entity
    db/          SQLAlchemy engine/session setup, sqlite-vec helper (vec_store.py)
    models/      SQLAlchemy ORM models (the tables)
    rag/         the RAG pipeline itself (retrieval + generation + reindexing)
    routers/     FastAPI endpoints, one module per resource
    schemas/     Pydantic request/response shapes
    services/    higher-level flows (Excel import/export)
    seed.py      creates the initial admin user + default settings
    reindex_stale.py   re-embeds any entry missing a vector, run on boot
  alembic/       DB schema migrations
  entrypoint.sh  container startup: migrate -> seed -> reindex -> serve
frontend/
  app/           Next.js pages — public chat at `/`, admin panel at `/admin/*`
  app/api/[...path]/route.ts   proxies /api/* to the backend (see below)
deploy/
  podman-compose.yml   runs backend + frontend as containers — the supported way to run the app
```

## The RAG flow (how a chat question gets answered)

This is the core of the app — [backend/app/rag/pipeline.py](backend/app/rag/pipeline.py):

1. **Filler check** — obviously empty/junk input is redirected immediately
   without spending an API call.
2. **Embed the question** — sent to OpenRouter's embeddings endpoint to get a
   vector.
3. **Search two sources in parallel**, both via `sqlite-vec` KNN queries:
   - `faq_entries_vec` — every FAQ that has an embedding.
   - `vault_entries_vec` — every Vault entry that has `memory_enabled = true`.
4. **Merge and rank** the two result sets by similarity (cosine), take the
   top-K overall (K is configurable in Settings) — a strong Vault match can
   outrank a weak FAQ match, or vice versa.
5. **Threshold check** against the best match's similarity score:
   - **Above the confidence threshold** → build a context block from the
     matched entries and ask OpenRouter to answer strictly from that context.
   - **Below the confidence threshold but above the off-topic threshold** →
     a real question the AI isn't confident about; return the fallback
     message and log it as an `UnansweredQuestion` for an agent to review.
   - **Below the off-topic threshold** → treated as small talk/greetings;
     return the off-topic redirect message, nothing logged.
6. **Guard against hallucination** — the system prompt instructs the model to
   respond with a fixed refusal sentinel if the context doesn't actually
   answer the question; that sentinel is caught and turned into the fallback
   message rather than shown to the user.
7. **Log everything** — every question (answered, fallback, or off-topic) is
   written to `ChatLog` with which FAQ/Vault ids matched, the confidence
   score, and which engine served it.

See [Off-Topic Chatter vs. Unanswered Questions](#off-topic-chatter-vs-unanswered-questions)
below for how the two thresholds are meant to be tuned.

### FAQ vs. Vault — two knowledge sources

- **FAQ** (`FAQEntry`) is the original, primary knowledge base: question +
  answer pairs, managed directly in the admin panel or bulk-imported from
  Excel. Always semantically searchable once it has an embedding.
- **Vault** (`VaultEntry`) is a second, more general knowledge store — free-form
  title + content entries, optionally tagged and categorized, with a
  `memory_enabled` flag that opts an entry into RAG (embedding it, so it can
  be retrieved during chat). Vault has its own admin search endpoint that
  combines FTS5 keyword search and `sqlite-vec` semantic search into one
  ranked list, independent of the chat pipeline.
- **Harvester** (`HarvestJob` / `HarvestSource` models) is scaffolding for a
  planned feature — bulk-ingesting external documents/URLs into the Vault —
  but no ingestion service or endpoint exists yet; only the DB tables are in
  place.

### Keeping embeddings in sync

Vectors live in separate `sqlite-vec` virtual tables (`faq_entries_vec`,
`vault_entries_vec`), keyed by the owning row's id — not as a column on the
FAQ/Vault tables themselves, since `sqlite-vec` doesn't support nullable
vector columns. Each FAQ/Vault row has a `has_embedding` boolean flag so the
app can tell whether a vector currently exists.

- Creating/editing an FAQ (or a memory-enabled Vault entry) re-embeds it
  immediately.
- `python -m app.reindex_stale` (run automatically by `entrypoint.sh` on every
  boot) finds any row with `has_embedding = false` and retries — covers the
  case where an embedding call failed (e.g. bad/missing API key at the time).
- `POST /api/admin/reindex` re-embeds **everything**, for when you change the
  embedding model and need every vector regenerated at the new dimension.

## How to Run

Requires [Podman](https://podman.io/) (or Docker) with Compose support
installed. This is the supported way to run the app — the backend and
frontend each build into a container, and the backend's SQLite database and
uploaded files persist in named volumes across restarts.

```sh
cp .env.example .env      # fill in OPENROUTER_API_KEY, JWT_SECRET, admin creds
podman compose -f deploy/podman-compose.yml --env-file .env up -d --build
```

Docker Compose works identically with the same file:

```sh
docker compose -f deploy/podman-compose.yml --env-file .env up -d --build
```

Then open:
- Public chat: http://localhost:3000
- Admin panel: http://localhost:3000/admin/login (`admin` / `changeme123` by
  default — see `.env.example` / `INITIAL_ADMIN_*` to change them)
- Backend API directly: http://localhost:8001

**Before chat/embeddings will work**, set an OpenRouter API key — either put
`OPENROUTER_API_KEY=...` in `.env` before the first build, or log in as admin
and set it under **Settings** in the admin panel afterward (no rebuild
needed either way).

Common commands:

```sh
# Rebuild after a code change
podman-compose -f deploy/podman-compose.yml --env-file .env up -d --build

# Start without rebuilding
podman-compose -f deploy/podman-compose.yml --env-file .env up -d

# Stop and remove the containers (data volumes are kept)
podman-compose -f deploy/podman-compose.yml --env-file .env down

# Tail backend logs
podman logs -f deploy_backend_1
```

### Running backend/frontend directly (no containers, for quick debugging)

Not the supported path, but useful for stepping through code without a
rebuild cycle. SQLite is just a file and OpenRouter is a remote API, so
nothing else needs installing:

**Backend:**

```sh
cd backend
python -m venv .venv
. .venv/Scripts/activate        # Windows Git Bash; use .venv\Scripts\activate.bat for cmd.exe
pip install -r requirements-dev.txt
alembic upgrade head            # creates ./helpdesk.db with all tables + sqlite-vec + FTS5
python -m app.seed               # creates the initial admin user + default settings
uvicorn app.main:app --reload
```

**Frontend** (separate terminal):

```sh
cd frontend
npm install
npm run dev
```

The frontend proxies `/api/*` and `/uploads/*` to `BACKEND_INTERNAL_URL`
(defaults to `http://localhost:8000`, matching the backend's default port
when run this way).

## LAN Access (reaching it from other devices, not just localhost)

The Compose file already publishes ports as `0.0.0.0:PORT`, which is normally
enough for other devices on the network to reach the app via the host's IP.
**However, Podman Desktop on Windows runs inside a WSL2 VM, and its port
forwarder (gvproxy) only binds `127.0.0.1` on the Windows host — not the LAN-
facing network adapter** — regardless of what `podman port` reports. The
symptom: `http://localhost:3000` works fine on the host, but
`http://<host-lan-ip>:3000` refuses to connect from another device. (This is a
Podman-on-Windows/WSL2 limitation, not something specific to this app; Docker
Desktop on Windows and native Linux Podman don't have it.)

To fix it, forward the LAN interface to loopback with a Windows port proxy.
Run these in an **Administrator PowerShell** window (adjust the ports if you
changed them from the Compose defaults — `3000` for frontend, `8001` for
backend):

```powershell
# Forward LAN traffic to the loopback-bound container ports
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=3000 connectaddress=127.0.0.1 connectport=3000
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8001 connectaddress=127.0.0.1 connectport=8001

# Allow inbound traffic on those ports through Windows Firewall
New-NetFirewallRule -DisplayName "Helpdesk Frontend" -Direction Inbound -Action Allow -LocalPort 3000 -Protocol TCP
New-NetFirewallRule -DisplayName "Helpdesk Backend" -Direction Inbound -Action Allow -LocalPort 8001 -Protocol TCP
```

Find your machine's LAN IP with `ipconfig` (look for the `IPv4 Address` under
your active Wi-Fi/Ethernet adapter), then browse to
`http://<that-ip>:3000` from another device on the same network. No app code
changes are needed for this: the frontend's browser-facing code only ever
calls relative `/api/*` paths, which stay same-origin against whatever host
the page was loaded from and get proxied server-side to the backend — CORS is
never a factor for normal use.

To remove the port proxy rules later:

```powershell
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=3000
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=8001
```

## AI Engine (OpenRouter)

The system uses **OpenRouter** for both generation and embeddings, via a
single API key. Configure it from the admin panel:

1. Log in as an admin user.
2. Go to **Settings**.
3. Provide an **OpenRouter API Key**, a generation model (default suggestion:
   `meta-llama/llama-3-70b-instruct`), and an embedding model (default:
   `openai/text-embedding-3-small`), then save.

No code changes or redeploys are required — the change takes effect on the
next chat request. Changing the embedding model requires re-indexing (see
above), since existing vectors were produced by the previous model at a
possibly different dimension.

## Off-Topic Chatter vs. Unanswered Questions

Every question is scored by similarity against the knowledge base. Two
thresholds (both editable in Settings) split the outcome three ways:

- **Above Confidence Threshold** (default 0.75) — answered from the matched
  FAQ/Vault entries.
- **Between the two thresholds** — a genuine question the AI can't
  confidently answer; the configurable fallback message is shown and it's
  logged as an `UnansweredQuestion` (category auto-assigned to **Other**) for
  agent review.
- **Below Off-Topic Threshold** (default 0.35) — treated as small
  talk/greetings unrelated to any product or technical topic ("hi", "thanks",
  "how are you?"); the off-topic redirect message is shown and **nothing is
  logged for review**.

The off-topic threshold is intentionally conservative by default: with a
small or new knowledge base, a vaguely worded real question (e.g. "can I get
a refund") can score in the same range as pure chatter. Raising the threshold
gives a cleaner review queue but risks silently redirecting real questions
instead of logging them; only raise it once the knowledge base is large
enough that real questions reliably score higher than greetings. When in
doubt, keep it low — a false positive here just means an occasional greeting
shows up in the Unanswered Questions queue, which is easy for an agent to
dismiss.

## Excel Import / Export

FAQ entries can be bulk-imported or exported via `.xlsx` with a fixed column
structure:

```
Category | Question | Answer | Image URL | Reference URL
```

- **Import**: `POST /api/faqs/import`, or "Import Excel" on the FAQ list page.
  Categories support nesting via `Parent > Child`; missing categories are
  auto-created. Row-level errors (missing required fields, embedding
  failures, etc.) are reported without failing the whole import.
- **Export**: `GET /api/faqs/export` (respects the same `category_id`/`search`
  filters as the FAQ list), or "Export Excel" on the FAQ list page. Uses the
  same column layout as the import template, so an exported file can be
  edited and re-imported directly.
- **Template**: `GET /api/faqs/template`, or "Download Template" on the FAQ
  list page.

## Data Model Summary

- **Category** — supports nested categories via `parent_id`.
- **FAQEntry** — question/answer/category/images/reference URLs; `has_embedding`
  flags whether a vector exists in `faq_entries_vec`.
- **VaultEntry** — free-form knowledge entries (harvested or manual);
  keyword-searchable via `vault_entries_fts` (FTS5), semantically searchable
  via `vault_entries_vec` once `memory_enabled` is true.
- **HarvestJob** / **HarvestSource** — scaffolding for a future bulk-ingestion
  feature; tables exist, no ingestion logic yet.
- **UnansweredQuestion** — logged when no confident match is found; can be
  promoted into a new FAQEntry from the admin dashboard.
- **ChatLog** — every question asked (answered or not) with matched FAQ/Vault
  ids, confidence score, and which AI engine served it.
- **User** — admin/agent role-based backend accounts.
- **Setting** — key/value store for AI engine config, fallback/off-topic
  messages, thresholds, and top-K retrieval count.

## Security Notes

- Passwords hashed with Argon2; sessions are JWT bearer tokens.
- Role checks (`admin` vs `agent`) are enforced server-side on every protected
  route (`app/core/deps.py`), not just hidden in the UI.
- Uploaded files are validated by extension/size and saved under randomly
  generated filenames — the original filename is never used for the path.
- The chat pipeline calls the LLM with a system prompt that strictly restricts
  it to the retrieved knowledge-base context, and falls back to the
  configured fallback message whenever similarity is below threshold or the
  model signals it cannot answer from context alone.

## Running Tests

```sh
cd backend
pytest
```
