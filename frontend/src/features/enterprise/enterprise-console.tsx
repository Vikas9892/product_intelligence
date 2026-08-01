"use client";

import { Building2, CircleCheck, CircleSlash, HelpCircle, LogOut, ShieldCheck } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth/use-auth";
import { cn } from "@/lib/utils";

import { ApiKeysPanel } from "./api-keys-panel";
import { CAPABILITY_COPY, type EnterpriseCapability } from "./capability";
import { EnterpriseOnboarding } from "./onboarding";
import { useEnterpriseCapability } from "./queries";

const STATE_STYLES: Record<EnterpriseCapability, { icon: typeof CircleCheck; badge: string }> = {
  disabled: { icon: CircleSlash, badge: "bg-muted text-muted-foreground border-transparent" },
  unauthenticated: {
    icon: ShieldCheck,
    badge: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-400",
  },
  authenticated: {
    icon: CircleCheck,
    badge: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  },
  unknown: { icon: HelpCircle, badge: "bg-muted text-muted-foreground border-transparent" },
};

const STATE_LABEL: Record<EnterpriseCapability, string> = {
  disabled: "Disabled",
  unauthenticated: "Enabled · not signed in",
  authenticated: "Enabled · signed in",
  unknown: "Unknown",
};

/** The capability banner — always states which of the four states applies. */
function CapabilityBanner({ capability }: { capability: EnterpriseCapability }) {
  const copy = CAPABILITY_COPY[capability];
  const style = STATE_STYLES[capability];
  const Icon = style.icon;

  return (
    <Alert>
      <Icon className="size-4" aria-hidden="true" />
      <AlertTitle className="flex flex-wrap items-center gap-2">
        {copy.title}
        <Badge className={cn(style.badge)}>{STATE_LABEL[capability]}</Badge>
      </AlertTitle>
      <AlertDescription>{copy.description}</AlertDescription>
    </Alert>
  );
}

/**
 * Tenant context for the current session.
 *
 * Only fields the backend actually gave us are shown. The organization id and
 * role are known when a session was established by bootstrapping; a pasted key
 * yields neither until an authenticated call reveals them, and that gap is
 * stated rather than filled with a guess.
 */
function TenantContext() {
  const auth = useAuth();

  const rows: { label: string; value: string | null; hint?: string }[] = [
    { label: "Key prefix", value: auth.keyPrefix },
    { label: "Role", value: auth.role },
    { label: "Organization", value: auth.organizationId },
    { label: "Tenant", value: auth.tenantId },
  ];

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Session context</CardTitle>
          <CardDescription>Identity attached to the key in use.</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={auth.signOut}>
          <LogOut className="size-4" aria-hidden="true" />
          Sign out
        </Button>
      </CardHeader>
      <CardContent>
        <dl className="text-sm">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex items-baseline justify-between gap-3 border-b py-2 last:border-b-0"
            >
              <dt className="text-muted-foreground">{row.label}</dt>
              <dd className={cn("font-medium", !row.value && "text-muted-foreground font-normal")}>
                {row.value ?? "Not reported for this session"}
              </dd>
            </div>
          ))}
        </dl>
        <p className="text-muted-foreground mt-3 text-xs">
          The backend has no &ldquo;who am I&rdquo; endpoint, so identity is only known when this
          session created it. A pasted key shows its prefix; its role and tenant appear once an
          authenticated call returns them.
        </p>
      </CardContent>
    </Card>
  );
}

/**
 * The enterprise entry point.
 *
 * Which surface renders is driven by the live capability probe, not by a
 * build-time flag — the backend only mounts the enterprise router when it is
 * configured to, and the probe reads that directly. When the layer is off, this
 * page explains the demo posture and the rest of the app stays fully usable.
 */
export function EnterpriseConsole() {
  const probe = useEnterpriseCapability();
  const capability = probe.data?.capability ?? "unknown";

  return (
    <>
      <PageHeader
        title="Enterprise"
        description="Organization, tenant, and access administration."
      />

      <div className="space-y-6">
        {probe.isPending ? (
          <CardSkeleton />
        ) : (
          <>
            <CapabilityBanner capability={capability} />

            {capability === "disabled" ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Building2 className="size-4" aria-hidden="true" />
                    Running in single-tenant demo mode
                  </CardTitle>
                  <CardDescription>Nothing is gated, and no API key is required.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p>
                    Search, upload, duplicates, recommendations, pricing, and analytics all work
                    without authentication. The enterprise surface — organizations, API keys, audit,
                    and usage — is unavailable because the backend did not mount those routes.
                  </p>
                  <p className="text-muted-foreground">
                    To enable it, run the backend with{" "}
                    <code className="text-xs">ENTERPRISE__ENABLED=true</code> and reload. This page
                    detects the change automatically; no frontend rebuild is needed.
                  </p>
                </CardContent>
              </Card>
            ) : capability === "unknown" ? (
              <ErrorState title="Couldn't reach the backend" onRetry={() => void probe.refetch()} />
            ) : capability === "unauthenticated" ? (
              // The probe — not a build-time flag — is what says the key is
              // missing or invalid, so it is what selects this branch.
              <EnterpriseOnboarding />
            ) : (
              <>
                <TenantContext />
                <ApiKeysPanel />
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}
