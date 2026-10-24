import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import FreshnessBadge from "../FreshnessBadge";

describe("FreshnessBadge", () => {
  it("renders the label for synthetic data", () => {
    render(<FreshnessBadge freshness="synthetic" />);
    expect(screen.getByText("synthetic")).toBeInTheDocument();
  });

  it("renders the label for delayed (stale) data", () => {
    render(<FreshnessBadge freshness="delayed" />);
    expect(screen.getByText("delayed")).toBeInTheDocument();
  });

  it("renders the label case-insensitively", () => {
    render(<FreshnessBadge freshness="SIMULATED" />);
    expect(screen.getByText("SIMULATED")).toBeInTheDocument();
  });

  it("renders unknown when freshness is missing", () => {
    render(<FreshnessBadge />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });

  it("shows the source next to the label", () => {
    render(<FreshnessBadge freshness="synthetic" source="regime-engine" />);
    expect(screen.getByText("synthetic")).toBeInTheDocument();
    expect(screen.getByText(/regime-engine/)).toBeInTheDocument();
  });
});
