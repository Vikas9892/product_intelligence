"use client";

import { ScrollText } from "lucide-react";
import { useMemo, useState } from "react";

import { ForbiddenState } from "@/components/auth/permission";
import { DataTable, type Column } from "@/components/data/data-table";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/loading-skeletons";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import type { AuditEventInfo } from "@/lib/api/types";
import { formatDateTime, formatRelativeTime } from "@/lib/format";

import { useAuditEvents } from "./queries";

const ALL_ACTIONS = "__all__";

/** Renders the event's `metadata` map, which the backend fills per action. */
function MetadataCell({ metadata }: { metadata: Record<string, unknown> | undefined }) {
  const entries = Object.entries(metadata ?? {});
  if (entries.length === 0) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([key, value]) => (
        <Badge key={key} variant="outline" className="font-mono text-[0.7rem]">
          {key}={String(value)}
        </Badge>
      ))}
    </div>
  );
}

/**
 * The tenant's audit log.
 *
 * `GET /audit` returns the most recent events newest-first, capped by a `limit`
 * query parameter. It offers **no offset or cursor**, so this provides a limit
 * selector rather than pagination — page controls would imply a capability the
 * endpoint does not have.
 *
 * Filtering is client-side over the fetched page for the same reason: the
 * endpoint accepts no actor or action filter, so narrowing here is presented as
 * filtering what was loaded, not as a server query.
 */
export function AuditPanel() {
  const [limit, setLimit] = useState("100");
  const [actionFilter, setActionFilter] = useState(ALL_ACTIONS);
  const [actorQuery, setActorQuery] = useState("");

  const audit = useAuditEvents(Number(limit));
  const forbidden = audit.error instanceof ApiError && audit.error.status === 403;
  const events = useMemo(() => audit.data ?? [], [audit.data]);

  const actions = useMemo(() => Array.from(new Set(events.map((e) => e.action))).sort(), [events]);

  const filtered = useMemo(
    () =>
      events.filter((event) => {
        if (actionFilter !== ALL_ACTIONS && event.action !== actionFilter) return false;
        if (
          actorQuery.trim() &&
          !event.actor.toLowerCase().includes(actorQuery.trim().toLowerCase())
        )
          return false;
        return true;
      }),
    [events, actionFilter, actorQuery],
  );

  const columns: Column<AuditEventInfo>[] = [
    {
      header: "When",
      cell: (e) => (
        <div className="min-w-36">
          <div>{formatRelativeTime(e.created_at)}</div>
          <div className="text-muted-foreground text-xs">{formatDateTime(e.created_at)}</div>
        </div>
      ),
    },
    {
      header: "Actor",
      cell: (e) => <code className="text-xs">{e.actor}</code>,
    },
    {
      header: "Action",
      cell: (e) => (
        <Badge variant="outline" className="font-mono text-xs">
          {e.action}
        </Badge>
      ),
    },
    {
      header: "Resource",
      cell: (e) =>
        e.resource ? (
          <code className="text-xs">{e.resource}</code>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    { header: "Metadata", cell: (e) => <MetadataCell metadata={e.metadata} /> },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ScrollText className="size-4" aria-hidden="true" />
          Audit log
        </CardTitle>
        <CardDescription>This tenant&apos;s recorded actions, newest first.</CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {forbidden ? (
          <ForbiddenState capability="viewAudit" title="This key can't view the audit log" />
        ) : (
          <>
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="audit-actor">Actor</Label>
                <Input
                  id="audit-actor"
                  value={actorQuery}
                  onChange={(e) => setActorQuery(e.target.value)}
                  placeholder="pik_…"
                  className="w-40"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="audit-action">Action</Label>
                <Select value={actionFilter} onValueChange={setActionFilter}>
                  <SelectTrigger id="audit-action" className="w-52">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_ACTIONS}>All actions</SelectItem>
                    {actions.map((action) => (
                      <SelectItem key={action} value={action}>
                        {action}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="audit-limit">Fetch</Label>
                <Select value={limit} onValueChange={setLimit}>
                  <SelectTrigger id="audit-limit" className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["25", "50", "100", "250"].map((n) => (
                      <SelectItem key={n} value={n}>
                        Last {n}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {audit.isPending ? (
              <TableSkeleton rows={4} columns={5} />
            ) : audit.isError ? (
              <ErrorState
                title="Couldn't load the audit log"
                onRetry={() => void audit.refetch()}
              />
            ) : events.length === 0 ? (
              <EmptyState
                icon={ScrollText}
                title="No audit events yet"
                description="Events are recorded when keys are created or revoked. Nothing has been logged for this tenant."
              />
            ) : filtered.length === 0 ? (
              <EmptyState
                icon={ScrollText}
                title="No events match these filters"
                description="Clear the actor or action filter to see the rest of the fetched events."
              />
            ) : (
              <>
                <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
                  Showing {filtered.length} of {events.length} fetched event
                  {events.length === 1 ? "" : "s"}
                </p>
                <DataTable
                  rows={filtered}
                  columns={columns}
                  getRowKey={(e) => e.id}
                  empty="No audit events."
                />
                <p className="text-muted-foreground text-xs">
                  The endpoint returns the most recent events up to the fetch limit and offers no
                  cursor or offset, so there are no page controls. Filters narrow what was fetched
                  rather than issuing a new server-side query.
                </p>
              </>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
