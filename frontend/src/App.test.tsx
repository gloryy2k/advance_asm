import { render, screen, fireEvent, waitFor, act, within } from "@testing-library/react";
import { vi, expect, test, beforeEach, describe } from "vitest";
import { App } from "./App";
import { baseConfig, baseReview, calls, FakeSocket, health, planReply, profilesReply, stubFetch } from "./test-utils";
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
  test("routes: five areas in the URL, legacy tabs and /target still resolve, params survive", () => {
    expect(parseRoute("/program/acme/diff")).toEqual({ page: "program", slug: "acme", tab: "history", view: "diff" });
    expect(parseRoute("/program/acme/assets")).toEqual({ page: "program", slug: "acme", tab: "data", view: "hosts" });
    expect(parseRoute("/program/acme/brief")).toEqual({ page: "program", slug: "acme", tab: "guide", view: "brief" });
    expect(parseRoute("/target/acme")).toEqual({ page: "program", slug: "acme", tab: "overview", view: "" });
    expect(parseRoute("/program/acme/bogus")).toMatchObject({ tab: "overview" });
    expect(parseRoute("/program/acme/data?v=urls&tag=api")).toEqual({ page: "program", slug: "acme", tab: "data", view: "urls" });
    expect(parseRoute("/scan/7/review")).toEqual({ page: "review", id: "7" });
    expect(parseRoute("/scan/7")).toEqual({ page: "run", id: "7" });
    expect(parseRoute("/help")).toEqual({ page: "help" });
    expect(parseRoute("/profiles")).toEqual({ page: "profiles" });
    expect(programPath("a b", "guide", "export")).toBe("/program/a%20b/guide?v=export");
    expect(programPath("acme")).toBe("/program/acme");
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
    expect(screen.getByText(/Mobile — làm tay/)).toBeInTheDocument();
    expect(screen.getByText(/Thiếu công cụ: nuclei/)).toBeInTheDocument();
    expect(screen.getByText(/CHƯA XÁC MINH/, { selector: "strong" })).toBeInTheDocument();  // scope trust is the first thing shown
  });

  test("N2: dump-only H1 data shows source, time and what is missing, and cannot be launched above passive", async () => {
    const dump = baseReview({
      trust: { level: "public", verified: false, label: "CHƯA XÁC MINH — dữ liệu công khai", detail: "Bản sao.", missing: ["policy đầy đủ"], checklist: [], official_url: null },
      policy: { text: "", source: "public_dump", fetched_at: "2026-10-14T01:00:00Z", user_text: "",
        attempts: [{ source: "api", ok: false, reason: "Chưa cấu hình H1_USER/H1_TOKEN" }, { source: "public_page", ok: false, reason: "HTTP 404" }, { source: "public_dump", ok: true }],
        classification: { classified: 2, unclassified_count: 1, unclassified: [{ identifier: "Open Scope", kind: "in", asset_type: "OTHER", reason: "Loại asset không rõ" }] } },
      launch_gate: { allowed_depths: ["passive"], missing: ["nguồn có cấu trúc hiện hành", "policy"], reasons: ["Scope chỉ lấy từ bản sao bounty-targets-data."] },
    });
    const fetch = setup(dump);
    expect(await screen.findByText(/Chưa đủ dữ liệu để chạy Light\/Strong/)).toBeInTheDocument();
    expect(screen.getByText(/Đã thử:/)).toHaveTextContent("Trang công khai ✗ (HTTP 404)");
    expect(screen.getByText(/Bản sao bounty-targets-data \(có thể cũ/)).toBeInTheDocument();
    expect(screen.getByText(/1 asset chưa phân loại — không đưa vào scope gate/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Light/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /Strong/ })).toBeDisabled();
    // The saved config is Light, which this data cannot support: the page starts on Passive instead.
    await waitFor(() => expect(screen.getByRole("radio", { name: /Passive/ })).toHaveAttribute("aria-checked", "true"));
    const launch = screen.getByRole("button", { name: "Launch scan" });
    await waitFor(() => expect(launch).toBeEnabled());
    fireEvent.click(launch);
    await waitFor(() => expect(location.hash).toBe("#/scan/4"));
    expect(JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config.depth).toBe("passive");
  });

  test("N2: public page data is labelled, unverified, and still lets Light proceed after the ack", async () => {
    const page = baseReview({
      trust: { level: "public_page", verified: false, label: "Trang công khai HackerOne — chưa xác minh bằng API", detail: "Đọc chỉ-đọc.", missing: [], checklist: [], official_url: "https://hackerone.com/acme" },
      policy: { text: "Automated scanning allowed, 5 req/s.", source: "public_page", fetched_at: "2026-10-14T01:00:00Z", user_text: "",
        attempts: [{ source: "api", ok: false, reason: "Chưa cấu hình H1_USER/H1_TOKEN" }, { source: "public_page", ok: true }] },
      launch_gate: { allowed_depths: ["passive", "light", "strong"], missing: [], reasons: [] },
    });
    setup(page);
    expect(await screen.findByText(/Trang công khai HackerOne — chưa xác minh bằng API/, { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText(/Đã thử:/)).toHaveTextContent("Trang công khai ✓");
    expect(screen.queryByText(/Chưa đủ dữ liệu để chạy/)).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Light/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Launch scan" })).toBeDisabled();  // still needs the ack
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

  const phaseReport = (over: object[] = [], status = "running") => ({
    scan_id: 9, slug: "acme", status, depth: "light", funnel: { raw: 52, in_scope: 49, out_of_scope: 3, invalid: 0 }, missing_tools: ["nmap"],
    phases: [
      { key: "subdomain_enum", title: "Tìm subdomain", what: "Gom subdomain", touches: false, status: "ran", status_label: "Đã chạy", reason: null, count: 4, count_label: "host",
        files: [{ path: "0/subdomains/all.txt", name: "all.txt", label: "subdomains/all.txt", bytes: 10, lines: 4 }], view: { kind: "hosts", label: "Xem danh sách host" } },
      { key: "port_scan", title: "Quét cổng", what: "nmap", touches: true, status: "skipped", status_label: "Bỏ qua", reason: "Chỉ chạy ở mức Strong", count: 0, count_label: "dòng", files: [], view: { kind: "file", label: "Đọc kết quả nmap" } },
      { key: "nuclei", title: "Nuclei", what: "mẫu", touches: true, status: "empty", status_label: "Chạy — 0 kết quả", reason: "Có chạy nhưng không tìm thấy gì (không có nghĩa là an toàn).", count: 0, count_label: "finding",
        files: [{ path: "0/nuclei/findings.jsonl", name: "findings.jsonl", label: "nuclei/findings.jsonl", bytes: 0, lines: 0 }], view: { kind: "findings", label: "Xem findings", filter: { type: "nuclei" } } },
      ...over,
    ],
  });

  test("each step says what it does, whether it ran, how much it found and where to read it; hunt command when done", async () => {
    let status = "running";
    stubFetch((path) => path.endsWith("/phases") ? phaseReport([], status) : path.endsWith("/review") ? baseReview({ scan: scan(status) }) : path.endsWith("/config") ? baseConfig : scan(status));
    location.hash = "/scan/9";
    render(<App />);
    await screen.findByText("đang chạy");
    const sub = await screen.findByText("Tìm subdomain");
    const row = sub.closest("li")!;
    expect(within(row).getByText("Đã chạy")).toBeInTheDocument();
    expect(within(row).getByText("host")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: /Xem danh sách host/ })).toHaveAttribute("href", "#/program/acme/data?v=hosts");
    const ports = screen.getByText("Quét cổng").closest("li")!;
    expect(within(ports).getByText("Bỏ qua")).toBeInTheDocument();
    expect(within(ports).getByText("Chỉ chạy ở mức Strong")).toBeInTheDocument();
    expect(within(ports).queryByRole("link")).not.toBeInTheDocument();  // nothing to open for a skipped step
    const nuclei = screen.getByText("Nuclei").closest("li")!;
    expect(within(nuclei).getByText(/không có nghĩa là an toàn/)).toBeInTheDocument();  // 0 results is not "safe"
    expect(screen.getByText(/Công cụ không có trên máy chủ: nmap/)).toBeInTheDocument();
    expect(screen.getByText(/52/)).toBeInTheDocument();  // URL funnel
    expect(screen.queryByText(/cd "/)).not.toBeInTheDocument();
    status = "done";
    act(() => FakeSocket.instances[0].emit({ id: 2, type: "done", status: "done" }));
    expect(await screen.findByText('cd "/data/targets/acme" && claude')).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xem Brief" })).toHaveAttribute("href", "#/program/acme/guide?v=brief");
  });

  test("a finished scan shows how long it took, not time since it started", async () => {
    stubFetch((path) => path.endsWith("/phases") ? phaseReport([], "done") : path.endsWith("/review") ? baseReview() : scan("done", { started_at: "2026-10-14T01:00:00Z", finished_at: "2026-10-14T01:04:00Z" }));
    location.hash = "/scan/9";
    render(<App />);
    expect(await screen.findByText(/Mất 4 phút/)).toBeInTheDocument();
  });

  test("raw output opens in a viewer: paged, searchable; secrets stay hidden until asked", async () => {
    const fetch = stubFetch((path) => {
      if (path.endsWith("/phases")) return phaseReport([{
        key: "secrets", title: "Bí mật trong JS", what: "quét", touches: true, status: "ran", status_label: "Đã chạy", reason: null, count: 1, count_label: "dấu vết",
        files: [{ path: "monitors/secret/trufflehog.jsonl", name: "trufflehog.jsonl", label: "monitors/secret/trufflehog.jsonl", bytes: 50, lines: 1 }],
        view: { kind: "findings", label: "Xem findings", filter: { type: "secret" } } }], "done");
      if (path.includes("/artifact?")) {
        const reveal = path.includes("reveal=true");
        return { path: "monitors/secret/trufflehog.jsonl", name: "trufflehog.jsonl", total: 1, offset: 0, limit: 100, filtered: false, redacted: !reveal,
          lines: [reveal ? '{"Raw":"AKIA-REAL"}' : '{"Raw":"[ẩn]"}'] };
      }
      return path.endsWith("/review") ? baseReview() : scan("done");
    });
    location.hash = "/scan/9";
    render(<App />);
    const row = (await screen.findByText("Bí mật trong JS")).closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: /Đọc file thô/ }));
    const dialog = await screen.findByRole("dialog", { name: /Bí mật trong JS/ });
    expect(await within(dialog).findByText(/\[ẩn\]/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Giá trị bí mật đang bị ẩn/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: /Tải file/ })).toHaveAttribute("href", expect.stringContaining("/artifact/download?path=monitors%2Fsecret%2Ftrufflehog.jsonl"));
    fireEvent.change(within(dialog).getByLabelText("Tìm trong file"), { target: { value: "akia" } });
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("q=akia"))).toBe(true));
    fireEvent.click(within(dialog).getByLabelText(/Hiện giá trị/));
    expect(await within(dialog).findByText(/AKIA-REAL/)).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
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
    expect(screen.getByRole("tab", { name: "Lịch sử" })).toHaveAttribute("href", "#/program/acme/history");
    expect(screen.getByRole("tab", { name: "Tổng quan" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("tab")).toHaveLength(5);  // five areas, not seven tabs
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


const urlRow = (over: object = {}) => ({ id: 1, url: "https://acme.com/api/v1/users?id=3", host: "acme.com", source: "katana", score: 5, verification: "observed",
  shape: "/api/v1/users", tags: ["api", "params", "id-param"], is_new: true, first_seen_scan: 2, ...over });
const urlSummary = () => ({ scan_id: 2, total: 49, funnel: { raw: 52, in_scope: 49, out_of_scope: 3, invalid: 0, excluded_by_rule: 2, out_of_scope_hosts: [{ host: "cdn.evil.test", count: 3 }] },
  by_tag: { api: 3, auth: 1, params: 8, js: 1 }, top_shapes: [{ shape: "/product/*", count: 39, max_score: 0.5, example: "https://acme.com/product/1" }, { shape: "/api/v1/users", count: 1, max_score: 5, example: "x" }], hosts: [] });

describe("Data: URL & endpoint explorer", () => {
  test("shows the funnel, hides plain pages by default and says how many, filters by tag/shape/source, exports", async () => {
    const fetch = stubFetch((path) => {
      if (path.includes("/urls/summary")) return urlSummary();
      if (path.includes("/urls?")) return { __total: path.includes("min_score=0") ? 49 : 10, body: [urlRow(), urlRow({ id: 2, url: "https://acme.com/login", verification: "historical", source: "gau", tags: ["auth"], score: 2.5, is_new: false })] };
      if (path.endsWith("/summary")) return {};
      return {};
    });
    location.hash = "/program/acme/data?v=urls";
    render(<App />);
    expect(await screen.findByText("https://acme.com/api/v1/users?id=3")).toBeInTheDocument();
    const funnel = screen.getByLabelText("Phễu URL");
    expect(within(funnel).getByText("52")).toBeInTheDocument();
    expect(within(funnel).getByText("49")).toBeInTheDocument();
    expect(within(funnel).getByText("3")).toBeInTheDocument();
    expect(screen.getByText(/cdn.evil.test \(3\)/)).toBeInTheDocument();
    expect(screen.getByText(/URL từ archive|URL lấy từ archive/)).toBeInTheDocument();
    expect(screen.getByText("đã crawl", { selector: ".chip" })).toBeInTheDocument();  // katana-seen is stronger than history
    expect(screen.getAllByText("lịch sử").length).toBeGreaterThan(0);
    expect(await screen.findByText(/Đang ẩn/)).toHaveTextContent("39");
    expect(fetch.mock.calls.some((c) => String(c[0]).includes("min_score=1"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Hiện tất cả" }));
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("min_score=0"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: /API\s*3/, pressed: false }));
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("tag=api"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: /\/product\/\*/ }));
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("shape=%2Fproduct%2F*"))).toBe(true));
    fireEvent.change(screen.getByLabelText("Mức kiểm chứng"), { target: { value: "historical" } });
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("verification=historical"))).toBe(true));
    const href = screen.getByRole("link", { name: /Tải danh sách/ }).getAttribute("href")!;
    expect(href).toContain("/urls/export?");
    expect(href).toContain("tag=api");
    expect(href).toContain("verification=historical");
    fireEvent.click(screen.getByRole("button", { name: /Bỏ lọc/ }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Bỏ lọc/ })).not.toBeInTheDocument());
  });

  test("overview points at the URLs worth a look and counts what the scope gate dropped", async () => {
    stubFetch((path) => path.includes("/urls/summary") ? urlSummary() : path.endsWith("/summary") ? { ...programSummary(), trust: { level: "public", verified: false, label: "CHƯA XÁC MINH — dữ liệu công khai", detail: "", missing: [], checklist: [], official_url: null } } : { scans: [] });
    location.hash = "/program/acme";
    render(<App />);
    expect(await screen.findByText(/Xem URL đáng chú ý: API 3 · đăng nhập 1/)).toHaveAttribute("href", "#/program/acme/data?v=urls&min_score=3");
    const tile = screen.getByText("URL", { selector: ".tile-label" }).closest("a")!;
    expect(tile).toHaveTextContent("49");
    expect(tile).toHaveTextContent("3 ngoài scope đã loại");
    expect(screen.getByText(/Đối chiếu scope và policy/)).toBeInTheDocument();
  });
});

