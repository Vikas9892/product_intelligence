"use client";

import { WifiOff } from "lucide-react";

import { useOnlineStatus } from "@/hooks/use-online-status";

/**
 * A thin banner shown only while the browser is offline. Requests are paused by
 * TanStack Query until connectivity returns, so this explains why data may be
 * stale. Rendered in the app shell below the top bar.
 */
export function OfflineIndicator() {
  const online = useOnlineStatus();
  if (online) return null;

  return (
    <div
      role="status"
      className="bg-destructive/10 text-destructive flex items-center justify-center gap-2 border-b px-4 py-1.5 text-sm"
    >
      <WifiOff className="size-4" aria-hidden />
      You&apos;re offline — data may be out of date.
    </div>
  );
}
