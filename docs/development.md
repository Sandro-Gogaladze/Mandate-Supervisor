# Development

Running from source, the test suite, and releasing. For what the system *is*,
start at the [README](../README.md).

---

## Requirements

| | |
|---|---|
| Python | **3.12+**. `pyproject.toml` requires `>=3.12`; `.python-version` pins `3.14`. Those disagree — 3.12+ is the real floor |
| Node | 24 |
| Package manager | `uv` for Python, `npm` for the console |
| Docker | Only for the packaged application, not for the edit loop |

```bash
git clone https://github.com/Sandro-Gogaladze/Mandate-Supervisor.git
cd Mandate-Supervisor
uv sync
cp .env.example .env      # add ANTHROPIC_API_KEY, or leave it empty
```

An empty key is a supported mode, not a broken one: every deterministic check
runs and the judgement layer is skipped with a clear message.

---

## The edit loop

Docker is not part of it. Three processes, each with hot reload:

```bash
./.venv/bin/python -m uvicorn api.main:app --port 8123 --reload
```
```bash
npm --prefix dashboard run copilot-runtime
```
```bash
npm --prefix dashboard run dev
```

The console is then on Vite's dev server. In the packaged application nginx
serves it and proxies both backends on one port.

---

## Tests

```bash
./.venv/bin/python -m pytest
```

**490 tests collected across 50 files.** Expect roughly 12 minutes — parts of the suite
make live model calls, which is deliberate: the contained judgement calls are
part of the product, and mocking all of them would prove only that the mocks
agree with themselves.

For a fast loop, target a module:

```bash
./.venv/bin/python -m pytest tests/test_ledger.py -q
```

`tests/corpus.py` provides the dossier fixtures and `tests/fakes.py` the model
doubles. `collect_ignore` in `tests/conftest.py` is empty and stays as the place
to park the next migration's debt — nothing is parked today.

### Evaluation

Precision and recall against the corpus answer keys:

```bash
./.venv/bin/python -m eval [--live] [--output report.json]
```

`eval/` is the only consumer of `ground_truth.json`. Nothing in the pipeline
reads it.

### Independent verification

```bash
./.venv/bin/python scripts/verify_dossier.py
./.venv/bin/python -m ledger.verify
```

`verify_dossier.py` checks the corpus's signatures and planted defects, and is
**forbidden from importing anything under `agents/`**. Ground truth that the
implementation helped write would be a mirror, not an evaluation — so the
verifier keeps its own patterns even where that means duplicating logic.

`ledger.verify` walks the whole hash chain: exit 0 and "intact", or exit 1
listing every broken link.

---

## Layout

```
schemas/     Pydantic models — the typed vocabulary everything else agrees on
data/        Synthetic corpus, Ed25519 keystore, reference registries, loaders
ingestion/   Deterministic verify + normalise. No model, ever
registry/    Rulesets, failure catalogue, scoring + authorisation policy, loader
agents/      10 specialists + orchestrator, investigator, critic, synthesizer,
             drafting, grounding, and the tool permission map
pipeline/    LangGraph graphs, state, scoring, authorisation, graph map
ledger/      Append-only store, hash chain, events, projection, seed, verify
sandbox/     Draft → sweep → diff → promote
api/         FastAPI: main, dossiers, sandbox routers
dashboard/   React + Vite + Tailwind + shadcn/ui + React Flow + CopilotKit
eval/        Precision/recall runner
scripts/     Corpus signing and independent verification
tests/       50 files, 490 tests
docker/      Three Dockerfiles + nginx.conf
```

Each specialist follows the same three-file shape:

```
agents/<name>.py            the agent — floor, then one contained model call
agents/<name>_checks.py     deterministic rule checkers → list[Fact]
agents/<name>_reasoning.py  the single judged call, schema-constrained
```

`log` and `drift` substitute `_stats.py` for `_checks.py`, because their rules
are judged over computed statistics rather than checked.

Adding a specialist means: a rulebook in `registry/rulesets/`, the three files
above, an entry in `agents/catalog.py`, and an empty tool set in
`agents/tools.py` unless it genuinely needs callable tools.

---

## Configuration

Everything in `.env.example` is optional except the key.

| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Empty runs the deterministic checks only |
| `TAG` | `latest` | Pin to a release for a stable demo |
| `PORT` | `5173` | Host port for the console |
| `MANDATE_THINKING_EFFORT` | `low` | `low` / `medium` / `high`. `high` takes a review to ~10 minutes |
| `MANDATE_MODEL_CONCURRENCY` | `8` | Concurrent model calls across the graph |
| `MANDATE_INSTITUTION_TOKENS` | unset | `{"token":"institution_id"}`. Unset = open intake — fine locally, **not** fine on a public URL |
| `MANDATE_LEDGER_PATH` | `data/ledger.db` | Where the chain lives |

---

## The packaged application

```bash
make up          # pull published images and start
make up-build    # build from this checkout and start
make smoke       # verify every path answers
make logs        # follow all three services
make down        # stop, keep the ledger
make clean       # stop and erase all state
make help        # list everything
```

Three containers behind nginx on one port:

```
browser :5173 ── nginx ─┬─ /            static console
                        ├─ /api/        FastAPI + LangGraph + ledger  :8123
                        └─ /copilotkit  CopilotKit ⇄ AG-UI runtime    :4000
```

State lives in three Docker volumes — `state` (ledger and sandbox databases),
`uploads` (ad hoc submissions), `drafts` (policy-sandbox drafts). They survive
`make down` and are erased by `make clean`.

For a venue with no network, `make save` writes all three images to one tarball
and `make load` installs them on the far side.

---

## CI and releasing

| Workflow | Trigger | What it does |
|---|---|---|
| `build.yml` | Push to `main` touching `docker/**` | Builds all three images (amd64) and runs the whole stack. The packaging test — a broken Dockerfile or nginx route surfaces here, not on a downloader's machine. Nothing is published |
| `release.yml` | A `v*` tag, or manual dispatch | Builds for amd64 + arm64 and publishes to GHCR |

```bash
git tag v0.1.0 && git push origin v0.1.0
```

Commits without a tag publish nothing. `compose.yml` is served from `main`, so
fixes to it reach downloaders without a release.

> One manual step, once, after the first successful release: GHCR packages are
> private by default, and a private package means every downloader needs a
> `docker login`. Profile → Packages → each package → change visibility.

---

## What is gitignored, and why

The repository tracks five markdown documents on purpose — this one, the
[README](../README.md), [supervision-model.md](supervision-model.md),
[architecture.md](architecture.md) and [guardrails.md](guardrails.md) — plus
[concept-note.md](concept-note.md), kept as **history, not design**: it describes
microservices and four specialists, and both were superseded.

The build produced a great deal more: a running plan, per-phase specs,
superseded architecture drafts, explainers whose numbers drifted, and pitch
material. Those are still on disk and ignored by `.gitignore`. They were
excluded rather than deleted because they are useful history — but a reader
cannot tell which of fifty documents is the one that is still true, and several
of them are demonstrably not. Anything a reader needs is in the six.

Also ignored: `CLAUDE.md`, `.claude/` and `.agents/` (Claude Code project
instructions and vendored agent skills — local development aids),
`registry/drafts/` and `data/sandbox.db` (a draft is a candidate, a sweep is an
experiment — neither is policy), `data/ledger.db` (runtime record, regenerated
by seeding), and `data/uploads/` (ad hoc submissions, not the curated corpus).
