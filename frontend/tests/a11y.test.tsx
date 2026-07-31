import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import { PageHeader } from "@/components/common/page-header";
import { ConfidenceBadge } from "@/components/data/confidence-badge";
import { ScoreBar } from "@/components/data/score-bar";
import { StatCard } from "@/components/data/stat-card";
import { StatusChip } from "@/components/data/status-chip";
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
