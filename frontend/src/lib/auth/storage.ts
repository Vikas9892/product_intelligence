/**
 * Persistence for the API key credential.
 *
 * An API key is a long-lived bearer credential, so the default scope is
 * `sessionStorage` (cleared when the tab closes). A user may opt into
 * `localStorage` ("remember on this device") for persistence across sessions.
 * All access is guarded for SSR (no `window` on the server) and wrapped in
 * try/catch so private-mode storage failures never crash the app.
 */
export type PersistScope = "session" | "local";

const KEY = "pi.apiKey";
const SCOPE_KEY = "pi.apiKey.scope";

function store(scope: PersistScope): Storage | null {
  if (typeof window === "undefined") return null;
  return scope === "local" ? window.localStorage : window.sessionStorage;
}

/** Read the persisted key from whichever scope it was saved in. */
export function loadApiKey(): { key: string; scope: PersistScope } | null {
  if (typeof window === "undefined") return null;
  try {
    const scope: PersistScope =
      window.localStorage.getItem(SCOPE_KEY) === "local" ? "local" : "session";
    const key = store(scope)?.getItem(KEY) ?? null;
    return key ? { key, scope } : null;
  } catch {
    return null;
  }
}

/** Persist the key to the chosen scope, clearing the other scope. */
export function saveApiKey(key: string, scope: PersistScope = "session"): void {
  try {
    store(scope === "local" ? "session" : "local")?.removeItem(KEY);
    store(scope)?.setItem(KEY, key);
    window.localStorage.setItem(SCOPE_KEY, scope);
  } catch {
    /* storage unavailable (private mode) — key simply won't persist */
  }
}

/** Remove the key from both scopes. */
export function clearApiKey(): void {
  try {
    store("session")?.removeItem(KEY);
    store("local")?.removeItem(KEY);
    window.localStorage.removeItem(SCOPE_KEY);
  } catch {
    /* no-op */
  }
}
