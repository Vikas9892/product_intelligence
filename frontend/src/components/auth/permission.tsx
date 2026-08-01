"use client";

import { Lock } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth/use-auth";
import type { Role, UiCapability } from "@/lib/auth/roles";

/**
 * Reusable permission-aware primitives.
 *
 * These exist so role checks live in one place instead of being scattered
 * through pages. All of them are **UX affordances**: they reduce dead ends by
 * hiding or disabling actions a key cannot perform. None of them protects
 * anything — the request is still made when attempted, and the backend's
 * 401/403 remains the only real gate.
 */

/**
 * Renders `children` only when the session's role grants `capability`.
 *
 * `fallback` (default: nothing) covers the denied case. In demo mode every
 * capability resolves true, because there is no enterprise layer to gate.
 */
export function Can({
  capability,
  children,
  fallback = null,
}: {
  capability: UiCapability;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const auth = useAuth();
  return auth.can(capability) ? <>{children}</> : <>{fallback}</>;
}

/**
 * Wraps an action so it is visibly present but disabled when not permitted,
 * with a tooltip explaining why.
 *
 * Preferred over hiding when the action's *existence* is useful information —
 * a viewer should learn that key management exists and needs a higher role,
 * rather than being silently shown a smaller app.
 */
export function PermissionGate({
  capability,
  children,
  reason,
}: {
  capability: UiCapability;
  children: ReactNode;
  reason?: string;
}) {
  const auth = useAuth();
  const permitted = auth.can(capability);

  if (permitted) return <>{children}</>;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className="inline-flex cursor-not-allowed opacity-50"
          aria-disabled="true"
          data-permission-denied={capability}
        >
          <span className="pointer-events-none">{children}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        {reason ?? `Your role (${auth.role ?? "unknown"}) does not grant this action.`}
      </TooltipContent>
    </Tooltip>
  );
}

/** Human copy for the roles that do grant a capability. */
function grantedBy(capability: UiCapability): Role[] {
  return capability === "manageOrganization" ? ["owner"] : ["admin", "owner"];
}

/**
 * A full-section forbidden state.
 *
 * Used where an entire panel is unavailable to the current role. Says which
 * roles do grant it, so the message is actionable rather than a dead end, and
 * is explicit that the server is what enforced it.
 */
export function ForbiddenState({
  capability,
  title = "You don't have access to this",
}: {
  capability: UiCapability;
  title?: string;
}) {
  const auth = useAuth();
  const roles = grantedBy(capability);

  return (
    <Alert>
      <Lock className="size-4" aria-hidden="true" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="space-y-1">
        <p>
          This key&apos;s role{auth.role ? ` (${auth.role})` : ""} does not grant the{" "}
          <code className="text-xs">{capability}</code> capability. It is available to:{" "}
          {roles.join(", ")}.
        </p>
        <p className="text-muted-foreground">
          The backend enforced this — the request was made and answered with 403. Hiding it here is
          only to save you the round trip.
        </p>
      </AlertDescription>
    </Alert>
  );
}
