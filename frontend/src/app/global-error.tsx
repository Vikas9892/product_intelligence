"use client";

import { useEffect } from "react";

/**
 * Global error boundary (Next.js `global-error.tsx`). Catches errors thrown in
 * the root layout itself, which the per-route `error.tsx` cannot. It must
 * render its own `<html>`/`<body>` because it replaces the root layout. Kept
 * deliberately minimal and self-contained (no shell, no providers).
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "1rem",
            fontFamily: "system-ui, sans-serif",
            textAlign: "center",
            padding: "2rem",
          }}
        >
          <h1 style={{ fontSize: "1.25rem", fontWeight: 600 }}>Something went wrong</h1>
          <p style={{ color: "#71717a", maxWidth: "28rem" }}>
            A critical error occurred. Please reload the page.
          </p>
          <button
            onClick={reset}
            style={{
              borderRadius: "0.5rem",
              border: "1px solid #d4d4d8",
              padding: "0.5rem 1rem",
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
