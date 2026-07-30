"use client";

import { KeyRound } from "lucide-react";
import type { ReactNode } from "react";

import { useAuth } from "@/lib/auth/use-auth";
import type { UiCapability } from "@/lib/auth/roles";

/**
 * Route/section protection primitives.
 *
 * These gate *rendering only* — the backend `401`/`403` is the real
 * enforcement boundary. In demo mode `RequireAuth` is a pass-through (the app
 * is intentionally unauthenticated); in enterprise mode it shows a fallback
 * until a session exists. No login form lives here — establishing a session is
 * the onboarding flow's job (a later stage).
 */

function AuthRequiredNotice() {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-10 text-center">
      <div className="bg-muted text-muted-foreground flex size-12 items-center justify-center rounded-full">
        <KeyRound className="size-6" />
      </div>
      <p className="text-sm font-medium">Authentication required</p>
      <p className="text-muted-foreground max-w-sm text-sm">
        This deployment runs in enterprise mode. Provide an API key to continue.
      </p>
    </div>
  );
}

/** Gates content behind an authenticated session (pass-through in demo mode). */
export function RequireAuth({ children, fallback }: { children: ReactNode; fallback?: ReactNode }) {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) return null;
  if (!isAuthenticated) return fallback ?? <AuthRequiredNotice />;
  return <>{children}</>;
}

/** Renders children only if the current role satisfies a UI capability (hint). */
export function RequirePermission({
  capability,
  children,
  fallback = null,
}: {
  capability: UiCapability;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { can } = useAuth();
  return can(capability) ? <>{children}</> : <>{fallback}</>;
}

/** Renders children only when the deployment is in enterprise mode. */
export function RequireEnterprise({
  children,
  fallback = null,
}: {
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { mode } = useAuth();
  return mode === "enterprise" ? <>{children}</> : <>{fallback}</>;
}
