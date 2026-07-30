import { create } from "zustand";

import { setApiKey as setApiTokenHeader } from "@/lib/api";
import { clearApiKey, loadApiKey, saveApiKey, type PersistScope } from "@/lib/auth/storage";
import type { Role } from "@/lib/auth/roles";

export type AuthStatus = "loading" | "anonymous" | "authenticated";

export interface SessionInfo {
  role?: Role | null;
  organizationId?: string | null;
  tenantId?: string | null;
}

interface SignInInput extends SessionInfo {
  key: string;
  scope?: PersistScope;
}

interface AuthState {
  status: AuthStatus;
  apiKey: string | null;
  keyPrefix: string | null;
  role: Role | null;
  organizationId: string | null;
  tenantId: string | null;

  /** Read any persisted key on the client and prime the request header. */
  hydrate: () => void;
  /** Establish a session from an API key (persists + primes the header). */
  signIn: (input: SignInInput) => void;
  /** Attach identity/role details discovered after validating the key. */
  setSession: (session: SessionInfo) => void;
  /** Clear the session everywhere (state, storage, request header). */
  signOut: () => void;
}

function prefixOf(key: string): string {
  return key.slice(0, 12);
}

/**
 * Global authentication store.
 *
 * Holds the API key and the derived identity, and keeps three things in sync:
 * this React state, the persisted credential (`lib/auth/storage`), and the API
 * client's request header (`lib/api` `setApiKey`). In single-tenant demo mode
 * nothing here is required — the store simply stays anonymous and no header is
 * sent. There are no login pages; a session is established programmatically via
 * `signIn` (wired to the onboarding flow in a later stage).
 */
export const useAuthStore = create<AuthState>((set) => ({
  status: "loading",
  apiKey: null,
  keyPrefix: null,
  role: null,
  organizationId: null,
  tenantId: null,

  hydrate: () => {
    const loaded = loadApiKey();
    if (loaded) {
      setApiTokenHeader(loaded.key);
      set({ status: "authenticated", apiKey: loaded.key, keyPrefix: prefixOf(loaded.key) });
    } else {
      set({ status: "anonymous" });
    }
  },

  signIn: ({ key, scope = "session", role = null, organizationId = null, tenantId = null }) => {
    saveApiKey(key, scope);
    setApiTokenHeader(key);
    set({
      status: "authenticated",
      apiKey: key,
      keyPrefix: prefixOf(key),
      role,
      organizationId,
      tenantId,
    });
  },

  setSession: ({ role, organizationId, tenantId }) => {
    set((state) => ({
      role: role ?? state.role,
      organizationId: organizationId ?? state.organizationId,
      tenantId: tenantId ?? state.tenantId,
    }));
  },

  signOut: () => {
    clearApiKey();
    setApiTokenHeader(null);
    set({
      status: "anonymous",
      apiKey: null,
      keyPrefix: null,
      role: null,
      organizationId: null,
      tenantId: null,
    });
  },
}));
