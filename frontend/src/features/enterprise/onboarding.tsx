"use client";

import { Check, Copy, KeyRound, ShieldAlert, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth/use-auth";
import type { OrganizationBootstrapResponse } from "@/lib/api/types";

import { useBootstrapOrganization } from "./queries";

/**
 * One-time display of a freshly minted secret.
 *
 * The backend returns the raw key exactly once — `GET /api-keys` afterwards
 * carries metadata only, with no `key` field — so this is the single moment it
 * can be captured. It is held in component state and never written to
 * `localStorage`, `sessionStorage`, or the console; dismissing the panel drops
 * it permanently, which the copy explains up front.
 */
export function CopyOnceSecret({ secret, onDismiss }: { secret: string; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be unavailable (permissions, insecure context). The
      // secret stays selectable on screen, so the user can copy it manually.
      setCopied(false);
    }
  }

  return (
    <Alert>
      <ShieldAlert className="size-4" aria-hidden="true" />
      <AlertTitle>Copy this key now — it cannot be shown again</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>
          The backend returns a key&apos;s secret only at creation. Listing keys afterwards returns
          metadata only, so there is no way to recover this value.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <code
            className="bg-muted min-w-0 flex-1 overflow-x-auto rounded px-2 py-1.5 font-mono text-xs"
            data-testid="one-time-secret"
          >
            {secret}
          </code>
          <Button type="button" variant="outline" size="sm" onClick={() => void copy()}>
            {copied ? (
              <>
                <Check className="size-4" aria-hidden="true" /> Copied
              </>
            ) : (
              <>
                <Copy className="size-4" aria-hidden="true" /> Copy
              </>
            )}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
            Done
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}

/**
 * Enterprise onboarding: bootstrap a new organization, or sign in with a key
 * that already exists.
 *
 * `POST /organizations` is the only unauthenticated enterprise endpoint, which
 * is why bootstrapping is possible from an anonymous session at all.
 */
export function EnterpriseOnboarding() {
  const auth = useAuth();
  const bootstrap = useBootstrapOrganization();

  const [orgName, setOrgName] = useState("");
  const [pastedKey, setPastedKey] = useState("");
  const [remember, setRemember] = useState(false);
  const [created, setCreated] = useState<OrganizationBootstrapResponse | null>(null);

  function handleBootstrap(event: React.FormEvent) {
    event.preventDefault();
    if (!orgName.trim()) return;
    bootstrap.mutate(orgName.trim(), {
      onSuccess: (result) => {
        setCreated(result);
        // Sign in immediately with the owner key so the console is usable.
        auth.signIn({
          key: result.api_key.key,
          scope: remember ? "local" : "session",
          role: "owner",
          organizationId: result.organization.id,
          tenantId: result.tenant.id,
        });
      },
    });
  }

  function handlePastedKey(event: React.FormEvent) {
    event.preventDefault();
    if (!pastedKey.trim()) return;
    // The role is unknown until the backend answers; the capability probe and
    // the keys list fill it in. Nothing is assumed here.
    auth.signIn({ key: pastedKey.trim(), scope: remember ? "local" : "session" });
    setPastedKey("");
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Create an organization</CardTitle>
          <CardDescription>
            Creates the organization, its default tenant, and an owner API key.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={handleBootstrap} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="org-name">Organization name</Label>
              <Input
                id="org-name"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                maxLength={200}
                disabled={bootstrap.isPending}
              />
            </div>
            <Button type="submit" disabled={!orgName.trim() || bootstrap.isPending}>
              {bootstrap.isPending ? "Creating…" : "Create organization"}
            </Button>
          </form>

          {bootstrap.isError ? (
            <Alert variant="destructive">
              <TriangleAlert className="size-4" aria-hidden="true" />
              <AlertTitle>Could not create the organization</AlertTitle>
              <AlertDescription>
                {bootstrap.error instanceof Error ? bootstrap.error.message : "Request failed."}
              </AlertDescription>
            </Alert>
          ) : null}

          {created ? (
            <div className="space-y-3">
              <CopyOnceSecret secret={created.api_key.key} onDismiss={() => setCreated(null)} />
              <dl className="text-sm">
                <div className="flex justify-between gap-2 border-b py-1.5">
                  <dt className="text-muted-foreground">Organization</dt>
                  <dd className="font-medium">{created.organization.name}</dd>
                </div>
                <div className="flex justify-between gap-2 border-b py-1.5">
                  <dt className="text-muted-foreground">Tenant</dt>
                  <dd className="font-medium">{created.tenant.name}</dd>
                </div>
                <div className="flex justify-between gap-2 py-1.5">
                  <dt className="text-muted-foreground">Key prefix</dt>
                  <dd className="font-mono text-xs">{created.api_key.api_key.prefix}</dd>
                </div>
              </dl>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Use an existing key</CardTitle>
          <CardDescription>
            The key is sent as the <code className="text-xs">X-API-Key</code> header on every
            request.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handlePastedKey} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="api-key">API key</Label>
              <Input
                id="api-key"
                type="password"
                autoComplete="off"
                value={pastedKey}
                onChange={(e) => setPastedKey(e.target.value)}
                placeholder="pik_…"
              />
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="size-4"
              />
              Remember on this device
            </label>
            <p className="text-muted-foreground text-xs">
              Unchecked (the default) keeps the key in{" "}
              <code className="text-xs">sessionStorage</code>, so it is dropped when the tab closes.
              Checking it moves the key to <code className="text-xs">localStorage</code>, where it
              persists until you sign out.
            </p>

            <Button type="submit" disabled={!pastedKey.trim()}>
              <KeyRound className="size-4" aria-hidden="true" />
              Use this key
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
