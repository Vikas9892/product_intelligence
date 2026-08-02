# syntax=docker/dockerfile:1.7
#
# Production image for the Next.js 15 frontend.
#
# Serves the standalone build (`output: "standalone"` is already set in
# next.config.ts) behind a minimal Node runtime. The browser only ever talks to
# this server's own origin; API calls are proxied from here to the backend, so
# no backend URL is ever exposed to the browser and CORS never applies.
#
# Build from the repository root so the context is `frontend/`:
#   docker build -t product-intelligence-frontend:latest ./frontend

# Debian slim rather than Alpine: `sharp` (pulled in by next for image
# optimization, and overridden to 0.35.3 for the libvips CVEs) links against
# libvips, and the glibc prebuilds are the well-trodden path. The size
# difference is not worth debugging musl binaries for.
ARG NODE_IMAGE=node:20-bookworm-slim

# ---------------------------------------------------------------------------
# Stage 1: deps -- install node_modules from the lockfile
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS deps

WORKDIR /app

# `npm ci` (not `npm install`): installs exactly what package-lock.json pins
# and fails if it has drifted from package.json, so the image can never be
# built from a dependency set nobody reviewed. This mirrors `uv sync --frozen`
# on the backend and `npm ci` in CI.
#
# Its own layer, keyed only on the two manifest files, so editing source does
# not trigger a reinstall.
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# ---------------------------------------------------------------------------
# Stage 2: builder -- produce the standalone production build
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# The backend origin is baked into the build output by Next (see
# docker-entrypoint.sh for the full explanation). Building against a sentinel
# on the reserved `.invalid` TLD means the real origin is substituted at
# container start, and a failed substitution surfaces as an unresolvable host
# rather than as traffic to somewhere unintended.
ENV BACKEND_ORIGIN="http://backend-origin.invalid" \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 3: runtime -- standalone server only, no toolchain, no dev deps
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS runtime

# tini, for the same reason as the backend image: PID 1 ignores signals it has
# no handler for, so without an init `compose down` waits 10s and then
# SIGKILLs. The apt lists are dropped in the same layer.
RUN apt-get update \
    && apt-get install --no-install-recommends -y tini \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged user at a fixed uid/gid, matching the backend image's
# convention. `node:20-bookworm-slim` ships a `node` user at uid 1000 already;
# a distinct uid keeps ownership explicit and stable.
RUN groupadd --gid 10001 web \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin web

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    # Bind all interfaces: the default 'localhost' would only accept
    # connections originating inside this container, so Compose could never
    # reach it.
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app

# The standalone bundle carries its own minimal, traced node_modules -- only
# what the server actually imports at runtime. Nothing from the dev
# dependencies (vitest, playwright, eslint, typescript, tailwind) is present,
# and neither is the source tree.
COPY --from=builder --chown=web:web /app/.next/standalone ./
# Static assets are deliberately NOT included in the standalone bundle by Next;
# they have to be copied alongside it or every page renders unstyled.
COPY --from=builder --chown=web:web /app/.next/static ./.next/static
COPY --from=builder --chown=web:web /app/public ./public

COPY --chown=web:web docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# `--chown` on COPY sets ownership of the copied *contents*, but /app itself
# was created by WORKDIR and is still root-owned. The entrypoint rewrites
# server.js and two manifests with `sed -i`, which works by writing a temp file
# into the containing directory -- so without write permission on the
# directories themselves it fails with "couldn't open temporary file".
RUN chown web:web /app /app/.next

USER web

EXPOSE 3000

# Probes this server's own root route, which is statically prerendered and
# needs no backend. Deliberately NOT /health: that path is proxied to the API,
# so probing it would make the frontend report unhealthy whenever the backend
# blips -- coupling the two services' health for no benefit. Backend
# reachability is the backend's health check to report.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "require('http').get({host:'127.0.0.1',port:3000,path:'/'},r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"]

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]

CMD ["node", "server.js"]
