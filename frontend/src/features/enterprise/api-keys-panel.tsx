"use client";

import { KeyRound, Info, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { DataTable, type Column } from "@/components/data/data-table";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/loading-skeletons";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";
import type { ApiKeyInfo } from "@/lib/api/types";
import { ROLES, type Role } from "@/lib/auth/roles";
import { formatDateTime } from "@/lib/format";

import { CopyOnceSecret } from "./onboarding";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "./queries";

/** Roles the backend accepts on `ApiKeyCreateRequest`, most privileged last. */
const ASSIGNABLE_ROLES: Role[] = [...ROLES];

function RoleBadge({ role }: { role: string }) {
  return (
    <Badge variant="outline" className="font-mono text-xs">
      {role}
    </Badge>
  );
}

/**
 * Create-key form.
 *
 * The role list is offered in full and the backend enforces the ceiling: it
 * refuses to mint a key whose role outranks the caller's, answering 403 with an
 * explanatory message. That message is surfaced verbatim rather than
 * pre-empting it with a client-side rule that could drift from the server's.
 */
function CreateKeyForm({ onCreated }: { onCreated: (secret: string) => void }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("member");
  const create = useCreateApiKey();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    create.mutate(
      { name: name.trim(), role },
      {
        onSuccess: (result) => {
          onCreated(result.key);
          setName("");
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_10rem_auto] sm:items-end">
        <div className="space-y-1.5">
          <Label htmlFor="key-name">Key name</Label>
          <Input
            id="key-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            placeholder="ci-pipeline"
            disabled={create.isPending}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="key-role">Role</Label>
          <Select value={role} onValueChange={(v) => setRole(v as Role)}>
            <SelectTrigger id="key-role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ASSIGNABLE_ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button type="submit" disabled={!name.trim() || create.isPending}>
          {create.isPending ? "Creating…" : "Create key"}
        </Button>
      </div>

      {create.isError ? (
        <Alert variant="destructive">
          <TriangleAlert className="size-4" aria-hidden="true" />
          <AlertTitle>
            {create.error instanceof ApiError && create.error.status === 403
              ? "Not permitted"
              : "Could not create the key"}
          </AlertTitle>
          <AlertDescription>
            {create.error instanceof Error ? create.error.message : "Request failed."}
          </AlertDescription>
        </Alert>
      ) : null}
    </form>
  );
}

/** Confirmation before revoking — revocation is immediate and irreversible. */
function RevokeDialog({
  target,
  onCancel,
  onConfirm,
  isPending,
}: {
  target: ApiKeyInfo | null;
  onCancel: () => void;
  onConfirm: (prefix: string) => void;
  isPending: boolean;
}) {
  return (
    <Dialog open={target !== null} onOpenChange={(open) => (!open ? onCancel() : undefined)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Revoke this API key?</DialogTitle>
          <DialogDescription>
            {target ? (
              <>
                <span className="font-medium">{target.name}</span> (
                <code className="text-xs">{target.prefix}</code>) stops working immediately.
                Requests using it will be rejected. This cannot be undone, and the backend offers no
                way to re-issue the same key.
              </>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => target && onConfirm(target.prefix)}
            disabled={isPending}
          >
            {isPending ? "Revoking…" : "Revoke key"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * API-key lifecycle for the caller's tenant.
 *
 * The backend supports exactly three operations — create, list, revoke — so
 * that is exactly what this offers. There is deliberately **no rotate action**:
 * no such endpoint exists, and presenting one would imply a capability the
 * platform does not have. Rotating means creating a new key and revoking the
 * old one, which the UI states rather than dressing up as a single button.
 *
 * A secret is only ever available in the create response. `GET /api-keys`
 * returns metadata with no `key` field, so the table can never show one.
 */
export function ApiKeysPanel({ canManage = true }: { canManage?: boolean }) {
  const keys = useApiKeys();
  const revoke = useRevokeApiKey();

  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyInfo | null>(null);

  const columns: Column<ApiKeyInfo>[] = [
    {
      header: "Name",
      cell: (k) => (
        <div className="min-w-32">
          <div className="font-medium">{k.name}</div>
          <code className="text-muted-foreground text-xs">{k.prefix}</code>
        </div>
      ),
    },
    { header: "Role", cell: (k) => <RoleBadge role={k.role} /> },
    {
      header: "Status",
      cell: (k) =>
        k.revoked ? (
          <Badge className="bg-muted text-muted-foreground border-transparent">Revoked</Badge>
        ) : (
          <Badge className="border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
            Active
          </Badge>
        ),
    },
    { header: "Created", cell: (k) => formatDateTime(k.created_at) },
    {
      header: "",
      cell: (k) =>
        k.revoked || !canManage ? null : (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setRevokeTarget(k)}
            aria-label={`Revoke ${k.name}`}
          >
            Revoke
          </Button>
        ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="size-4" aria-hidden="true" />
          API keys
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label="About key rotation"
                className="text-muted-foreground hover:text-foreground"
              >
                <Info className="size-3.5" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              The backend supports create, list, and revoke. There is no rotate endpoint — to
              rotate, create a replacement key and then revoke the old one.
            </TooltipContent>
          </Tooltip>
        </CardTitle>
        <CardDescription>
          Secrets are shown once at creation and are never returned again.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {newSecret ? (
          <CopyOnceSecret secret={newSecret} onDismiss={() => setNewSecret(null)} />
        ) : null}

        {canManage ? <CreateKeyForm onCreated={setNewSecret} /> : null}

        {revoke.isError ? (
          <Alert variant="destructive">
            <TriangleAlert className="size-4" aria-hidden="true" />
            <AlertTitle>Could not revoke the key</AlertTitle>
            <AlertDescription>
              {revoke.error instanceof Error ? revoke.error.message : "Request failed."}
            </AlertDescription>
          </Alert>
        ) : null}

        {keys.isPending ? (
          <TableSkeleton rows={3} columns={5} />
        ) : keys.isError ? (
          <ErrorState title="Couldn't load API keys" onRetry={() => void keys.refetch()} />
        ) : (keys.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon={KeyRound}
            title="No API keys yet"
            description="Create one above. Its secret is displayed once and cannot be recovered afterwards."
          />
        ) : (
          <DataTable
            rows={keys.data ?? []}
            columns={columns}
            getRowKey={(k) => k.id}
            empty="No API keys."
          />
        )}
      </CardContent>

      <RevokeDialog
        target={revokeTarget}
        isPending={revoke.isPending}
        onCancel={() => setRevokeTarget(null)}
        onConfirm={(prefix) => revoke.mutate(prefix, { onSuccess: () => setRevokeTarget(null) })}
      />
    </Card>
  );
}