const programSummary = () => ({
  slug: "acme", source: "h1", handle: "acme", target_path: "/t/acme", hunt_command: 'cd "targets/acme" && claude', hunt_note: "",
  latest_scan: { id: 2, status: "done", depth: "light" }, last_completed_scan: { id: 2, status: "done", depth: "light", baseline_scan_id: 1 },
  changes: { new: 4, changed: 1, gone: 0 }, findings_by_severity: { critical: 1, high: 0, medium: 2, low: 0, info: 0 }, assets_active: 12,
  top_surface: [], draft_count: 0, schedule: null, default_profile_id: null,
});

describe("Guide, history, help", () => {
  test("history names the scan it compares against and lists scans with results", async () => {
    stubFetch((path) => path.includes("/diff") ? { __total: 0, body: [] } : path.endsWith("/summary") ? programSummary() : { scans: [{ id: 2, depth: "light", status: "done", stats: { observed: 5, subs: 3, urls: 1200, findings: 2 }, finished_at: "2026-10-14T08:00:00Z" }] });
    location.hash = "/program/acme/history?v=scans";
    const view = render(<App />);
    const row = (await screen.findByText("#2")).closest("tr")!;
    expect(within(row).getByText(/3 host · 1\.200 URL · 2 finding/)).toBeInTheDocument();
    view.unmount();
    location.hash = "/program/acme/history?v=diff";
    render(<App />);
    expect(await screen.findByText(/so với scan hoàn tất gần nhất trước đó \(#1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Scan bị huỷ hoặc lỗi không dùng làm mốc/)).toBeInTheDocument();
  });

  test("export offers three modes and recommends the scope-filtered one", async () => {
    stubFetch((path) => path.endsWith("/summary") ? programSummary() : { scans: [] });
    location.hash = "/program/acme/guide?v=export";
    render(<App />);
    expect(await screen.findByText("Đã lọc scope (khuyến nghị)")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "Tải ZIP ↓" }).map((a) => a.getAttribute("href"));
    expect(links).toEqual(["/api/programs/acme/export?mode=filtered", "/api/programs/acme/export?mode=brief", "/api/programs/acme/export?mode=full"]);
    expect(screen.getByText(/CÓ THỂ chứa URL\/host ngoài scope/)).toBeInTheDocument();
  });

  test("scope & policy shows trust, scope lists and lets you pick the default profile", async () => {
    const fetch = stubFetch((path, init) => {
      if (path.endsWith("/default-profile")) return { slug: "acme", default_profile_id: 7 };
      if (path === "/api/profiles") return profilesReply([{ id: 7, name: "Nhanh", description: "", based_on: "light", builtin: false, config: {} }]);
      if (path.endsWith("/summary")) return { ...programSummary(), trust: { level: "public", verified: false, label: "CHƯA XÁC MINH — dữ liệu công khai", detail: "cũ", missing: ["policy đầy đủ"], checklist: ["Mở trang chính thức"], official_url: "https://hackerone.com/acme" } };
      return { scans: [], scope: [{ id: 1, pattern: "*.acme.com", kind: "in", asset_type: "wildcard" }, { id: 2, pattern: "legacy.acme.com", kind: "out", asset_type: "url" }], policy: { policy_text: "No DoS" } };
    });
    location.hash = "/program/acme/guide?v=scope";
    render(<App />);
    expect(await screen.findByText("*.acme.com")).toBeInTheDocument();
    expect(screen.getByText("legacy.acme.com")).toBeInTheDocument();
    expect(screen.getByText("No DoS")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Mở trang chính thức/ })).toHaveAttribute("href", "https://hackerone.com/acme");
    fireEvent.change(await screen.findByRole("combobox", { name: "Profile mặc định" }), { target: { value: "7" } });
    await waitFor(() => expect(JSON.parse(calls(fetch, "/default-profile", "PUT")[0][1]!.body as string)).toEqual({ profile_id: 7 }));
  });

  test("Help lists every step with what it does and where to read it", async () => {
    stubFetch((path) => path === "/api/meta/phases" ? [
      { key: "url_crawl", title: "Crawl chủ động", what: "katana đi theo liên kết", touches: true, tools: ["katana"], count_label: "URL", view: { kind: "urls", label: "Xem URL" }, files: [] },
      { key: "subdomain_enum", title: "Tìm subdomain", what: "Gom subdomain công khai", touches: false, tools: ["subfinder"], count_label: "host", view: { kind: "hosts", label: "Xem host" }, files: [] }] : {});
    location.hash = "/help";
    render(<App />);
    const row = (await screen.findByText("Crawl chủ động")).closest("tr")!;
    expect(within(row).getByText("katana đi theo liên kết")).toBeInTheDocument();
    expect(within(row).getByText("Có")).toBeInTheDocument();
    expect(within(row).getByText("Dữ liệu › URL & endpoint")).toBeInTheDocument();
    expect(screen.getByText("Tìm subdomain").closest("tr")).toHaveTextContent("Không");
    expect(screen.getByText(/0 kết quả/, { selector: "dt" })).toBeInTheDocument();  // glossary: 0 results != safe
  });
});

