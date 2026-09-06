# syntax=docker/dockerfile:1.7
#
# The Python service: FastAPI, the LangGraph pipeline, the specialists and
# the append-only ledger. Two stages so the shipped image carries the
# dependency tree but none of the machinery that resolved it.

# ---------------------------------------------------------------- builder
FROM python:3.14-slim AS builder

# 3.14 matches .python-version and the venv every test has been run against.
# Not 3.12: pyproject's floor is a floor, not a statement about what is tested.

# COMPILE_BYTECODE: pay .pyc generation once here instead of on first request.
# LINK_MODE=copy: uv's hardlink optimisation can't cross the cache mount, and
# warns on every build without this.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir "uv>=0.9,<1.0"

WORKDIR /src

# Lockfile before source: editing an agent must not re-resolve the world.
# --frozen installs exactly what uv.lock pins — the set the suite passes on,
# not whatever resolves on build day.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------- runtime
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MANDATE_LEDGER_PATH=/state/ledger.db \
    MANDATE_SANDBOX_PATH=/state/sandbox.db

# Just the venv — uv, pip and every resolver cache stay in the builder.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .

# Everything the process writes, created up front and owned by the app user.
# Docker seeds a named volume from the image path it covers, ownership
# included — so these chowns are what let a non-root process write to the
# mounted volumes at all.
RUN useradd --create-home --uid 10001 supervisor \
 && mkdir -p /state /app/data/uploads /app/registry/drafts \
 && python -m compileall -q /app \
 && chown -R supervisor:supervisor /state /app

USER supervisor

EXPOSE 8123

# start-period covers import of pandas, langgraph and the corpus seed.
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8123/health').read()"

# No --reload: a file watcher in production restarts mid-run.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8123"]
