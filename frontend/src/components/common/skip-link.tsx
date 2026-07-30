/**
 * "Skip to content" link — the first focusable element on the page. Visually
 * hidden until focused (keyboard/screen-reader users), then jumps focus past
 * the sidebar/topbar to the main content region (`#main-content`). An
 * accessibility baseline for a persistent app shell.
 */
export function SkipLink() {
  return (
    <a
      href="#main-content"
      className="bg-background ring-ring sr-only z-50 rounded-md px-3 py-2 text-sm font-medium focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:ring-2"
    >
      Skip to content
    </a>
  );
}
