import { render, screen, fireEvent, waitFor, act, within } from "@testing-library/react";
import { vi, expect, test, beforeEach, describe } from "vitest";
import { App } from "./App";
import { baseConfig, baseReview, calls, FakeSocket, health, stubFetch } from "./test-utils";
import { explain } from "./lib/errors";
import { ApiError } from "./api/client";
import { parseRoute, programPath } from "./lib/router";
import { cidrSize } from "./lib/format";
import { phaseState } from "./lib/phases";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  location.hash = "";
});

const okPreview = (over: object = {}) => ({
  mode: "raw", ok: true, message: "", summary: { in: 1, out: 0, errors: 0, warnings: 0 },
  lines: [{ box: "in", line: 1, raw: "example.com", status: "ok", kind: "in", category: "web", normalized: "example.com", note: "" }],
  ...over,
});

describe("router, errors, helpers", () => {
  test("routes: tabs in URL, legacy /target, unknown tab falls back", () => {
    expect(parseRoute("/program/acme/diff")).toEqual({ page: "program", slug: "acme", tab: "diff" });
    expect(parseRoute("/target/acme")).toEqual({ page: "program", slug: "acme", tab: "overview" });
    expect(parseRoute("/program/acme/bogus")).toMatchObject({ tab: "overview" });
    expect(parseRoute("/scan/7/review")).toEqual({ page: "review", id: "7" });
    expect(parseRoute("/scan/7")).toEqual({ page: "run", id: "7" });
    expect(programPath("a b", "brief")).toBe("/program/a%20b/brief");
  });
  test("errors become actionable sentences", () => {
    expect(explain(new ApiError("x", "no_completed_scan", 422))).toMatch(/Chưa có scan hoàn tất/);
    expect(explain(new TypeError("Failed to fetch"))).toMatch(/Không kết nối được backend/);
    expect(explain(new ApiError("Scope có 1 dòng lỗi — ô IN dòng 2", "scope_invalid", 422))).toMatch(/dòng 2/);
    expect(explain(new Error("temporary outage"))).toBe("temporary outage");
  });
  test("cidr size and phase state", () => {
    expect(cidrSize("10.0.0.0/24")).toBe(256);
    expect(cidrSize("api.example.com")).toBeNull();
    const phases = phaseState([{ type: "phase", phase: "live_probe" }], false);
    expect(phases.find((p) => p.key === "subdomain_enum")!.state).toBe("pending");
    expect(phases.find((p) => p.key === "live_probe")!.state).toBe("current");
    expect(phaseState([{ type: "phase", phase: "live_probe" }], true).find((p) => p.key === "live_probe")!.state).toBe("done");
  });
});