describe("Customisation: steps, profiles, defaults", () => {
  function review(over: Record<string, object> = {}) {
    const fetch = stubFetch((path, init) => {
      if (path === "/api/health") return health();
      if (path.endsWith("/review")) return baseReview();
      if (path.endsWith("/config")) return baseConfig;
      if (path.endsWith("/launch")) return { scan_id: 4, status: "queued" };
      if (path === "/api/meta/plan") return planReply((over.plan as any) || {});
      if (path === "/api/profiles" && init?.method === "POST") return { id: 9, name: "Nhanh", description: "", based_on: "light", builtin: false, config: JSON.parse(init.body as string).config };
      if (path.endsWith("/default-profile")) return { slug: "acme", default_profile_id: 9 };
      return undefined as any;
    });
    location.hash = "/scan/4/review";
    render(<App />);
    return fetch;
  }

  test("every step shows what it does, whether it touches the target and where its output lives; toggles change the launched config", async () => {
    const fetch = review({ plan: { nuclei: { status: "missing_tool", reason: "Thiếu nuclei — bước này sẽ bị bỏ qua." }, port_scan: { status: "off", reason: "Chỉ chạy ở mức Strong" } } });
    const nuclei = (await screen.findByText("Nuclei", { selector: "strong" })).closest("li")!;
    expect(within(nuclei).getByText("mô tả Nuclei")).toBeInTheDocument();
    expect(within(nuclei).getByText("chạm target")).toBeInTheDocument();
    expect(within(nuclei).getByText(/Kết quả: Xem Nuclei/)).toBeInTheDocument();
    expect(within(nuclei).getByText("Thiếu công cụ")).toBeInTheDocument();
    const subdomain = screen.getByText("Tìm subdomain", { selector: "strong" }).closest("li")!;
    expect(within(subdomain).getByText("không chạm target")).toBeInTheDocument();
    const ports = screen.getByText("Quét cổng", { selector: "strong" }).closest("li")!;
    expect(within(ports).getByLabelText("Chạy: Quét cổng")).toBeDisabled();  // forced off by the preset, not by the user
    fireEvent.click(within(nuclei).getByLabelText("Chạy: Nuclei"));
    fireEvent.click(screen.getByLabelText(/Tôi đã đọc policy/));
    await waitFor(() => expect(calls(fetch, "/api/meta/plan").length).toBeGreaterThan(1));  // plan is recomputed from the new config
    fireEvent.click(screen.getByRole("button", { name: "Launch scan" }));
    await waitFor(() => expect(calls(fetch, "/launch")).toHaveLength(1));
    const config = JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config;
    expect(config.skip_nuclei).toBe(true);
    expect(config.skip_nmap).toBe(true);
  });

  test("changing values shows what differs from the preset and lets you reset", async () => {
    review();
    await screen.findByText(/Đang đúng theo preset Light/);
    fireEvent.click(screen.getByText(/Tuỳ chỉnh chi tiết/));
    fireEvent.change(screen.getByLabelText(/^Số luồng/), { target: { value: "120" } });
    fireEvent.change(screen.getByLabelText("Số URL trong brief"), { target: { value: "5" } });
    const line = await screen.findByText(/Khác preset Light/);
    expect(line).toHaveTextContent("2 mục");
    expect(line).toHaveTextContent("số luồng");
    expect(line).toHaveTextContent("số URL trong brief");
    fireEvent.change(screen.getByLabelText(/Đường dẫn KHÔNG đưa vào kết quả/), { target: { value: "/internal/*\n  \n/admin/*" } });
    expect(await screen.findByText(/3 mục/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "↺ Đặt lại" }));
    await screen.findByText(/Đang đúng theo preset Light/);
    expect((screen.getByLabelText(/^Số luồng/) as HTMLInputElement).value).toBe("50");
  });

  test("save the current setup as a profile (optionally the program default) and the recipe excludes scope", async () => {
    const fetch = review();
    fireEvent.click(await screen.findByText(/Tuỳ chỉnh chi tiết/));
    fireEvent.change(screen.getByLabelText(/^Số luồng/), { target: { value: "120" } });
    fireEvent.click(screen.getByRole("button", { name: /Lưu cấu hình này thành profile/ }));
    fireEvent.change(screen.getByLabelText("Tên profile"), { target: { value: "Nhanh" } });
    fireEvent.click(screen.getByLabelText(/Mặc định cho program này/));
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(calls(fetch, "/default-profile", "PUT")).toHaveLength(1));
    const body = JSON.parse(calls(fetch, "/api/profiles", "POST")[0][1]!.body as string);
    expect(body).toMatchObject({ name: "Nhanh", based_on: "light", config: { threads: 120, depth: "light" } });
    expect(body.config).not.toHaveProperty("categories_enabled");  // a profile is how to scan, never what
    expect(body.config).not.toHaveProperty("excluded_hosts");
    expect(JSON.parse(calls(fetch, "/default-profile", "PUT")[0][1]!.body as string)).toEqual({ profile_id: 9 });
  });

  test("picking a saved profile applies its recipe but keeps this scan's scope choices", async () => {
    const mine = { id: 5, name: "Chỉ passive nhẹ", description: "", based_on: "passive", builtin: false, config: { ...profilesReply().builtin[0].config, threads: 7, skip_historical: true } };
    const fetch = stubFetch((path) => path === "/api/profiles" ? profilesReply([mine]) : path === "/api/health" ? health() : path.endsWith("/review") ? baseReview() : path.endsWith("/config") ? baseConfig : path.endsWith("/launch") ? { status: "queued" } : undefined as any);
    location.hash = "/scan/4/review";
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Profile của tôi"), { target: { value: "5" } });
    expect(await screen.findByText(/Đang đúng theo preset Chỉ passive nhẹ/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Tôi đã đọc policy/)).not.toBeInTheDocument();  // passive: no automation ack
    fireEvent.click(screen.getByRole("button", { name: "Launch scan" }));
    await waitFor(() => expect(calls(fetch, "/launch")).toHaveLength(1));
    const config = JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config;
    expect(config).toMatchObject({ depth: "passive", threads: 7, skip_historical: true, categories_enabled: ["web", "wildcard"] });
  });
});

