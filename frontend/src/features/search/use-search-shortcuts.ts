"use client";

import { useEffect } from "react";

/** Whether the event originated in a control where typing should win. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable === true
  );
}

export interface SearchShortcutHandlers {
  /** Focus the query box. Bound to "/" and Ctrl/Cmd+K. */
  onFocusQuery: () => void;
  /** Clear the current query, image, and results. Bound to Escape. */
  onClear: () => void;
  /** Cycle the search mode. Bound to Ctrl/Cmd+Shift+M. */
  onCycleMode: () => void;
}

/**
 * Keyboard shortcuts for the search workspace.
 *
 * Deliberately conservative: "/" is ignored while the user is typing so it
 * stays usable as a character, and every binding has a visible equivalent
 * control — the shortcuts are an accelerator, never the only way to do
 * something.
 */
export function useSearchShortcuts({
  onFocusQuery,
  onClear,
  onCycleMode,
}: SearchShortcutHandlers): void {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const mod = event.ctrlKey || event.metaKey;

      if (mod && event.shiftKey && event.key.toLowerCase() === "m") {
        event.preventDefault();
        onCycleMode();
        return;
      }

      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onFocusQuery();
        return;
      }

      if (event.key === "/" && !isTypingTarget(event.target)) {
        event.preventDefault();
        onFocusQuery();
        return;
      }

      if (event.key === "Escape" && !mod) {
        onClear();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onFocusQuery, onClear, onCycleMode]);
}
