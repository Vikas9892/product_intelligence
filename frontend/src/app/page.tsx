/**
 * Placeholder root page for the repository foundation (Stage 3, Milestone 1).
 *
 * Intentionally minimal and content-free: the application shell arrives in
 * Milestone 2 and the real dashboard in Stage 4. This exists only so the app
 * renders and the toolchain (build, lint, tests) has something to compile.
 */
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 p-8 text-center">
      <p className="text-muted-foreground text-sm font-medium tracking-wide uppercase">
        Product Intelligence
      </p>
      <h1 className="text-2xl font-semibold">Frontend foundation ready</h1>
      <p className="text-muted-foreground max-w-md text-sm">
        Repository setup complete. The application shell, navigation, and pages are built in the
        following milestones.
      </p>
    </main>
  );
}
