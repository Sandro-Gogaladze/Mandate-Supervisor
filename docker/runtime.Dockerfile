# syntax=docker/dockerfile:1.7
#
# The CopilotKit runtime — the one Node process in the stack. It translates
# CopilotKit's client protocol into the FastAPI backend's AG-UI endpoints and
# holds no business logic; every real decision happens in the Python graph
# (see dashboard/server/copilot-runtime.js).

FROM node:24-slim

# Telemetry off by default. The library phones home anonymously unless told
# not to; a supervision tool handling regulatory case material should not
# make that call on an operator's behalf, and the deployment says so rather
# than leaving it to whoever reads the startup log.
ENV NODE_ENV=production \
    SUPERVISOR_API_URL=http://api:8123 \
    COPILOT_RUNTIME_PORT=4000 \
    COPILOTKIT_TELEMETRY_DISABLED=true

WORKDIR /app/server

# dashboard/server/package.json, not dashboard/package.json. The server needs
# four packages; the dashboard's production tree additionally carries every
# frontend library @copilotkit/react-core depends on — mermaid, streamdown,
# lucide-react, date-fns — none of which this process ever imports. Measured:
# 811 MB of node_modules against 321 MB, for identical behaviour. Versions in
# the two manifests are pinned to match, so dev and container run the same code.
COPY dashboard/server/package.json dashboard/server/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --omit=dev

COPY dashboard/server/copilot-runtime.js ./

USER node

EXPOSE 4000

CMD ["node", "copilot-runtime.js"]
