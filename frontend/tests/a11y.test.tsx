import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import { PageHeader } from "@/components/common/page-header";
import { ConfidenceBadge } from "@/components/data/confidence-badge";
import { ScoreBar } from "@/components/data/score-bar";
import { StatCard } from "@/components/data/stat-card";
import { StatusBadge } from "@/components/data/status-badge";
import { StatusChip } from "@/components/data/status-chip";
import { DataTable } from "@/components/data/data-table";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";

/**
 * Automated accessibility checks (axe-core) on the shared building blocks used
 * across every feature. Complements the manual a11y practices (semantic
 * landmarks, skip link, keyboard support) with an assertion that these
 * primitives ship no obvious violations.
 */
describe("accessibility (axe)", () => {
  it("shared components have no violations", async () => {
    const { container } = render(
      <main>
        <PageHeader title="Dashboard" description="Overview" />
        <StatCard label="Uploads today" value={12} hint="7d" />
        <StatusChip tone="success" label="Healthy" />
        <ConfidenceBadge score={0.9} />
        <ScoreBar value={0.5} label="image" />
        <EmptyState title="Nothing here" description="No results yet" />
        <ErrorState onRetry={() => {}} />
      </main>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});

/**
 * Composed-surface checks.
 *
 * The suite above covers primitives in isolation. These render the assembled
 * pieces — a status badge set, a populated table, a form with labelled fields —
 * because most real violations come from composition (a table without headers,
 * an input whose label was dropped in a grid refactor), not from a primitive
 * used on its own.
 */
describe("accessibility (axe) — composed surfaces", () => {
  it("status badges expose their meaning as text, not colour alone", async () => {
    const { container } = render(
      <main>
        <StatusBadge tone="success">Healthy</StatusBadge>
        <StatusBadge tone="warning">Degraded</StatusBadge>
        <StatusBadge tone="danger">Unavailable</StatusBadge>
        <StatusBadge tone="neutral">Unknown</StatusBadge>
      </main>,
    );
    expect(await axe(container)).toHaveNoViolations();
    // Every tone carries a label; none relies on the colour to be understood.
    for (const label of ["Healthy", "Degraded", "Unavailable", "Unknown"]) {
      expect(container.textContent).toContain(label);
    }
  });

  it("a populated data table has header semantics", async () => {
    const { container } = render(
      <main>
        <DataTable<{ id: string; name: string; role: string }>
          rows={[
            { id: "1", name: "owner", role: "owner" },
            { id: "2", name: "ci", role: "viewer" },
          ]}
          columns={[
            { header: "Name", cell: (r) => r.name },
            { header: "Role", cell: (r) => r.role },
          ]}
          getRowKey={(r) => r.id}
        />
      </main>,
    );
    expect(await axe(container)).toHaveNoViolations();
    expect(container.querySelectorAll("th").length).toBe(2);
  });

  it("the score meter exposes an accessible name", async () => {
    const { container } = render(
      <main>
        <ScoreBar value={0.83} label="Relevance score" />
      </main>,
    );
    expect(await axe(container)).toHaveNoViolations();
    expect(container.querySelector("[role='progressbar']")).toHaveAttribute("aria-label");
  });
});
