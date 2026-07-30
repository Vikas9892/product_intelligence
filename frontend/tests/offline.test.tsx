import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OfflineIndicator } from "@/components/common/offline-indicator";

function setOnline(value: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
}

afterEach(() => setOnline(true));

describe("OfflineIndicator", () => {
  it("renders nothing while online", () => {
    setOnline(true);
    const { container } = render(<OfflineIndicator />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a banner while offline", () => {
    setOnline(false);
    render(<OfflineIndicator />);
    expect(screen.getByRole("status")).toHaveTextContent(/offline/i);
  });
});
