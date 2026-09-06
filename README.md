# Mandate Supervisor

A regulator-side supervision tool for agentic payments. It checks what an AI
payment agent **actually did** against what it was **authorised to do** — using
the firm's real AP2 mandate chain (Intent, Cart, Payment) and its transaction
history — instead of a policy review filed once a year.

A submission is verified deterministically at the door, an orchestrator
dispatches specialist agents over it, their findings are scored by a pure
function, and anything escalated is drafted into a supervisory query that a
named human signs off before it goes anywhere. Every step lands on a
hash-chained, append-only ledger.

Built for NBG's submission to the C:\>DIR Global "Agentic Regulator" Hackathon.
Full framing: [`docs/concept-note.md`](docs/concept-note.md).

---

## Run it

You need [Docker](https://docs.docker.com/get-started/get-docker/). Nothing
else — no Python, no Node, no npm. The images are prebuilt.

```bash
curl -O https://raw.githubusercontent.com/Sandro-Gogaladze/Mandate-Supervisor/main/compose.yml
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
docker compose up -d
```

Then open **http://localhost:5173**. The case queue is already populated: the
synthetic corpus is baked into the image and seeded into the ledger on first
boot.

### Without an API key

It still runs. Every specialist has a deterministic floor that needs no model
at all — signature and delegation-chain verification, structuring and
counterparty-cluster detection, mandate-scope checks, scoring — and those all
work. Only the LLM judgement and narration layer is skipped, and it says so
rather than failing.

Get a key from [console.anthropic.com](https://console.anthropic.com) when you
want the full experience. It is yours and is billed to you; nothing here
ships a key.

### Everyday commands

With just `compose.yml`:

```bash
docker compose logs -f     # follow all three services
docker compose down        # stop, keep the ledger
docker compose down -v     # stop and erase all state
docker compose pull        # fetch the newest published images
```

From a clone, the same things are `make logs`, `make down`, `make clean`,
`make pull`, plus `make smoke` to check every path answers. `make save` writes
all three images to one tarball and `make load` installs them again — for
demoing somewhere with no network. `make help` lists everything.

## What's running

Three containers, one published port. nginx serves the console and proxies
both backends, so the whole application is same-origin.

```
browser :5173 ── nginx ─┬─ /            static console (React, Vite)
                        ├─ /api/        FastAPI + LangGraph + ledger  :8123
                        └─ /copilotkit  CopilotKit ⇄ AG-UI runtime    :4000
```

State lives in three Docker volumes: `state` (the ledger and sandbox
databases), `uploads` (ad hoc submissions), `drafts` (policy-sandbox drafts).
They survive `make down` and are erased by `make clean`.

## Configuration

Everything is optional except the key. See [`.env.example`](.env.example) for
the full list; the ones that matter:

| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Empty runs the deterministic checks only |
| `TAG` | `latest` | Pin to a release for a stable demo |
| `PORT` | `5173` | Host port for the console |
| `MANDATE_INSTITUTION_TOKENS` | unset | Unset = open intake. Set it before exposing this beyond localhost |

## Building from source

```bash
git clone https://github.com/Sandro-Gogaladze/Mandate-Supervisor.git
cd Mandate-Supervisor
make up-build
```

This builds all three images locally instead of pulling them. Slower, and it
needs nothing extra installed — the toolchains live inside the build stages.

## Developing

Docker isn't part of the edit loop. Development runs the three processes
directly, with hot reload:

```bash
./.venv/bin/python -m uvicorn api.main:app --port 8123 --reload
npm --prefix dashboard run copilot-runtime
npm --prefix dashboard run dev
```

Requires Python 3.14 (see `.python-version`) and Node 24. Tests:
`./.venv/bin/python -m pytest` — around 12 minutes, since parts of the suite
make live model calls.

## Releasing

Pushing a version tag builds all three images for amd64 and arm64 and
publishes them to GHCR:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

Commits without a tag publish nothing. `compose.yml` is served from `main`, so
fixes to it reach downloaders without a release.
