/**
 * In-memory holder for the current API key.
 *
 * This is the decoupling seam between the API client (which must attach the key
 * to every request) and the auth layer (Milestone 4), which owns *where* the
 * key comes from and *how* it is persisted. The client only reads `getApiKey()`
 * in its request interceptor; the auth store calls `setApiKey()` to keep this in
 * sync. In single-tenant demo mode the key stays `null` and no header is sent.
 *
 * Intentionally module-local (not a store): it is read on every request and
 * should never trigger React re-renders.
 */
let currentApiKey: string | null = null;

export function getApiKey(): string | null {
  return currentApiKey;
}

export function setApiKey(key: string | null): void {
  currentApiKey = key;
}
