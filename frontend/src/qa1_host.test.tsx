import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "./App";
import { AssetTable } from "./pages/Program";
import { stubFetch } from "./test-utils";

beforeEach(() => { vi.restoreAllMocks(); location.hash = ""; });

const summary = {
  slug: "acme", source: "raw", target_path: "/tmp/acme", hunt_command: "cd /tmp/acme",
  latest_scan: { id: 2, status: "done", depth: "light" },
  last_completed_scan: { id: 2, status: "done", depth: "light" },
  changes: { new: 0, changed: 0, gone: 0 },
  findings_by_severity: { critical: 1, high: 0, medium: 2, low: 0, info: 0 },
  assets_active: 1, top_surface: [], draft_count: 0, schedule: null,
};

test("QA-1 Findings severity strip is all-time information, not a filter", async () => {
  const fetch = stubFetch((path) => path.endsWith("/summary") ? summary
    : path.includes("/findings?") ? { __total: 1, body: [{ id: 1, severity: "critical", name: "fixture", type: "nuclei", host: "127.0.0.1", detail: { matched_at: "http://127.0.0.1/a" } }] }
      : path === "/api/programs/acme" ? { scans: [{ id: 2, status: "done", depth: "light" }] } : {});
  location.hash = "/program/acme/findings";
  render(<App />);
  const strip = await screen.findByLabelText("Số finding theo mức nghiêm trọng, toàn bộ program");
  expect(within(strip).getByText("1 critical")).toBeInTheDocument();
  expect(within(strip).getByText("2 medium")).toBeInTheDocument();
  expect(within(strip).queryAllByRole("button")).toHaveLength(0);
  expect(within(strip).getByText(/toàn bộ program, mọi lần scan/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Mức nghiêm trọng"), { target: { value: "critical" } });
  await waitFor(() => expect(fetch.mock.calls.some((call) => String(call[0]).includes("severity=critical"))).toBe(true));
});

test("QA-1 Host tech tags collapse and expand", () => {
  render(<AssetTable rows={[{ id: 1, host: "127.0.0.1", tech: ["one", "two", "three", "four", "five"], reasons: [] } as any]} />);
  expect(screen.getByRole("button", { name: "+2 nữa" })).toBeInTheDocument();
  expect(screen.queryByText("five")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "+2 nữa" }));
  expect(screen.getByText("five")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "thu gọn" }));
  expect(screen.queryByText("five")).not.toBeInTheDocument();
});

test("QA-1 Overview distinguishes historical selection from current inventory", async () => {
  stubFetch((path) => path.endsWith("/summary") ? summary
    : path === "/api/programs/acme" ? { scans: [
      { id: 2, status: "done", depth: "light", stats: { subs: 3, urls: 4, findings: 1 } },
      { id: 1, status: "done", depth: "passive", stats: { subs: 1, urls: 2, findings: 0 } },
    ] } : {});
  location.hash = "/program/acme?scan=1";
  render(<App />);
  expect(await screen.findByText(/Đang xem scan #1/)).toBeInTheDocument();
  const banner = screen.getByTestId("data-scan");
  expect(banner).toHaveTextContent(/tình trạng hiện hành/);
  expect(banner).toHaveTextContent(/khác với scan #1 bạn đang xem ở trên/);
});
