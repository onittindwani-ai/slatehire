import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Button, CommandPalette, ConfirmDialog, ConnectionWizard, CopyButton, DataTable, DateRange, Dialog, Field, Kanban, SegmentedControl, TabsView, ThemeProvider, ThemeToggle, Tooltip, type Column } from "../src";

describe("Button", () => {
  it("shows processing then a success tick, then returns to idle", async () => {
    let done!: () => void;
    const onClick = vi.fn(() => new Promise<void>((r) => (done = r)));
    render(<Button onClick={onClick} minProcessingMs={0}>Save</Button>);
    const btn = screen.getByRole("button", { name: "Save" });
    await userEvent.click(btn);
    expect(btn).toHaveAttribute("data-state", "processing");
    expect(btn).toHaveAttribute("aria-busy", "true");
    await userEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
    await act(async () => done());
    await waitFor(() => expect(btn).toHaveAttribute("data-state", "success"));
    await waitFor(() => expect(btn).toHaveAttribute("data-state", "idle"), { timeout: 1500 });
  });
  it("returns to idle when the action fails", async () => {
    const onClick = vi.fn(() => Promise.reject(new Error("nope")));
    render(<Button onClick={onClick} minProcessingMs={0}>Send</Button>);
    const btn = screen.getByRole("button", { name: "Send" });
    await userEvent.click(btn);
    await waitFor(() => expect(btn).toHaveAttribute("data-state", "idle"));
  });
  it("explains why it is disabled and does not fire", async () => {
    const onClick = vi.fn();
    render(<Button disabled disabledReason="Connect an inbox first" onClick={onClick}>Send</Button>);
    const btn = screen.getByRole("button", { name: "Send" });
    expect(btn).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
    await userEvent.hover(btn);
    expect(await screen.findAllByText("Connect an inbox first")).not.toHaveLength(0);
  });
  it("skips the states when feedback is off", async () => {
    const onClick = vi.fn();
    render(<Button feedback={false} onClick={onClick}>Go</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Go" })).toHaveAttribute("data-state", "idle");
  });
});

describe("Field", () => {
  it("validates after blur, counts characters and clears", async () => {
    function Wrap() {
      const [v, setV] = useState("");
      return <Field label="Email" value={v} onChange={setV} maxLength={20} clearable validate={(x) => (x.includes("@") ? null : "Add an @ and a domain, like name@company.com")} />;
    }
    render(<Wrap />);
    const input = screen.getByLabelText("Email");
    await userEvent.type(input, "ada");
    expect(screen.queryByRole("alert")).toBeNull();
    await userEvent.tab();
    expect(screen.getByRole("alert")).toHaveTextContent("Add an @");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("3/20")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear Email" }));
    expect(input).toHaveValue("");
  });
});

describe("Navigation", () => {
  it("segmented control moves with arrow keys and keeps one tab stop", async () => {
    function Wrap() {
      const [v, setV] = useState<"a" | "b" | "c">("a");
      return <SegmentedControl label="Pick" value={v} onChange={setV} options={[{ value: "a", label: "A" }, { value: "b", label: "B" }, { value: "c", label: "C" }]} />;
    }
    render(<Wrap />);
    const a = screen.getByRole("radio", { name: "A" });
    a.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "B" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "A" })).toHaveAttribute("tabindex", "-1");
    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "C" })).toHaveAttribute("aria-checked", "true");
  });
  it("date range offers four presets", async () => {
    const on = vi.fn();
    render(<DateRange value="7d" onChange={on} />);
    await userEvent.click(screen.getByRole("radio", { name: "30 days" }));
    expect(on).toHaveBeenCalledWith("30d");
  });
  it("tabs switch content", async () => {
    render(<TabsView items={[{ value: "a", label: "One", content: <p>first</p> }, { value: "b", label: "Two", content: <p>second</p> }]} />);
    expect(screen.getByText("first")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Two" }));
    expect(screen.getByText("second")).toBeInTheDocument();
  });
});