describe("New program", () => {
  test("H1: any URL form is previewed, resolve is gated, then goes to review without launching", async () => {
    const fetch = stubFetch((path, init) => {
      if (path === "/api/health") return health({ h1_api: true });
      if (path === "/api/scope/preview") return { mode: "h1", ok: true, message: "", handle: "live_nation", lines: [], summary: { in: 0, out: 0, errors: 0, warnings: 0 } };
      if (path === "/api/scope/resolve") return { scan_id: 4 };
      if (path.endsWith("/review")) return baseReview();
      if (path.endsWith("/config")) return baseConfig;
      return {};
    });
    location.hash = "/new";
    render(<App />);
    const submit = screen.getByRole("button", { name: "Resolve & review" });
    expect(submit).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/handle hoặc URL/);
    fireEvent.change(screen.getByLabelText("HackerOne handle hoặc URL"), { target: { value: "https://hackerone.com/live_nation?type=team" } });
    expect(await screen.findByText("live_nation")).toBeInTheDocument();
    await waitFor(() => expect(submit).toBeEnabled());
    expect(screen.getByText(/Dùng API HackerOne/)).toBeInTheDocument();
    fireEvent.click(submit);
    await waitFor(() => expect(location.hash).toBe("#/scan/4/review"));
    expect(calls(fetch, "/launch")).toHaveLength(0);
    const resolve = JSON.parse(calls(fetch, "/api/scope/resolve", "POST")[0][1]!.body as string);
    expect(resolve).toEqual({ input: "https://hackerone.com/live_nation?type=team", policy_text: "" });
  });

  test("raw: bad line blocks resolve and is named; IN and OUT go to separate fields", async () => {
    let preview: any = okPreview({
      ok: false, message: "Có dòng lỗi", summary: { in: 1, out: 0, errors: 1, warnings: 0 },
      lines: [{ box: "in", line: 2, raw: "10.0.0.5/24", status: "error", kind: "in", category: "", normalized: "10.0.0.5/24", note: "CIDR không chuẩn; ý bạn là 10.0.0.0/24?" }],
    });
    const fetch = stubFetch((path) => (path === "/api/health" ? health() : path === "/api/scope/preview" ? preview
      : path.endsWith("/review") ? baseReview() : path.endsWith("/config") ? baseConfig : { scan_id: 9 }));
    location.hash = "/new";
    render(<App />);
    fireEvent.click(screen.getByRole("tab", { name: "Raw scope" }));
    fireEvent.change(screen.getByLabelText(/Scope — mỗi dòng/), { target: { value: "a.example.com\n10.0.0.5/24" } });
    expect(await screen.findByText(/ý bạn là 10.0.0.0\/24/)).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Resolve & review" });
    expect(submit).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Có dòng lỗi");
    preview = okPreview();
    fireEvent.change(screen.getByLabelText(/Scope — mỗi dòng/), { target: { value: "example.com" } });
    fireEvent.change(screen.getByLabelText(/Loại trừ \(OUT\)/), { target: { value: "admin.example.com" } });
    fireEvent.change(screen.getByLabelText(/Tên program/), { target: { value: "acme-internal" } });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);
    await waitFor(() => expect(location.hash).toBe("#/scan/9/review"));
    const body = JSON.parse(calls(fetch, "/api/scope/resolve", "POST")[0][1]!.body as string);
    expect(body).toMatchObject({ input: "raw", scope: ["example.com"], scope_out: ["admin.example.com"], name: "acme-internal" });
  });

  test("resolve failure shows the server's line-level message", async () => {
    stubFetch((path) =>
      path === "/api/scope/resolve"
        ? { __error: { status: 422, code: "scope_invalid", message: "Scope có 1 dòng lỗi — ô IN dòng 2" } }
        : path === "/api/health" ? health() : okPreview({ mode: "h1", handle: "x" }));
    location.hash = "/new";
    render(<App />);
    fireEvent.change(screen.getByLabelText("HackerOne handle hoặc URL"), { target: { value: "acme" } });
    const submit = screen.getByRole("button", { name: "Resolve & review" });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);
    expect(await screen.findByRole("alert")).toHaveTextContent("dòng 2");
  });
});

