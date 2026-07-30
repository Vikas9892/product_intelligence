"use client";

import { env } from "@/config/env";
import { can as canDo, type UiCapability } from "@/lib/auth/roles";
import { useAuthStore } from "@/stores/auth-store";

export type AuthMode = "demo" | "enterprise";

/**
 * Primary auth hook and user context. Exposes the current session plus the
 * deployment `mode`. In demo mode (`enterpriseEnabled` off) the app is
 * unauthenticated by design — `isAuthenticated` is reported `true` so gated
 * content renders without a key. In enterprise mode it reflects the real
 * session. `can()` is a UI-only capability hint; the server `403` is the gate.
 */
export function useAuth() {
  const store = useAuthStore();
  const mode: AuthMode = env.enterpriseEnabled ? "enterprise" : "demo";

  const isLoading = mode === "enterprise" && store.status === "loading";
  const isAuthenticated = mode === "demo" ? true : store.status === "authenticated";

  return {
    mode,
    status: store.status,
    isLoading,
    isAuthenticated,
    role: store.role,
    keyPrefix: store.keyPrefix,
    organizationId: store.organizationId,
    tenantId: store.tenantId,
    signIn: store.signIn,
    setSession: store.setSession,
    signOut: store.signOut,
    can: (capability: UiCapability) => (mode === "demo" ? true : canDo(store.role, capability)),
  };
}
