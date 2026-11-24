import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Avatar, AppShell, AreaChart, Badge, Card, CountUp, Delta, EmptyState, ErrorState, FilterBar, Gauge, Kbd, OfflineBanner, Skeleton, SplitView, Sparkline, Stat, TableSkeleton, ThemeProvider, Toaster, notify } from "../src";
import { roundCountStep } from "../src/components/Metrics";
import { mockMatchMedia } from "./setup";

describe("Metrics", () => {
  it("count up lands on the final value", async () => {
    const { container } = render(<CountUp value={1234} />);
    expect(screen.getByText("1,234", { selector: ".sx-sr-only" })).toBeInTheDocument();
    await waitFor(() => expect(container.querySelector("[aria-hidden]")?.textContent).toBe("1,234"), { timeout: 2000 });
  });
  it("count up never prints long decimals on the way to a whole number", async () => {
    const seen: string[] = [];
    const { container } = render(<CountUp value={71} format={(n) => `${n}%`} />);
    const obs = new MutationObserver(() => seen.push(container.querySelector("[aria-hidden]")?.textContent ?? ""));
    obs.observe(container, { childList: true, subtree: true, characterData: true });
    await waitFor(() => expect(container.querySelector("[aria-hidden]")?.textContent).toBe("71%"), { timeout: 2000 });
    obs.disconnect();
    expect(seen.filter((t) => /\.\d/.test(t))).toEqual([]);
  });
  it("count step precision follows the target", () => {
    expect(roundCountStep(70.948037512176, 71)).toBe(71);
    expect(roundCountStep(4.48371, 4.5)).toBe(4.5);
    expect(roundCountStep(4.48371, 4.52)).toBe(4.48);
  });
  it("count up shows the value at once with reduced motion", () => {
    mockMatchMedia({ "(prefers-reduced-motion: reduce)": true });
    const { container } = render(<CountUp value={88} />);
    expect(container.querySelector("[aria-hidden]")?.textContent).toBe("88");
    mockMatchMedia();
  });
  it("delta reads naturally and flips colour meaning with goodWhen", () => {
    const { rerender } = render(<Delta value={12} />);
    expect(screen.getByLabelText("Up 12%")).toHaveAttribute("data-dir", "up");
    rerender(<Delta value={12} goodWhen="down" />);
    expect(screen.getByLabelText("Up 12%")).toHaveAttribute("data-dir", "down");
    rerender(<Delta value={0} />);
    expect(screen.getByLabelText("No change 0%")).toHaveAttribute("data-dir", "flat");
  });
  it("stat shows label, value and delta", () => {
    render(<Stat label="Replies" value={42} delta={-3} note="vs last week" />);
    expect(screen.getByText("Replies")).toBeInTheDocument();
    expect(screen.getByText("42", { selector: ".sx-sr-only" })).toBeInTheDocument();
    expect(screen.getByLabelText("Down 3%")).toBeInTheDocument();
    expect(screen.getByText("vs last week")).toBeInTheDocument();
  });
  it("gauge exposes a meter role and clamps", () => {
    render(<Gauge value={1.7} label="Speed to lead" />);
    expect(screen.getByRole("meter", { name: "Speed to lead" })).toHaveAttribute("aria-valuenow", "100");
  });
  it("sparkline draws a path and describes itself", () => {
    const { container } = render(<Sparkline data={[1, 3, 2, 5, 4]} label="Replies" />);
    expect(container.querySelectorAll("path")).toHaveLength(2);
    expect(screen.getByRole("img", { name: /Replies: 5 points, last 4/ })).toBeInTheDocument();
    const empty = render(<Sparkline data={[1]} />);
    expect(empty.container.querySelector("path")?.getAttribute("d")).toBe("");
  });
  it("area chart legend toggles a series", async () => {
    render(<AreaChart data={[{ d: "Mon", a: 1, b: 2 }, { d: "Tue", a: 3, b: 1 }]} xKey="d" series={[{ key: "a", label: "Sent" }, { key: "b", label: "Replies" }]} />);
    const chip = screen.getByRole("button", { name: /Sent/ });
    expect(chip).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "false");
  });
});

describe("Surfaces and states", () => {
  it("renders cards, badges, avatars and keys", () => {
    render(<><Card title="Pipeline" glass lift>x</Card><Badge tone="success">Live</Badge><Avatar name="Ada Lovelace" /><Kbd>K</Kbd></>);
    expect(screen.getByRole("heading", { name: "Pipeline" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Ada Lovelace" })).toHaveTextContent("AL");
    expect(screen.getByText("Live")).toHaveClass("sx-badge--success");
  });
  it("empty state offers the next action", async () => {
    const act1 = vi.fn();
    render(<EmptyState title="No leads yet" body="Import a CSV to start." actionLabel="Import leads" onAction={act1} />);
    await userEvent.click(screen.getByRole("button", { name: "Import leads" }));
    expect(act1).toHaveBeenCalled();
  });
  it("error state says what happened and how to fix it", () => {
    render(<ErrorState title="Inbox not connected" whatHappened="The password was rejected." howToFix="Create a new app password and paste it again." onRetry={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("How to fix it: Create a new app password");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
  it("skeletons render", () => {
    render(<><Skeleton /><TableSkeleton rows={2} columns={3} /></>);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });
  it("offline banner appears when the browser goes offline", async () => {
    render(<OfflineBanner />);
    expect(screen.queryByRole("status")).toBeNull();
    act(() => window.dispatchEvent(new Event("offline")));
    expect(await screen.findByRole("status")).toHaveTextContent("You are offline");
    act(() => window.dispatchEvent(new Event("online")));
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  });
  it("toast with undo", async () => {
    const undo = vi.fn();
    render(<Toaster />);
    act(() => void notify.undo("Archived 3 leads", undo));
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(undo).toHaveBeenCalled();
    act(() => void notify.error("Could not send", "Check the mailbox password."));
    expect(await screen.findByText("Could not send")).toBeInTheDocument();
  });
});

describe("Shell", () => {
  it("marks the current page, navigates, and opens the mobile menu", async () => {
    const nav = vi.fn();
    const palette = vi.fn();
    render(
      <ThemeProvider><AppShell productName="Sample app" nav={[{ id: "overview", label: "Overview" }, { id: "pipeline", label: "Pipeline", count: 12 }]} activeId="pipeline" onNavigate={nav} onOpenPalette={palette}>
        <SplitView list={<p>list</p>} detail={<p>detail</p>} />
        <FilterBar><span>filters</span></FilterBar>
      </AppShell></ThemeProvider>,
    );
    expect(screen.getByRole("button", { name: /Pipeline/ })).toHaveAttribute("aria-current", "page");
    await userEvent.click(screen.getByRole("button", { name: "Overview" }));
    expect(nav).toHaveBeenCalledWith("overview");
    await userEvent.click(screen.getByRole("button", { name: /Search/ }));
    expect(palette).toHaveBeenCalled();
    const menu = screen.getByRole("button", { name: "Open menu" });
    await userEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("search")).toBeInTheDocument();
  });
});