describe("Review", () => {
  function setup(review = baseReview(), config: object = baseConfig) {
    const fetch = stubFetch((path, init) => {
      if (path === "/api/health") return health();
      if (path.endsWith("/review")) return review;
      if (path.endsWith("/config")) return config;
      if (path.endsWith("/launch")) return { scan_id: 4, status: "queued" };
      return {};
    });
    location.hash = "/scan/4/review";
    render(<App />);
    return fetch;
  }

  test("shows policy, warnings, OUT, manual assets, CIDR size and missing tools before launch", async () => {
    setup();
    expect(await screen.findByText(/Automated scanning limited to 5 req\/s/)).toBeInTheDocument();
    expect(screen.getByText("Dữ liệu từ nguồn công khai", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/tự động\/scanner/)).toBeInTheDocument();
    expect(screen.getByText(/10\.0\.0\.0\/24 \(256 địa chỉ\)/)).toBeInTheDocument();
    expect(screen.getAllByText("legacy.acme.com").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/luôn bị chặn/).length).toBeGreaterThan(0);
    expect(screen.getByText(/mobile\/khác làm tay/)).toBeInTheDocument();
    expect(screen.getByText(/Thiếu công cụ cho Light: nuclei/)).toBeInTheDocument();
  });

  test("Launch needs explicit automation ack above passive; sends ack + reviewed config", async () => {
    const fetch = setup();
    const launch = await screen.findByRole("button", { name: "Launch scan" });
    expect(launch).toBeDisabled();
    expect(screen.getAllByRole("status").some((n) => /xác nhận program cho phép/.test(n.textContent || ""))).toBe(true);
    fireEvent.click(screen.getByLabelText(/Tôi đã đọc policy/));
    expect(launch).toBeEnabled();
    expect(calls(fetch, "/launch")).toHaveLength(0);
    fireEvent.click(launch);
    await waitFor(() => expect(location.hash).toBe("#/scan/4"));
    const body = JSON.parse(calls(fetch, "/launch")[0][1]!.body as string);
    expect(body.automation_ack).toBe(true);
    expect(body.config.depth).toBe("light");
  });

  test("passive needs no ack and applies its preset; strong needs a second confirmation", async () => {
    const fetch = setup();
    await screen.findByRole("button", { name: "Launch scan" });
    fireEvent.click(screen.getByRole("radio", { name: /Passive/ }));
    const launch = screen.getByRole("button", { name: "Launch scan" });
    expect(launch).toBeEnabled();
    expect(screen.queryByLabelText(/Tôi đã đọc policy/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Strong/ }));
    fireEvent.click(screen.getByLabelText(/Tôi đã đọc policy/));
    expect(launch).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Tôi hiểu Strong/));
    expect(launch).toBeEnabled();
    fireEvent.click(launch);
    await waitFor(() => expect(calls(fetch, "/launch")).toHaveLength(1));
    const config = JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config;
    expect(config).toMatchObject({ depth: "strong", skip_nmap: false, scan_timeout: 2700, nuclei_severity: "low,medium,high,critical" });
  });

  test("excluding an entry changes exactly what is launched", async () => {
    const fetch = setup();
    fireEvent.click(await screen.findByLabelText("Include *.acme.com"));
    fireEvent.click(screen.getByLabelText(/Tôi đã đọc policy/));
    fireEvent.click(screen.getByRole("button", { name: "Launch scan" }));
    await waitFor(() => expect(calls(fetch, "/launch")).toHaveLength(1));
    const config = JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config;
    expect(config.excluded_hosts).toEqual(["*.acme.com"]);
    expect(config.categories_enabled).toEqual(["web", "wildcard"]);
  });

  test("turning every group off blocks launch with a reason", async () => {
    setup();
    fireEvent.click(await screen.findByLabelText(/Tôi đã đọc policy/));
    fireEvent.click(screen.getByLabelText("Nhóm Wildcard (liệt kê subdomain)"));
    fireEvent.click(screen.getByLabelText("Nhóm Web / domain"));
    expect(screen.getByRole("button", { name: "Launch scan" })).toBeDisabled();
    expect(screen.getAllByRole("status").some((n) => /Chưa có mục IN/.test(n.textContent || ""))).toBe(true);
    fireEvent.click(screen.getByLabelText("Nhóm Web / domain"));
    expect(screen.getByRole("button", { name: "Launch scan" })).toBeEnabled();
  });

  test("an already launched scan cannot be launched again", async () => {
    setup(baseReview({ scan: { id: 4, depth: "light", status: "running" } }));
    expect(await screen.findByRole("button", { name: "Launch scan" })).toBeDisabled();
    expect(screen.getByRole("link", { name: /Xem scan/ })).toBeInTheDocument();
  });

  test("launch error is surfaced and the page stays", async () => {
    stubFetch((path) =>
      path === "/api/health" ? health() : path.endsWith("/review") ? baseReview() : path.endsWith("/config") ? baseConfig
        : { __error: { status: 422, code: "invalid_state", message: "Only draft scans can be launched" } });
    location.hash = "/scan/4/review";
    render(<App />);
    fireEvent.click(await screen.findByLabelText(/Tôi đã đọc policy/));
    fireEvent.click(screen.getByRole("button", { name: "Launch scan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Thao tác không hợp lệ/);
    expect(location.hash).toBe("#/scan/4/review");
  });
});

describe("Run", () => {
  const scan = (status: string, extra: object = {}) => ({ id: 9, depth: "light", status, started_at: "2026-10-14T01:00:00Z", ...extra });

  test("progress stepper follows phase events; hunt command appears when done", async () => {
    let status = "running";
    stubFetch((path) => (path.endsWith("/review") ? baseReview({ scan: scan(status) }) : path.endsWith("/config") ? baseConfig : scan(status)));
    location.hash = "/scan/9";
    render(<App />);
    await screen.findByText("đang chạy");
    act(() => FakeSocket.instances[0].emit({ id: 1, type: "phase", phase: "live_probe", message: "HTTP Probing" }));
    expect(screen.getByRole("list", { name: "Tiến độ recon" })).toBeInTheDocument();
    expect(screen.getByText("Probe HTTP").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.queryByText(/cd "/)).not.toBeInTheDocument();
    status = "done";
    act(() => FakeSocket.instances[0].emit({ id: 2, type: "done", status: "done" }));
    expect(await screen.findByText('cd "/data/targets/acme" && claude')).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xem Brief" })).toHaveAttribute("href", "#/program/acme/brief");
  });

  test("cancel asks for confirmation first", async () => {
    const fetch = stubFetch((path, init) => (path.endsWith("/cancel") ? scan("cancelled") : path.endsWith("/review") ? baseReview() : path.endsWith("/config") ? baseConfig : scan("running")));
    location.hash = "/scan/9";
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel scan" }));
    expect(calls(fetch, "/cancel")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Xác nhận huỷ scan" }));
    await waitFor(() => expect(calls(fetch, "/cancel", "POST")).toHaveLength(1));
  });

  test("failed scan offers a fresh draft with the same scope", async () => {
    const fetch = stubFetch((path) =>
      path.endsWith("/rescan") ? { scan_id: 12, slug: "acme" }
        : path === "/api/health" ? health() : path.endsWith("/config") ? baseConfig
        : path.endsWith("/review") ? baseReview() : scan("failed", { error: "Dashboard interrupted" }));
    location.hash = "/scan/9";
    render(<App />);
    expect(await screen.findByText("Dashboard interrupted")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Tạo scan mới/ }));
    await waitFor(() => expect(location.hash).toBe("#/scan/12/review"));
    expect(calls(fetch, "/rescan", "POST")).toHaveLength(1);
  });

  test.each(["done", "done_partial", "failed", "cancelled"])("REST reaches %s when WebSocket fails, then stops polling", async (final) => {
    vi.useFakeTimers();
    let n = 0;
    const fetch = stubFetch((path) => (path.endsWith("/review") ? baseReview() : scan(++n === 1 ? "queued" : final)));
    class Broken extends FakeSocket {
      close() { this.onclose?.(); }
    }
    vi.stubGlobal("WebSocket", Broken);
    location.hash = "/scan/9";
    const view = render(<App />);
    try {
      await act(async () => { await vi.advanceTimersByTimeAsync(10); });
      const badge = () => screen.getByRole("status", { name: "Scan status" });
      expect(badge()).toHaveTextContent("đang chờ");
      act(() => FakeSocket.instances[0].onerror?.());
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      expect(badge()).not.toHaveTextContent("đang chờ");
      expect(screen.queryByRole("button", { name: "Cancel scan" })).not.toBeInTheDocument();
      const scanCalls = () => fetch.mock.calls.filter((c) => String(c[0]) === "/api/scans/9").length;
      const atEnd = scanCalls();
      await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
      expect(scanCalls()).toBe(atEnd);
    } finally {
      view.unmount();
      vi.useRealTimers();
    }
  });

  test("transient REST failure is shown, retried and cleaned up on unmount", async () => {
    vi.useFakeTimers();
    let n = 0;
    const fetch = stubFetch((path) => {
      if (path.endsWith("/review")) return baseReview();
      return ++n === 1 ? new Error("temporary outage") : scan("running");
    });
    location.hash = "/scan/9";
    const view = render(<App />);
    try {
      await act(async () => { await vi.advanceTimersByTimeAsync(10); });
      expect(screen.getByRole("alert")).toHaveTextContent("temporary outage");
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      expect(screen.getByRole("status", { name: "Scan status" })).toHaveTextContent("đang chạy");
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      view.unmount();
      const after = fetch.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(fetch.mock.calls.length).toBe(after);
    } finally {
      view.unmount();
      vi.useRealTimers();
    }
  });

  test("log reconnects with the replay cursor", async () => {
    vi.useFakeTimers();
    stubFetch((path) => (path.endsWith("/review") ? baseReview() : scan("running")));
    location.hash = "/scan/9";
    const view = render(<App />);
    try {
      await act(async () => { await Promise.resolve(); });
      act(() => FakeSocket.instances[0].emit({ id: 12, type: "log", message: "hello" }));
      act(() => FakeSocket.instances[0].onclose?.());
      await act(async () => { await vi.advanceTimersByTimeAsync(1600); });
      expect(FakeSocket.instances[1].url).toContain("after=12");
      expect(screen.getByRole("log")).toHaveTextContent("hello");
    } finally {
      view.unmount();
      vi.useRealTimers();
    }
  });
});

describe("Portfolio", () => {
  const card = (over: object = {}) => ({
    id: 1, slug: "acme", source: "h1", asset_count: 9, new_count: 3, finding_count: 2, draft_count: 0, monitoring: false,
    latest_scan: { id: 2, status: "done", depth: "light" }, ...over,
  });

  test("cards show NEW, attention flags and link to the program", async () => {
    stubFetch((path) => (path === "/api/programs" ? [card()] : path === "/api/drafts" ? [] : health()));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "acme" })).toBeInTheDocument();
    expect(screen.getByText("+3 NEW")).toBeInTheDocument();
    expect(screen.getByText(/Chưa bật monitoring/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /acme/ })).toHaveAttribute("href", "#/program/acme");
  });

  test("empty state explains the 3 steps and offers the first action", async () => {
    stubFetch((path) => (path === "/api/programs" || path === "/api/drafts" ? [] : health()));
    render(<App />);
    expect(await screen.findByText("Chưa có program nào")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Thêm program đầu tiên" })).toHaveAttribute("href", "#/new");
  });

  test("drafts can be resumed or deleted", async () => {
    let drafts: object[] = [{ id: 5, slug: "x", source: "raw", depth: "light", created_at: null, in: 2, out: 1 }];
    const fetch = stubFetch((path, init) => {
      if (init?.method === "DELETE") { drafts = []; return { deleted: 5 }; }
      return path === "/api/programs" ? [] : path === "/api/drafts" ? drafts : health();
    });
    vi.stubGlobal("confirm", () => true);
    render(<App />);
    expect(await screen.findByRole("link", { name: "Tiếp tục review" })).toHaveAttribute("href", "#/scan/5/review");
    fireEvent.click(screen.getByRole("button", { name: "Xoá" }));
    await waitFor(() => expect(calls(fetch, "/api/scans/5", "DELETE")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText(/Bản nháp chờ review/)).not.toBeInTheDocument());
  });

  test("API failure shows an error with retry", async () => {
    stubFetch((path) => (path === "/api/programs" ? { __error: { status: 500, message: "boom" } } : path === "/api/drafts" ? [] : health()));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(screen.getByRole("button", { name: "Thử lại" })).toBeInTheDocument();
  });
});

