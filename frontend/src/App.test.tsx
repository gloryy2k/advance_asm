import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, expect, test, beforeEach } from "vitest";
import { App, AssetTable, ScanNew, ScanLog } from "./App";
beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("WebSocket", class { close() {} });
  location.hash = "";
});
test("review excludes hosts and launches only on explicit click", async () => {
  location.hash = "/scan/4/review";
  const config = {
    depth: "light",
    threads: 50,
    rate_limit: 150,
    scan_timeout: 900,
    nuclei_severity: "low,medium",
    skip_nmap: true,
    skip_nuclei: false,
    skip_active_crawl: false,
    categories_enabled: ["web"],
    excluded_hosts: [],
  };
  const request = vi
    .fn()
    .mockImplementation((path: string) =>
      Promise.resolve({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () =>
          path.endsWith("/config")
            ? config
            : {
                id: 4,
                status: "draft",
                stats_json: JSON.stringify({
                  resolved_scope: [
                    { pattern: "example.com", kind: "in", category: "web" },
                  ],
                }),
              },
      }),
    );
  vi.stubGlobal("fetch", request);
  render(<App />);
  fireEvent.click(await screen.findByLabelText("Include example.com"));
  expect(request.mock.calls.some((c) => c[0].endsWith("/launch"))).toBe(false);
  fireEvent.click(screen.getByText("Launch scan"));
  await waitFor(() =>
    expect(request.mock.calls.some((c) => c[0].endsWith("/launch"))).toBe(true),
  );
  const call = request.mock.calls.find((c) => c[0].endsWith("/launch"));
  expect(JSON.parse(call![1].body).config.excluded_hosts).toEqual([
    "example.com",
  ]);
});
test("surface renders rank, reasons and tech", () => {
  render(
    <AssetTable
      rows={[
        {
          id: 1,
          host: "api.example.com",
          rank_score: 8,
          status_code: 200,
          tech: ["GraphQL"],
          reasons: ["api", "fresh"],
        },
      ]}
    />,
  );
  expect(screen.getByText("8")).toBeInTheDocument();
  expect(screen.getByText("GraphQL")).toBeInTheDocument();
  expect(screen.getByText("api, fresh")).toBeInTheDocument();
});
test("resolve navigates to review without launching", async () => {
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => ({ scan_id: 4 }),
  });
  vi.stubGlobal("fetch", fetch);
  render(<ScanNew />);
  fireEvent.change(screen.getByLabelText(/Scope —/), {
    target: { value: "*.example.com" },
  });
  fireEvent.click(screen.getByText("Resolve & review"));
  await waitFor(() => expect(location.hash).toBe("#/scan/4/review"));
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe("/api/scope/resolve");
});
test("empty asset state is explicit", () => {
  render(<AssetTable rows={[]} />);
  expect(screen.getByText("Chưa có asset phù hợp.")).toBeInTheDocument();
});
test("portfolio renders NEW count from API", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((path: string) =>
      Promise.resolve({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () =>
          path.includes("health")
            ? { tools: {} }
            : [
                {
                  id: 1,
                  slug: "acme",
                  source: "raw",
                  new_count: 3,
                  asset_count: 9,
                  latest_scan: { id: 2, status: "done", depth: "light" },
                },
              ],
      }),
    ),
  );
  render(<App />);
  expect(await screen.findByText("acme")).toBeInTheDocument();
  expect(screen.getByText("+3 NEW")).toBeInTheDocument();
});
test("log reconnects with replay cursor", () => {
  vi.useFakeTimers();
  const sockets: any[] = [];
  class Socket {
    onopen: any;
    onclose: any;
    onerror: any;
    onmessage: any;
    constructor(public url: string) {
      sockets.push(this);
    }
    close() {}
  }
  vi.stubGlobal("WebSocket", Socket);
  const view = render(<ScanLog id="9" />);
  sockets[0].onmessage({
    data: JSON.stringify({ id: 12, type: "log", message: "hello" }),
  });
  sockets[0].onclose();
  vi.advanceTimersByTime(1500);
  expect(sockets[1].url).toContain("after=12");
  view.unmount();
  vi.useRealTimers();
});