describe("Overlays", () => {
  it("dialog opens, labels itself and closes with escape", async () => {
    function Wrap() {
      const [o, setO] = useState(true);
      return <Dialog open={o} onOpenChange={setO} title="Delete lead" description="This removes the lead.">body</Dialog>;
    }
    render(<Wrap />);
    expect(screen.getByRole("dialog", { name: "Delete lead" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
  it("confirm dialog runs the action then closes", async () => {
    const onConfirm = vi.fn();
    function Wrap() {
      const [o, setO] = useState(true);
      return <ConfirmDialog open={o} onOpenChange={setO} title="Remove" description="Cannot be undone." confirmLabel="Remove" destructive onConfirm={onConfirm} />;
    }
    render(<Wrap />);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull(), { timeout: 2000 });
  });
  it("tooltip shows on focus", async () => {
    render(<Tooltip content="Helpful words" delay={0}><button>Hi</button></Tooltip>);
    await userEvent.tab();
    expect((await screen.findAllByText("Helpful words")).length).toBeGreaterThan(0);
  });
});

describe("CommandPalette", () => {
  it("opens with the keyboard shortcut, filters and runs an item", async () => {
    const run = vi.fn();
    render(<CommandPalette items={[{ id: "1", label: "Go to pipeline", group: "Navigate", onSelect: run, shortcut: ["G", "P"] }, { id: "2", label: "Add lead", group: "Actions", onSelect: () => {} }]} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = await screen.findByPlaceholderText("Search or run an action");
    await userEvent.type(input, "pipe");
    expect(screen.queryByText("Add lead")).toBeNull();
    await userEvent.click(screen.getByText("Go to pipeline"));
    expect(run).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByPlaceholderText("Search or run an action")).toBeNull());
  });
  it("says so when nothing matches", async () => {
    render(<CommandPalette open onOpenChange={() => {}} items={[{ id: "1", label: "Alpha", group: "G", onSelect: () => {} }]} />);
    await userEvent.type(await screen.findByPlaceholderText("Search or run an action"), "zzzz");
    expect(await screen.findByText(/Nothing matches/)).toBeInTheDocument();
  });
});

type Row = { id: string; name: string; score: number };
const columns: Column<Row>[] = [
  { key: "name", header: "Name", sortValue: (r) => r.name },
  { key: "score", header: "Score", align: "right", sortValue: (r) => r.score },
];
const makeRows = (n: number): Row[] => Array.from({ length: n }, (_, i) => ({ id: `r${i}`, name: `Lead ${String(i).padStart(4, "0")}`, score: (i * 37) % 100 }));

describe("DataTable", () => {
  it("only renders a window of 5,000 rows", () => {
    render(<DataTable columns={columns} rows={makeRows(5000)} rowKey={(r) => r.id} label="Leads" />);
    const rendered = screen.getAllByRole("row").length;
    expect(rendered).toBeLessThan(40);
    expect(screen.getByText("5,000 rows")).toBeInTheDocument();
    expect(screen.getByRole("grid")).toHaveAttribute("aria-rowcount", "5001");
  });
  it("sorts ascending, descending, then back", async () => {
    render(<DataTable columns={columns} rows={makeRows(20)} rowKey={(r) => r.id} label="Leads" />);
    const firstCell = () => screen.getAllByRole("gridcell")[0]!.textContent;
    expect(firstCell()).toBe("Lead 0000");
    await userEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(screen.getByRole("columnheader", { name: /Name/ })).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(firstCell()).toBe("Lead 0019");
    await userEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(firstCell()).toBe("Lead 0000");
  });
  it("moves with j and k, opens with enter, selects with x and shows the bulk bar", async () => {
    const open = vi.fn();
    const bulk = vi.fn();
    render(<DataTable columns={columns} rows={makeRows(10)} rowKey={(r) => r.id} label="Leads" selectable onRowOpen={open} bulkActions={(sel, clear) => <Button onClick={() => { bulk(sel.length); clear(); }}>Archive</Button>} />);
    screen.getByRole("grid").focus();
    await userEvent.keyboard("jj");
    await userEvent.keyboard("{Enter}");
    expect(open).toHaveBeenCalledWith(expect.objectContaining({ id: "r2" }));
    await userEvent.keyboard("kx");
    expect(screen.getByRole("toolbar")).toHaveTextContent("1 selected");
    await userEvent.keyboard("jx");
    expect(screen.getByRole("toolbar")).toHaveTextContent("2 selected");
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(bulk).toHaveBeenCalledWith(2));
    await waitFor(() => expect(screen.queryByRole("toolbar")).toBeNull());
  });
});

describe("Kanban", () => {
  it("renders cards in their columns with counts", () => {
    render(<Kanban columns={[{ id: "new", title: "New" }, { id: "won", title: "Won" }]} items={[{ id: "1", columnId: "new" }, { id: "2", columnId: "new" }, { id: "3", columnId: "won" }]} renderCard={(i) => <span>card {i.id}</span>} onMove={() => {}} />);
    const newCol = screen.getByRole("region", { name: "New" });
    expect(within(newCol).getAllByText(/card/)).toHaveLength(2);
    expect(within(screen.getByRole("region", { name: "Won" })).getByText("1")).toBeInTheDocument();
  });
});

describe("Kanban cards", () => {
  const cols = [{ id: "new", title: "New" }, { id: "won", title: "Won" }];
  const items = [{ id: "1", columnId: "new" }, { id: "2", columnId: "won" }];

  it("is a labelled group, not a button, so it can hold buttons and links", () => {
    render(
      <Kanban columns={cols} items={items} onMove={() => {}} cardLabel={(i) => `Lead ${i.id}`}
        renderCard={(i) => <div><a href="#x">link {i.id}</a><button type="button">act {i.id}</button></div>} />,
    );
    const card = screen.getByRole("group", { name: "Lead 1" });
    expect(card).toHaveAttribute("aria-roledescription", "draggable card");
    expect(card).not.toHaveAttribute("role", "button");
    expect(within(card).getByRole("link", { name: "link 1" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "act 1" })).toBeInTheDocument();
    expect(card.querySelector("[role=button] [role=button], button button, a button")).toBeNull();
  });

  it("opens a card with Enter on the card and with its Open button, without nesting problems", async () => {
    const onOpen = vi.fn();
    render(<Kanban columns={cols} items={items} onMove={() => {}} onOpen={onOpen} cardLabel={(i) => `Lead ${i.id}`} renderCard={(i) => <span>card {i.id}</span>} />);
    const card = screen.getByRole("group", { name: "Lead 1" });
    card.focus();
    await userEvent.keyboard("{Enter}");
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenLastCalledWith(items[0]);
    await userEvent.click(screen.getByRole("button", { name: "Open Lead 2" }));
    expect(onOpen).toHaveBeenLastCalledWith(items[1]);
    await userEvent.tab();
    expect(onOpen).toHaveBeenCalledTimes(2);
  });

  it("a click on a button inside a card does not open or move the card", async () => {
    const onOpen = vi.fn();
    const onMove = vi.fn();
    const act = vi.fn();
    render(<Kanban columns={cols} items={items} onMove={onMove} onOpen={onOpen} renderCard={(i) => <button type="button" onClick={act}>act {i.id}</button>} />);
    await userEvent.click(screen.getByRole("button", { name: "act 1" }));
    expect(act).toHaveBeenCalledTimes(1);
    expect(onOpen).not.toHaveBeenCalled();
    expect(onMove).not.toHaveBeenCalled();
  });

  it("shows no Open button when onOpen is not given and uses a default label", () => {
    render(<Kanban columns={cols} items={items} onMove={() => {}} renderCard={(i) => <span>card {i.id}</span>} />);
    expect(screen.queryByRole("button", { name: /^Open/ })).toBeNull();
    expect(screen.getByRole("group", { name: "Card 2" })).toBeInTheDocument();
  });
});

describe("Theme, copy and wizard", () => {
  it("toggles the theme and remembers it", async () => {
    render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
    await userEvent.click(screen.getByRole("button", { name: /Switch to dark theme/ }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    expect(localStorage.getItem("sx-theme")).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: /Switch to light theme/ }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
  });
  it("copy button morphs to a tick", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<CopyButton value="hello" />);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("hello");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
  it("wizard reports test results", async () => {
    const onStatus = vi.fn();
    render(<ConnectionWizard onStatus={onStatus} steps={[{ id: "mail", title: "Email", description: "Connect an inbox", status: "todo", onTest: async () => {} }, { id: "bad", title: "SMS", description: "Texting", status: "todo", onTest: async () => { throw new Error("401"); } }]} />);
    const [ok, bad] = screen.getAllByRole("button", { name: "Test connection" });
    await userEvent.click(ok!);
    await waitFor(() => expect(onStatus).toHaveBeenCalledWith("mail", "ok"));
    await userEvent.click(bad!);
    await waitFor(() => expect(onStatus).toHaveBeenCalledWith("bad", "error"));
  });
});
