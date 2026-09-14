# Chat Helpdesk — RAG-based AI Helpdesk

A helpdesk chat system grounded strictly in an internal knowledge base via
Retrieval-Augmented Generation (RAG). Public chat frontend (Next.js) + admin/agent
backend (FastAPI) + PostgreSQL/pgvector for storage and similarity search + Ollama
(default) or OpenRouter for embeddings/generation.

## Stack

- Frontend: Next.js (App Router) + Tailwind CSS
- Backend: Python + FastAPI (async, SQLAlchemy + psycopg/asyncpg)
- Database: PostgreSQL + `pgvector`
- AI engine: Ollama (default) or OpenRouter — switchable via admin Settings, no code change
- File storage: local disk (`/uploads`), no cloud storage
- Containerization: Podman Compose (primary), Docker Compose (compatible)

## Quick Start (Podman — recommended)

1. Copy the environment template and adjust values:

   ```sh
   cp .env.example .env
   ```

2. Build and start the stack:

   ```sh
   podman compose -f deploy/podman-compose.yml --env-file .env up -d --build
   ```

3. Wait for the `ollama-init` one-shot container to finish pulling
   `nomic-embed-text` and `llama3` (first boot only — this can take several
   minutes depending on your connection):

   ```sh
   podman logs -f helpdesk_ollama-init_1
   ```

4. Open the app:
   - Public chat: http://localhost:3000
   - Admin panel: http://localhost:3000/admin/login

   Log in with the seeded admin credentials from `.env`
   (`INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD`).

## Quick Start (Docker Compose — alternative)

The same Compose file works with Docker:

```sh
docker compose -f deploy/podman-compose.yml --env-file .env up -d --build
```

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
the page was loaded from and get proxied server-side to the backend container
— CORS is never a factor for normal use.

To remove the port proxy rules later:

```powershell
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=3000
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=8001
```

## Switching AI Engines

By default the system uses **Ollama** for both embeddings and generation. To use
**OpenRouter** for generation instead (embeddings always stay on Ollama's
`nomic-embed-text` to keep vector dimensions consistent):

1. Log in to the admin panel as an admin user.
2. Go to **Settings**.
3. Set **Active AI Engine** to `openrouter`, provide an API key and model
   string (default suggestion: `meta-llama/llama-3-70b-instruct`), and save.

No code changes or redeploys are required — the change takes effect on the next
chat request.

## Off-Topic Chatter vs. Unanswered Questions

Every question is scored by similarity against the knowledge base. Two thresholds
(both editable in Settings) split the outcome three ways:

- **Above Confidence Threshold** (default 0.75) — answered from the matched FAQ(s).
- **Between the two thresholds** — a genuine question the AI can't confidently
  answer; the configurable fallback message is shown and it's logged as an
  `UnansweredQuestion` (category auto-assigned to **Other**) for agent review.
- **Below Off-Topic Threshold** (default 0.35) — treated as small talk/greetings
  unrelated to any product or technical topic ("hi", "thanks", "how are you?");
  the off-topic redirect message is shown and **nothing is logged for review**.

The off-topic threshold is intentionally conservative by default: with a small or
new knowledge base, a vaguely worded real question (e.g. "can I get a refund")
can score in the same range as pure chatter. Raising the threshold gives a
cleaner review queue but risks silently redirecting real questions instead of
logging them; only raise it once the knowledge base is large enough that real
questions reliably score higher than greetings. When in doubt, keep it low —
a false positive here just means an occasional greeting shows up in the
Unanswered Questions queue, which is easy for an agent to dismiss.

## Re-indexing

If you change the embedding model (`Ollama Embedding Model` in Settings), all
existing FAQ entries must be re-embedded so their vectors stay consistent with
new queries. Use the **Re-index All FAQs** button on the Settings page, or call:

```
POST /api/admin/reindex
```

## Excel Import

FAQ entries can be bulk-imported via `.xlsx` with a fixed column structure:

```
Category | Question | Answer | Image URL | Reference URL
```

Download the exact template from the FAQ list page ("Download Template") or
`GET /api/faqs/template`. Categories support nesting via `Parent > Child` in the
Category column; missing categories are auto-created. Row-level errors (missing
required fields, etc.) are reported without failing the whole import.

## Local Development (without containers)

### Backend

```sh
cd backend
python -m venv .venv
. .venv/Scripts/activate  # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements-dev.txt
# Point DATABASE_URL at a local Postgres with pgvector installed, then:
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

### Frontend

```sh
cd frontend
npm install
npm run dev
```

The frontend proxies `/api/*` and `/uploads/*` to `BACKEND_INTERNAL_URL`
(defaults to `http://localhost:8000` for local dev).

## Running Tests

```sh
cd backend
pytest
```

## Project Layout

```
backend/    FastAPI app, SQLAlchemy models, Alembic migrations, AI engine abstraction, RAG pipeline
frontend/   Next.js public chat UI + admin/agent panel
deploy/     Compose file and Postgres init scripts
```

## Data Model Summary

- **Category** — supports nested categories via `parent_id`.
- **FAQEntry** — question/answer/category/images/reference URLs + embedding vector.
- **UnansweredQuestion** — logged when no confident match is found; can be
  promoted into a new FAQEntry from the admin dashboard.
- **ChatLog** — every question asked (answered or not) with matched FAQ ids,
  confidence score, and which AI engine served it.
- **User** — admin/agent role-based backend accounts.
- **Setting** — key/value store for AI engine config, fallback message,
  confidence threshold, and top-K retrieval count.

## Security Notes

- Passwords hashed with Argon2; sessions are JWT bearer tokens.
- Role checks (`admin` vs `agent`) are enforced server-side on every protected
  route, not just hidden in the UI.
- Uploaded files are validated by extension/size and saved under randomly
  generated filenames — the original filename is never used for the path.
- The chat pipeline calls the LLM with a system prompt that strictly restricts
  it to the retrieved knowledge-base context, and falls back to the
  configured fallback message whenever similarity is below threshold or the
  model signals it cannot answer from context alone.

## The whole stack is up from a single command

- podman-compose -f deploy/podman-compose.yml --env-file .env up -d --build
- Chat: http://localhost:3000
- Admin: http://localhost:3000/admin/login (admin / changeme123)
- Backend: http://localhost:8001

## To start not rebuild
podman-compose -f deploy/podman-compose.yml --env-file .env up -d

## Confirmed — still only bound to 127.0.0.1, matching exactly what I predicted. The netsh/firewall commands haven't been run yet (that requires an elevated PowerShell, which I can't run for you). Let's check if you're on an elevated shell now so I can try running them for you this time.

Press Win, type PowerShell, right-click Windows PowerShell, choose Run as administrator
Paste and run:
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=3000 connectaddress=127.0.0.1 connectport=3000
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8001 connectaddress=127.0.0.1 connectport=8001
New-NetFirewallRule -DisplayName "Helpdesk Frontend" -Direction Inbound -Action Allow -LocalPort 3000 -Protocol TCP
New-NetFirewallRule -DisplayName "Helpdesk Backend" -Direction Inbound -Action Allow -LocalPort 8001 -Protocol TCP
