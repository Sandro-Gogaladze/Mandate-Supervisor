# syntax=docker/dockerfile:1.7
#
# The React console, built to static files and served by nginx — which also
# reverse-proxies both backends. That is what makes the whole application
# same-origin on one port: no CORS, and no host names compiled into the
# bundle, so this image runs unchanged on a laptop or a server.

# ---------------------------------------------------------------- build
FROM node:24-slim AS build

WORKDIR /app

COPY dashboard/package.json dashboard/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY dashboard/ ./

# Relative URLs. nginx below maps them onto the two service containers;
# the alternative — baking http://127.0.0.1:8123 in — pins the image to one
# machine and one port.
ENV VITE_SUPERVISOR_API_URL=/api \
    VITE_COPILOT_RUNTIME_URL=/copilotkit

RUN npm run build

# ---------------------------------------------------------------- serve
FROM nginx:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
