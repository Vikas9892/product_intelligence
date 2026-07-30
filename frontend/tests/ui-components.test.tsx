import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfidenceBadge, levelFromScore } from "@/components/data/confidence-badge";
import { DataTable } from "@/components/data/data-table";
import { ScoreBar } from "@/components/data/score-bar";
import { StatCard } from "@/components/data/stat-card";
import { StatusChip } from "@/components/data/status-chip";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";

describe("shared UI components", () => {
  it("StatCard shows its label and value", () => {
    render(<StatCard label="Uploads" value={128} hint="today" />);
    expect(screen.getByText("Uploads")).toBeInTheDocument();
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getByText("today")).toBeInTheDocument();
  });

  it("levelFromScore buckets a 0..1 score", () => {
    expect(levelFromScore(0.9)).toBe("high");
    expect(levelFromScore(0.6)).toBe("medium");
    expect(levelFromScore(0.2)).toBe("low");
  });

  it("ConfidenceBadge renders level and score", () => {
    render(<ConfidenceBadge score={0.94} />);
    expect(screen.getByText(/High/)).toBeInTheDocument();
    expect(screen.getByText(/0\.94/)).toBeInTheDocument();
  });

  it("ScoreBar exposes an accessible progressbar", () => {
    render(<ScoreBar value={0.42} label="image" />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText("0.42")).toBeInTheDocument();
  });

  it("StatusChip renders its label", () => {
    render(<StatusChip tone="success" label="Healthy" />);
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });

  it("EmptyState renders as a status region", () => {
    render(<EmptyState title="Nothing here" description="No results yet" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  it("ErrorState calls onRetry when the button is clicked", async () => {
    const onRetry = vi.fn();
    render(<ErrorState onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("DataTable renders rows and an empty state", () => {
    const { rerender } = render(
      <DataTable
        columns={[
          { header: "Name", cell: (r: { name: string }) => r.name },
          { header: "Role", cell: (r: { role: string }) => r.role },
        ]}
        rows={[{ name: "ci", role: "member" }]}
        getRowKey={(r) => r.name}
      />,
    );
    expect(screen.getByText("ci")).toBeInTheDocument();
    expect(screen.getByText("member")).toBeInTheDocument();

    rerender(
      <DataTable
        columns={[{ header: "Name", cell: (r: { name: string }) => r.name }]}
        rows={[]}
        getRowKey={(r) => r.name}
        empty="Nothing to show"
      />,
    );
    expect(screen.getByText("Nothing to show")).toBeInTheDocument();
  });
});
