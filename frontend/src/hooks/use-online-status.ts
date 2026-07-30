"use client";

import { useEffect, useState } from "react";

/**
 * Tracks browser connectivity via the `online`/`offline` events. Starts `true`
 * to avoid an SSR/hydration mismatch, then syncs to `navigator.onLine` on mount.
 * (TanStack Query independently pauses fetching when offline via its own
 * `onlineManager`; this hook drives the visible indicator.)
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    setOnline(navigator.onLine);
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  return online;
}