describe("Program", () => {
  const summary = (over: object = {}) => ({
    slug: "acme", source: "h1", handle: "acme", target_path: "/t/acme", hunt_command: 'cd "targets/acme" && claude',
    hunt_note: "Chạy từ thư mục dự án", latest_scan: { id: 2, status: "done", depth: "light" },
    last_completed_scan: { id: 2, status: "done", depth: "light" }, changes: { new: 4, changed: 1, gone: 0 },
    findings_by_severity: { critical: 1, high: 0, medium: 2, low: 0, info: 0 }, assets_active: 12,
    top_surface: [{ id: 1, host: "api.acme.com", rank_score: 7.5, reasons: ["api", "fresh"] }], draft_count: 0, schedule: null, ...over,
  });

  test("overview: counts, hunt command with Docker note, top surface; tab is a link in the URL", async () => {
    stubFetch((path) => (path.endsWith("/summary") ? summary() : path === "/api/programs/acme" ? { scans: [{ id: 2, depth: "light", status: "done" }] } : {}));
    location.hash = "/program/acme";
    render(<App />);
    expect(await screen.findByText('cd "targets/acme" && claude')).toBeInTheDocument();
    expect(screen.getByText("Chạy từ thư mục dự án")).toBeInTheDocument();
    expect(screen.getByText("api.acme.com")).toBeInTheDocument();
    expect(screen.getByText("API, mới")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Diff" })).toHaveAttribute("href", "#/program/acme/diff");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  });

  test("monitoring above passive needs ack; enabling posts interval, depth, enabled", async () => {
    const fetch = stubFetch((path) => (path.endsWith("/summary") ? summary() : path.endsWith("/schedule") ? {} : { scans: [] }));
    location.hash = "/program/acme";
    render(<App />);
    const enable = await screen.findByRole("button", { name: "Bật giám sát" });
    expect(enable).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Program cho phép scan tự động theo lịch/));
    fireEvent.change(screen.getByLabelText("Interval"), { target: { value: "weekly" } });
    fireEvent.click(enable);
    await waitFor(() => expect(calls(fetch, "/schedule")).toHaveLength(1));
    expect(JSON.parse(calls(fetch, "/schedule")[0][1]!.body as string)).toEqual({ interval: "weekly", depth: "light", enabled: true });
  });

  test("diff tab: filter, readable change text, pagination total", async () => {
    const rows = [
      { id: 1, change: "new", entity_ref: "a.acme.com", detail: { after: { status_code: 200, tech: ["nginx"] } } },
      { id: 2, change: "changed", entity_ref: "b.acme.com", detail: { status_code: { before: 200, after: 403 }, tech: { before: ["php"], after: ["php", "nginx"] } } },
      { id: 3, change: "gone", entity_ref: "c.acme.com", detail: {} },
    ];
    const fetch = stubFetch((path) => (path.includes("/diff") ? { __total: 120, body: rows } : path.endsWith("/summary") ? summary() : { scans: [] }));
    location.hash = "/program/acme/diff";
    render(<App />);
    expect(await screen.findByText("HTTP 200 · nginx")).toBeInTheDocument();
    expect(screen.getByText(/status_code: 200 → 403; tech \+nginx/)).toBeInTheDocument();
    expect(screen.getByText(/không còn xuất hiện/)).toBeInTheDocument();
    expect(screen.getByText(/Trang 1\/3 · 120 mục/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Thay đổi" }));
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("change=changed"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Sau →" }));
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("offset=50"))).toBe(true));
  });

  test("assets tab sends search, group and state filters", async () => {
    const fetch = stubFetch((path) => (path.includes("/assets") ? { __total: 1, body: [{ id: 1, host: "api.acme.com", rank_score: 3 }] } : path.endsWith("/summary") ? summary() : { scans: [] }));
    location.hash = "/program/acme/assets";
    render(<App />);
    await screen.findByText("api.acme.com");
    fireEvent.change(screen.getByLabelText("Tìm host"), { target: { value: "api" } });
    fireEvent.change(screen.getByLabelText("Nhóm"), { target: { value: "cidr" } });
    fireEvent.change(screen.getByLabelText("Trạng thái"), { target: { value: "gone" } });
    await waitFor(() => {
      const last = String(fetch.mock.calls.filter((c) => String(c[0]).includes("/assets")).at(-1)![0]);
      expect(last).toContain("q=api");
      expect(last).toContain("category=cidr");
      expect(last).toContain("state=gone");
    });
  });

  test("findings: severity badge, host column and empty state", async () => {
    let empty = false;
    stubFetch((path) => path.includes("/findings")
      ? { __total: empty ? 0 : 1, body: empty ? [] : [{ id: 1, severity: "critical", name: "CVE-1", type: "nuclei", host: "api.acme.com", detail: { matched_at: "https://api.acme.com/x" } }] }
      : path.endsWith("/summary") ? summary() : { scans: [] });
    location.hash = "/program/acme/findings";
    const view = render(<App />);
    expect(await screen.findByText("CVE-1")).toBeInTheDocument();
    expect(screen.getByText("https://api.acme.com/x")).toBeInTheDocument();
    view.unmount();
    empty = true;
    render(<App />);
    expect(await screen.findByText("Chưa có finding")).toBeInTheDocument();
  });

  test("brief before first scan explains instead of erroring; Program tab still editable", async () => {
    const doc = "# acme\n<!-- user-editable -->\nold\n<!-- /user-editable -->\n";
    const fetch = stubFetch((path, init) =>
      path.endsWith("/brief") ? { __error: { status: 422, code: "no_completed_scan", message: "x" } }
        : path.endsWith("/program") ? (init?.method === "PUT" ? { saved: true } : doc)
          : path.endsWith("/summary") ? summary({ last_completed_scan: null }) : { scans: [] });
    location.hash = "/program/acme/brief";
    const view = render(<App />);
    expect(await screen.findByText("Chưa có brief")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    view.unmount();
    location.hash = "/program/acme/program";
    render(<App />);
    const box = await screen.findByLabelText(/Ghi chú của bạn/);
    await waitFor(() => expect(box).toHaveValue("old"));
    const save = screen.getByRole("button", { name: "Save instructions" });
    expect(save).toBeDisabled();
    fireEvent.change(box, { target: { value: "Auth: account A" } });
    expect(screen.getByText("Chưa lưu")).toBeInTheDocument();
    fireEvent.click(save);
    await waitFor(() => expect(JSON.parse(calls(fetch, "/program", "PUT")[0][1]!.body as string)).toEqual({ content: "Auth: account A" }));
  });

  test("Scan lại creates a draft and opens Review", async () => {
    const fetch = stubFetch((path) => (path.endsWith("/rescan") ? { scan_id: 33, slug: "acme" } : path === "/api/health" ? health() : path.endsWith("/config") ? baseConfig : path.endsWith("/review") ? baseReview() : path.endsWith("/summary") ? summary() : { scans: [] }));
    location.hash = "/program/acme";
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Scan lại" }));
    await waitFor(() => expect(location.hash).toBe("#/scan/33/review"));
    expect(calls(fetch, "/launch")).toHaveLength(0);
  });
});
