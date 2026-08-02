#!/bin/sh
# Rewrite the backend origin baked into the Next.js build, then exec the server.
#
# WHY THIS EXISTS
#
# next.config.ts proxies the API through this server via `rewrites()`. Next
# evaluates `rewrites()` at BUILD time and serializes the result into the build
# output -- `server.js`, `.next/routes-manifest.json` and
# `.next/required-server-files.json` all end up containing the literal
# destination URL. The standalone server never re-reads next.config.ts, so
# setting BACKEND_ORIGIN in the environment at `docker run` time has no effect
# on its own. Verified against a real build before writing this.
#
# The alternatives were worse. Baking the value at build time would produce an
# image that only works in one environment, which defeats promoting a single
# tested artifact from Compose to ECS. Converting the proxy to a route handler
# or middleware would work, but the frontend is feature-frozen in this stage
# and that is an application change, not a packaging one.
#
# So the image is built against a sentinel origin and the real one is
# substituted here, at container start. That keeps BACKEND_ORIGIN a genuine
# runtime variable while leaving the application source untouched.
#
# The sentinel uses the reserved `.invalid` TLD (RFC 2606), which is guaranteed
# never to resolve. If this substitution ever silently fails, the proxy fails
# loudly with a DNS error instead of quietly reaching some real host.

set -eu

SENTINEL="http://backend-origin.invalid"
: "${BACKEND_ORIGIN:=http://api:8000}"

if [ "$BACKEND_ORIGIN" != "$SENTINEL" ]; then
    # Only these three files carry the serialized rewrite destinations.
    for f in \
        /app/server.js \
        /app/.next/routes-manifest.json \
        /app/.next/required-server-files.json
    do
        [ -f "$f" ] || continue
        # `|` as the delimiter because the values are URLs containing `/`.
        sed -i "s|${SENTINEL}|${BACKEND_ORIGIN}|g" "$f"
    done

    # Fail fast rather than serve a subtly broken proxy: if the sentinel is
    # still present, every API call would try to resolve a .invalid host.
    if grep -q "$SENTINEL" /app/server.js 2>/dev/null; then
        echo "entrypoint: FATAL: could not rewrite backend origin in server.js" >&2
        exit 1
    fi

    echo "entrypoint: backend origin set to ${BACKEND_ORIGIN}"
fi

# exec so the Node server becomes PID 1's direct child and receives SIGTERM
# itself, rather than having this shell absorb it.
exec "$@"