describe("Profiles page", () => {
  test("create, duplicate and delete a profile; presets are read-only starting points", async () => {
    let custom: any[] = [{ id: 3, name: "Nhanh", description: "mô tả", based_on: "light", builtin: false, config: profilesReply().builtin[1].config }];
    const fetch = stubFetch((path, init) => {
      if (path === "/api/profiles" && init?.method === "POST") { custom = [...custom, { id: 4, name: "Mới", description: "", based_on: "light", builtin: false, config: {} }]; return custom[1]; }
      if (path === "/api/profiles") return profilesReply(custom);
      if (path.endsWith("/duplicate")) return { id: 8 };
      if (init?.method === "DELETE") { custom = []; return { deleted: 3 }; }
      return undefined as any;
    });
    vi.stubGlobal("confirm", () => true);
    location.hash = "/profiles";
    render(<App />);
    const row = (await screen.findByText("Nhanh", { selector: "strong" })).closest("li")!;
    expect(row).toHaveTextContent("light · 50 luồng · 150 req/s");
    fireEvent.click(within(row).getByRole("button", { name: "Nhân bản" }));
    await waitFor(() => expect(calls(fetch, "/duplicate", "POST")).toHaveLength(1));
    fireEvent.click(screen.getAllByRole("button", { name: "+ Tạo profile" })[0]);
    const save = await screen.findByRole("button", { name: "Lưu profile" });
    expect(save).toBeDisabled();  // a name is required
    fireEvent.change(screen.getByLabelText("Tên profile"), { target: { value: "Mới" } });
    fireEvent.click(await screen.findByText(/Tuỳ chỉnh chi tiết/));
    fireEvent.change(screen.getByLabelText(/^Số luồng/), { target: { value: "99" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu profile" }));
    await waitFor(() => expect(JSON.parse(calls(fetch, "/api/profiles", "POST")[0][1]!.body as string).config.threads).toBe(99));
    fireEvent.click((await screen.findAllByRole("button", { name: "Xoá" }))[0]);
    await waitFor(() => expect(calls(fetch, "/api/profiles/3", "DELETE")).toHaveLength(1));
    expect(await screen.findByText("Chưa có profile nào")).toBeInTheDocument();
  });
});
