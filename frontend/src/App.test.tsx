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

  test("nuclei auto-select (-as) toggle and the by-tag lookup preview", async () => {
    const fetch = stubFetch((path, init) => {
      if (path === "/api/health") return health();
      if (path.endsWith("/review")) return baseReview();
      if (path.endsWith("/config")) return baseConfig;
      if (path.includes("/templates/lookup")) {
        const tag = new URL(path, "http://x").searchParams.get("tag");
        return tag === "wordpress" ? { tag: "wordpress", total: 2, truncated: false,
          templates: [{ path: "http/technologies/wordpress/wp-login.yaml", name: "WordPress Login Page", severity: "info" }] }
          : { tag, total: 0, templates: [], truncated: false };
      }
      return {};
    });
    location.hash = "/scan/4/review";
    render(<App />);
    fireEvent.click(await screen.findByText(/Tra cứu template theo công nghệ/));
    const toggle = screen.getByLabelText(/Tự chọn thêm template theo công nghệ phát hiện được/) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    fireEvent.click(toggle);
    expect(toggle.checked).toBe(true);
    fireEvent.change(screen.getByLabelText("Tag cần tra"), { target: { value: "wordpress" } });
    fireEvent.click(screen.getByRole("button", { name: "Tra cứu" }));
    expect(await screen.findByTestId("lookup-total")).toHaveTextContent('2 template gắn tag "wordpress"');
    expect(screen.getByText("WordPress Login Page")).toBeInTheDocument();
    expect(screen.getByText("http/technologies/wordpress/wp-login.yaml")).toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("/templates/lookup?") && String(c[0]).includes("tag=wordpress"))).toBe(true));
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
        attempts: [{ source: "api", ok: false, reason: "Chưa cấu hình H1_USER/H1_TOKEN" }, { source: "public_page", ok: true }],
        completeness: { in: { fetched: 19, total: 19 }, out: { fetched: 25, total: 25 } } },
      launch_gate: { allowed_depths: ["passive", "light", "strong"], missing: [], reasons: [] },
    });
    setup(page);
    expect(await screen.findByText(/Trang công khai HackerOne — chưa xác minh bằng API/, { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText(/Đã thử:/)).toHaveTextContent("Trang công khai ✓");
    expect(screen.queryByText(/Chưa đủ dữ liệu để chạy/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Đối chiếu số lượng asset")).toHaveTextContent("IN 19/19 · OUT 25/25 ✓");
    expect(screen.getByTestId("gate-note")).toHaveTextContent("không phải policy đã cho phép quét tự động");
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
    expect(launch).toBeDisabled();   // ffuf would guess paths: the policy must be confirmed separately (or the step switched off)
    expect(screen.getAllByRole("status").some((n) => /dò thư mục bằng ffuf/.test(n.textContent || ""))).toBe(true);
    fireEvent.click(screen.getByLabelText(/xác nhận policy cho phép dò thư mục/));
    expect(launch).toBeEnabled();
    fireEvent.click(launch);
    await waitFor(() => expect(calls(fetch, "/launch")).toHaveLength(1));
    const config = JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config;
    expect(config).toMatchObject({ depth: "strong", skip_nmap: false, scan_timeout: 2700, nuclei_severity: "low,medium,high,critical", ffuf_confirmed: true });
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
    fireEvent.click(await screen.findByLabelText(/Tôi đã đọc policy và program cho phép/));
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
    fireEvent.click(await screen.findByLabelText(/Tôi đã đọc policy và program cho phép/));
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
    expect(screen.getByText("52", { selector: "strong" })).toBeInTheDocument();  // URL funnel
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
    stubFetch((path) => (path.split("?")[0] === "/api/programs" ? [card()] : path === "/api/drafts" ? [] : health()));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "acme" })).toBeInTheDocument();
    expect(screen.getByText("+3 NEW")).toBeInTheDocument();
    expect(screen.getByText(/Chưa bật monitoring/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /acme/ })).toHaveAttribute("href", "#/program/acme");
  });

  test("empty state explains the 3 steps and offers the first action", async () => {
    stubFetch((path) => (path.split("?")[0] === "/api/programs" || path === "/api/drafts" ? [] : health()));
    render(<App />);
    expect(await screen.findByText("Chưa có program nào")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Thêm program đầu tiên" })).toHaveAttribute("href", "#/new");
  });

  test("drafts can be resumed or deleted", async () => {
    let drafts: object[] = [{ id: 5, slug: "x", source: "raw", depth: "light", created_at: null, in: 2, out: 1 }];
    const fetch = stubFetch((path, init) => {
      if (init?.method === "DELETE") { drafts = []; return { deleted: 5 }; }
      return path.split("?")[0] === "/api/programs" ? [] : path === "/api/drafts" ? drafts : health();
    });
    vi.stubGlobal("confirm", () => true);
    render(<App />);
    expect(await screen.findByRole("link", { name: "Tiếp tục review" })).toHaveAttribute("href", "#/scan/5/review");
    fireEvent.click(screen.getByRole("button", { name: "Xoá" }));
    await waitFor(() => expect(calls(fetch, "/api/scans/5", "DELETE")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText(/Bản nháp chờ review/)).not.toBeInTheDocument());
  });

  test("API failure shows an error with retry", async () => {
    stubFetch((path) => (path.split("?")[0] === "/api/programs" ? { __error: { status: 500, message: "boom" } } : path === "/api/drafts" ? [] : health()));
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
    expect(JSON.parse(calls(fetch, "/schedule")[0][1]!.body as string)).toEqual({ interval: "weekly", depth: "light", enabled: true, automation_ack: true, skipped_headers: [] });
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

describe("v1.3: policy header, OUT paths, stages and coverage", () => {
  const withHint = () => baseReview({
    request_header_hints: ["X-HackerOne-Research"],
    scope: [
      { pattern: "*.wolt.com", kind: "in", asset_type: "WILDCARD", category: "wildcard", instruction: "" },
      { pattern: "https://wolt.com/en/wolt-for-work-contact-request", kind: "out", asset_type: "URL", category: "web", instruction: "" },
    ],
  });
  const reviewStub = (review: object) => stubFetch((path) =>
    path === "/api/health" ? health() : path.endsWith("/review") ? review : path.endsWith("/config") ? baseConfig
      : path.endsWith("/launch") ? { scan_id: 4, status: "queued" } : path.endsWith("/request-headers") ? { headers: [] } : {});

  test("a header the policy asks for blocks Light until it is filled in or knowingly skipped; the value is sent with the config only", async () => {
    const fetch = reviewStub(withHint());
    location.hash = "/scan/4/review";
    render(<App />);
    fireEvent.click(await screen.findByLabelText(/Tôi đã đọc policy và program cho phép/));
    const launch = screen.getByRole("button", { name: "Launch scan" });
    expect(launch).toBeDisabled();
    expect(screen.getAllByRole("status").some((n) => /Policy yêu cầu header X-HackerOne-Research/.test(n.textContent || ""))).toBe(true);
    fireEvent.change(screen.getByLabelText("Header gửi kèm"), { target: { value: "X-HackerOne-Research: tester-4711" } });
    await waitFor(() => expect(launch).toBeEnabled());
    fireEvent.click(screen.getByLabelText(/Dùng làm mặc định cho program/));
    fireEvent.click(launch);
    await waitFor(() => expect(location.hash).toBe("#/scan/4"));
    expect(JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config.request_headers).toEqual(["X-HackerOne-Research: tester-4711"]);
    await waitFor(() => expect(calls(fetch, "/request-headers", "PUT")).toHaveLength(1));
  });

  test("an invalid header is named, and skipping the hint is an explicit choice", async () => {
    reviewStub(withHint());
    location.hash = "/scan/4/review";
    render(<App />);
    fireEvent.click(await screen.findByLabelText(/Tôi đã đọc policy và program cho phép/));
    fireEvent.click(screen.getByLabelText(/không dùng header X-HackerOne-Research/));
    const launch = screen.getByRole("button", { name: "Launch scan" });
    await waitFor(() => expect(launch).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Header gửi kèm"), { target: { value: "Cookie ngu" } });
    await waitFor(() => expect(launch).toBeDisabled());
    expect(screen.getAllByRole("status").some((n) => /Header không hợp lệ/.test(n.textContent || ""))).toBe(true);
  });

  test("a skipped header stored in the draft shows as confirmed after reload, and edits are saved to the draft", async () => {
    const fetch = stubFetch((path, init) =>
      path === "/api/health" ? health() : path.endsWith("/review") ? withHint()
        : path.endsWith("/config") ? { ...baseConfig, skipped_headers: ["X-HackerOne-Research"] }
          : path.endsWith("/launch") ? { scan_id: 4, status: "queued" } : {});
    location.hash = "/scan/4/review";
    render(<App />);
    fireEvent.click(await screen.findByLabelText(/Tôi đã đọc policy và program cho phép/));
    const skip = screen.getByLabelText(/không dùng header X-HackerOne-Research/) as HTMLInputElement;
    expect(skip.checked).toBe(true);
    expect(screen.getByRole("button", { name: "Launch scan" })).toBeEnabled();
    fireEvent.click(skip);   // withdraw the confirmation: blocked again, and the draft remembers it
    await waitFor(() => expect(screen.getByRole("button", { name: "Launch scan" })).toBeDisabled());
    await waitFor(() => expect(JSON.parse(calls(fetch, "/config", "PUT")[0][1]!.body as string).skipped_headers).toEqual([]));
  });

  test("OUT URLs with a path are listed as path rules, hosts are probe-only unless the user opts in", async () => {
    const fetch = reviewStub(withHint());
    location.hash = "/scan/4/review";
    render(<App />);
    const panel = (await screen.findByText("OUT theo đường dẫn", { selector: "h2" })).closest("section")!;
    expect(within(panel).getByText("https://wolt.com/en/wolt-for-work-contact-request")).toBeInTheDocument();
    expect(within(panel).getByText(/chỉ probe/)).toHaveTextContent("wolt.com");
    fireEvent.click(within(panel).getByLabelText(/Cho phép quét chủ động các host này/));
    fireEvent.click(await screen.findByLabelText(/Tôi đã đọc policy và program cho phép/));
    fireEvent.click(screen.getByLabelText(/không dùng header X-HackerOne-Research/));
    fireEvent.click(screen.getByRole("button", { name: "Launch scan" }));
    await waitFor(() => expect(location.hash).toBe("#/scan/4"));
    expect(JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config.allow_active_on_path_rules).toBe(true);
  });

  test("Run shows stages, discovered/probed/unprobed, failed sources and why, and says unprobed hosts are not 'gone'", async () => {
    stubFetch((path) => path.endsWith("/phases")
      ? { scan_id: 31, slug: "wolt", status: "done_partial", depth: "light", phases: [], funnel: { raw: 4422, in_scope: 223, out_of_scope: 75, invalid: 17, path_rule_blocked: 4107 },
          missing_tools: [], coverage: { discovered: 720, probed: 4, unprobed: 716, explicit: 4, batches: 5, batches_done: 0 },
          stages: [{ key: "discovery", label: "Khám phá subdomain/URL", status: "ok", budget_s: 270, used_s: 190, commands: 1 },
                   { key: "probe", label: "Probe host đã khám phá", status: "timeout", budget_s: 270, used_s: 270, commands: 5 }],
          sources: [{ source: "web.archive.org", status: "timeout", seconds: 45 }], partial_inputs: [], path_rule_hosts: { "wolt.com": ["/en/x"] },
          tool_notes: [{ tool: "katana", note: "known-files (robots.txt, sitemap.xml) tắt: katana không gắn header của policy vào các request này" }] }
      : path.endsWith("/review") ? baseReview({ scan: { id: 31, depth: "light", status: "done_partial" } })
      : path.endsWith("/config") ? baseConfig
      : { id: 31, depth: "light", status: "done_partial", started_at: "2026-10-15T02:11:56Z", finished_at: "2026-10-15T02:27:45Z", error: "Giai đoạn 'Probe host đã khám phá' hết ngân sách 270s (timeout)" });
    location.hash = "/scan/31";
    render(<App />);
    const coverage = await screen.findByLabelText("Phủ host khám phá");
    expect(coverage).toHaveTextContent("720");
    expect(coverage).toHaveTextContent(/chưa probe\s*716/);
    expect(coverage).toHaveTextContent("không bị coi là đã biến mất");
    const probe = document.querySelector("tr[data-stage=\"probe\"]") as HTMLElement;
    expect(within(probe).getByText("hết thời gian")).toBeInTheDocument();
    expect(within(probe).getByText("270s / 270s")).toBeInTheDocument();
    expect(screen.getByText("web.archive.org").closest("p")).toHaveTextContent("web.archive.org quá thời gian sau 45s");
    expect(screen.getByTestId("partial-reason")).toHaveTextContent("hết ngân sách");
    expect(screen.getByText(/chặn theo OUT đường dẫn/)).toBeInTheDocument();
    expect(screen.getByTestId("tool-note")).toHaveTextContent("katana: known-files");
  });

  test("Program overview tells a running scan apart from the finished data it still shows", async () => {
    const done = { id: 28, depth: "light", status: "done_partial", finished_at: "2026-10-15T02:27:45Z",
      stats: { coverage: { discovered: 720, probed: 4, unprobed: 716 }, stages: [], sources: [] } };
    stubFetch((path) => path.endsWith("/summary")
      ? { slug: "wolt", source: "h1", handle: "wolt", target_path: "/t/wolt", hunt_command: "cd t && claude", hunt_note: "", latest_scan: { id: 32, depth: "light", status: "running" },
          last_completed_scan: done, changes: { new: 0, changed: 0, gone: 0 }, findings_by_severity: {}, assets_active: 5, top_surface: [], draft_count: 0, schedule: null }
      : {});
    location.hash = "/program/wolt";
    render(<App />);
    const banner = await screen.findByTestId("data-scan");
    expect(banner).toHaveTextContent("Scan #32 (light) đang chạy");
    expect(banner).toHaveTextContent("số liệu dưới đây vẫn là của scan #28");
    expect(banner).toHaveTextContent("hoàn tất MỘT PHẦN");
    expect(banner).toHaveTextContent("716 host khám phá chưa probe");
  });

  test("log lines carry why a step did not run: by configuration, missing tool or timeout", async () => {
    vi.stubGlobal("WebSocket", FakeSocket);
    stubFetch((path) => path.endsWith("/phases") ? { scan_id: 9, slug: "acme", status: "running", depth: "light", phases: [], funnel: null, missing_tools: [] }
      : path.endsWith("/review") ? baseReview({ scan: { id: 9, depth: "light", status: "running" } }) : path.endsWith("/config") ? baseConfig
      : { id: 9, depth: "light", status: "running", started_at: "2026-10-15T02:11:56Z" });
    location.hash = "/scan/9";
    render(<App />);
    await screen.findByText("Nhật ký scan");
    await waitFor(() => expect(FakeSocket.instances.length).toBeGreaterThan(0));
    act(() => {
      FakeSocket.instances[0].emit({ id: 1, type: "log", tag: "skipped_config", message: "[!] Dò thư mục (ffuf): bỏ qua theo mức quét — chỉ chạy ở Strong" });
      FakeSocket.instances[0].emit({ id: 2, type: "log", tag: "timeout", message: "Nguồn web.archive.org quá thời gian sau 45s" });
      FakeSocket.instances[0].emit({ id: 3, type: "stage", status: "running", message: "▶ Probe host đã khám phá: 5 lệnh, tối đa 270s" });
    });
    expect(await screen.findByText("bỏ qua theo mức quét", { selector: "span.chip" })).toBeInTheDocument();
    expect(screen.getByText("quá thời gian", { selector: "span.chip" })).toBeInTheDocument();
    expect(screen.getByText(/▶ Probe host đã khám phá/)).toBeInTheDocument();
  });
});


describe("UI/logic audit fixes (V134_UI_LOGIC_AUDIT)", () => {
  const sum = (over: object = {}) => ({ ...programSummary(), request_header_hints: [], request_headers: [], assets_live: 4, assets_gone: 0, ...over });

  test("UI-1: when the newest scan has no URLs but history does, say so and offer the history instead of 'no URLs'", async () => {
    const fetch = stubFetch((path) => {
      if (path.includes("/urls/summary")) return { ...urlSummary(), total: path.includes("scan=all") ? 49 : 0, history_total: 49, latest: { id: 59, depth: "passive", status: "done", finished_at: "2026-10-16T01:00:00Z" } };
      if (path.includes("/urls?")) return path.includes("scan=all") ? { __total: 49, body: [urlRow({ first_seen_scan: 31, last_seen_scan: 31 })] } : { __total: 0, body: [] };
      return {};
    });
    location.hash = "/program/acme/data?v=urls";
    render(<App />);
    expect(await screen.findByTestId("url-history-cta")).toHaveTextContent(/#59.*không thu được URL.*49/);
    expect(screen.queryByText("Chưa có URL: scan chưa thu thập URL, hoặc chưa có scan hoàn tất.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Xem URL lịch sử/ }));
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("/urls?") && String(c[0]).includes("scan=all"))).toBe(true));
    expect(await screen.findByText("#31")).toBeInTheDocument();   // each row says which scan saw it
    expect(screen.getByTestId("url-scope-note")).toHaveTextContent(/Mọi URL đã ghi nhận qua các scan/);
    expect(screen.getByRole("link", { name: /Tải danh sách/ }).getAttribute("href")).toContain("scan=all");
  });

  test("UI-2: an older Run links to URLs 'as of that scan' and says it is not the program's current view", async () => {
    stubFetch((path) => {
      if (path.endsWith("/summary")) return sum({ last_completed_scan: { id: 59, status: "done", depth: "passive" } });
      if (path.endsWith("/phases")) return { scan_id: 31, slug: "acme", status: "done", depth: "light", missing_tools: [], funnel: null,
        phases: [{ key: "url_history", title: "URL lịch sử", what: "x", touches: false, status: "ran", status_label: "Đã chạy", reason: null, count: 4667, count_label: "URL thô", files: [],
          view: { kind: "urls", label: "Xem URL đã lọc scope" } }] };
      if (path.endsWith("/review")) return baseReview({ scan: { id: 31, depth: "light", status: "done" } });
      return { id: 31, program_id: 1, depth: "light", status: "done", started_at: "2026-10-14T01:00:00Z", finished_at: "2026-10-14T01:04:00Z", error: null };
    });
    location.hash = "/scan/31";
    render(<App />);
    expect(await screen.findByTestId("older-scan-note")).toHaveTextContent(/#31 không phải scan mới nhất.*#59/);
    expect(screen.getByRole("link", { name: /Xem URL đã lọc scope/ }).getAttribute("href")).toContain("scan=31");
    expect(screen.getByRole("link", { name: /Xem Brief hiện hành \(scan #59\)/ })).toBeInTheDocument();
  });

  test("UI-3: scheduling shows what will run, needs the header decision, and sends consent + skipped header", async () => {
    const fetch = stubFetch((path) => path.endsWith("/summary") ? sum({ request_header_hints: ["X-HackerOne-Research"] }) : path.endsWith("/schedule") ? {} : { scans: [] });
    location.hash = "/program/acme";
    render(<App />);
    const enable = await screen.findByRole("button", { name: "Bật giám sát" });
    expect(screen.getByTestId("schedule-preview")).toHaveTextContent(/light.*header gửi kèm: không có/);
    fireEvent.click(screen.getByLabelText(/Program cho phép scan tự động theo lịch/));
    expect(enable).toBeDisabled();   // consent alone is not enough: the policy names a header nobody configured
    expect(screen.getAllByRole("status").some((n) => /X-HackerOne-Research.*chưa lưu header mặc định/.test(n.textContent || ""))).toBe(true);
    fireEvent.click(screen.getByLabelText(/lịch này không gửi header X-HackerOne-Research/));
    await waitFor(() => expect(enable).toBeEnabled());
    fireEvent.click(enable);
    await waitFor(() => expect(calls(fetch, "/schedule")).toHaveLength(1));
    expect(JSON.parse(calls(fetch, "/schedule")[0][1]!.body as string)).toMatchObject({ depth: "light", automation_ack: true, skipped_headers: ["X-HackerOne-Research"] });
  });

  test("UI-3: a saved program header means no extra decision and is named in the preview", async () => {
    stubFetch((path) => path.endsWith("/summary") ? sum({ request_header_hints: ["X-HackerOne-Research"], request_headers: ["X-HackerOne-Research: me"] }) : { scans: [] });
    location.hash = "/program/acme";
    render(<App />);
    await screen.findByRole("button", { name: "Bật giám sát" });
    expect(screen.getByTestId("schedule-preview")).toHaveTextContent(/header gửi kèm: X-HackerOne-Research/);
    fireEvent.click(screen.getByLabelText(/Program cho phép scan tự động theo lịch/));
    expect(screen.getByRole("button", { name: "Bật giám sát" })).toBeEnabled();
    expect(screen.queryByLabelText(/lịch này không gửi header/)).not.toBeInTheDocument();
  });

  test("UI-4: 'active' hosts are inventory, not proof of HTTP; unprobed rows say so", async () => {
    stubFetch((path) => {
      if (path.endsWith("/summary")) return sum({ assets_active: 944, assets_live: 4 });
      if (path.includes("/assets?")) return { __total: 1, body: [{ id: 1, host: "a.acme.com", rank_score: 1, status_code: null, tech: [], reasons: [], category: "web" }] };
      return {};
    });
    location.hash = "/program/acme";
    const { unmount } = render(<App />);
    const tile = (await screen.findByText("Host", { selector: ".tile-label" })).closest("a")!;
    expect(tile).toHaveTextContent("944");
    expect(tile).toHaveTextContent(/trong inventory · 4 có HTTP · 940 chưa probe/);
    expect(tile).not.toHaveTextContent("đang hoạt động");
    unmount();
    location.hash = "/program/acme/data?v=hosts";
    render(<App />);
    expect(await screen.findByText("chưa có HTTP")).toBeInTheDocument();
  });

  test("UI-5: a real comparison with no changes says what was compared", async () => {
    stubFetch((path) => path.includes("/diff?") ? { __total: 0, body: [] } : path.endsWith("/summary") ? sum() : {});
    location.hash = "/program/acme/history?v=diff";
    render(<App />);
    expect(await screen.findByText("Đã so sánh #2 với #1: không phát hiện thay đổi.")).toBeInTheDocument();
    expect(screen.queryByText(/sau khi program có từ hai scan/)).not.toBeInTheDocument();
  });

  test("UI-7: the policy the user pasted is shown next to the source policy", async () => {
    stubFetch((path) => path.endsWith("/summary") ? sum() : path === "/api/programs/acme" ? { scans: [], scope: [], policy: { policy_text: "Source policy text", policy_source: "api", user_policy_text: "Add X-HackerOne-Research header" } } : {});
    location.hash = "/program/acme/guide?v=scope";
    render(<App />);
    expect(await screen.findByTestId("user-policy")).toHaveTextContent("X-HackerOne-Research");
    expect(screen.getByText("Source policy text")).toBeInTheDocument();
    expect(screen.queryByText(/Chưa có nội dung policy/)).not.toBeInTheDocument();
  });

  test("UI-8: revealing secrets can be turned off again, and the download says when it is raw", async () => {
    const fetch = stubFetch((path) => {
      if (path.endsWith("/phases")) return { scan_id: 9, slug: "acme", status: "done", depth: "light", missing_tools: [], funnel: null, phases: [{
        key: "secrets", title: "Bí mật trong JS", what: "quét", touches: true, status: "ran", status_label: "Đã chạy", reason: null, count: 1, count_label: "dấu vết",
        files: [{ path: "a.jsonl", name: "a.jsonl", label: "a.jsonl", bytes: 5, lines: 1 }], view: { kind: "file", label: "Đọc" } }] };
      if (path.includes("/artifact?")) { const reveal = path.includes("reveal=true"); return { total: 1, offset: 0, limit: 100, redacted: !reveal, lines: [reveal ? "H1_TOKEN=FAKE-MARKER" : "H1_TOKEN=[ẩn]"] }; }
      return path.endsWith("/review") ? baseReview() : { id: 9, status: "done", depth: "light" };
    });
    location.hash = "/scan/9";
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Đọc/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByLabelText(/Hiện giá trị/));
    expect(await within(dialog).findByText(/FAKE-MARKER/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: /Tải file THÔ/ })).toHaveAttribute("href", expect.stringContaining("reveal=true"));
    const toggle = within(dialog).getByLabelText(/Hiện giá trị/) as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    fireEvent.click(toggle);   // still there after reveal: it can be switched back
    expect(await within(dialog).findByText(/\[ẩn\]/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/FAKE-MARKER/)).not.toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Tải file ↓" })).toBeInTheDocument();
    expect(fetch).toBeDefined();
  });

  test("F3: a skipped scheduled run is explained on the Program page", async () => {
    stubFetch((path) => path.endsWith("/summary") ? sum({ schedule: { interval: "daily", depth: "light", enabled: 1, next_run_at: "2026-10-18T01:00:00Z",
      last_error: "Chưa đủ dữ liệu scope/policy để chạy light: Scope chỉ lấy từ bản sao bounty-targets-data.", last_error_at: "2026-10-17T01:00:00Z" } }) : { scans: [] });
    location.hash = "/program/acme";
    render(<App />);
    const alert = await screen.findByTestId("schedule-error");
    expect(alert).toHaveTextContent(/đã bị bỏ qua.*Chưa đủ dữ liệu scope\/policy/);
  });

  test("F1: Review says that exclusions are kept for Rescan and schedules", async () => {
    stubFetch((path) => path === "/api/health" ? health() : path.endsWith("/review") ? baseReview() : path.endsWith("/config") ? { ...baseConfig, excluded_hosts: ["legacy.acme.com", "https://acme.com/admin"] } : {});
    location.hash = "/scan/4/review";
    render(<App />);
    expect(await screen.findByText(/đang có 2/)).toBeInTheDocument();
    expect(screen.getByText(/lưu cho program: Scan lại và lịch giám sát dùng lại/)).toBeInTheDocument();
  });

  test("F4: an older draft says a newer one exists and links to it", async () => {
    stubFetch((path) => path === "/api/health" ? health() : path.endsWith("/review") ? baseReview({ policy_newer: true, newest_draft: 9 }) : path.endsWith("/config") ? baseConfig : {});
    location.hash = "/scan/4/review";
    render(<App />);
    const note = await screen.findByTestId("policy-newer");
    expect(note).toHaveTextContent(/Resolve lại sau bản nháp này/);
    expect(within(note).getByRole("link", { name: /#9/ })).toHaveAttribute("href", "#/scan/9/review");
  });

});

describe("Sitemap tree (Data › URL › Cây sitemap)", () => {
  const node = (over: object) => ({ name: "", display: "", kind: "dir", host: "a.example.com", path: "/", count: 1, self_count: 0, variants: 0, has_children: false,
    max_score: 0, tags: [], verification: "historical", is_new: false, first_seen_scan: 1, last_seen_scan: 2, url: null, children: null, ...over });
  const hosts = [node({ name: "a.example.com", display: "a.example.com", kind: "host", count: 5, has_children: true, url: "https://a.example.com/" }),
                 node({ name: "b.example.com", display: "b.example.com", kind: "host", host: "b.example.com", count: 1, url: "https://b.example.com/" })];
  const kids = [node({ name: "Alpha", display: "Alpha", path: "/Alpha", count: 3, has_children: true, max_score: 4, tags: ["api"], verification: "observed" }),
                node({ name: "zeta", display: "zeta", kind: "file", path: "/zeta", count: 1, url: "https://a.example.com/zeta" })];
  const level = (nodes: object[], over: object = {}) => ({ scan: "latest", scan_id: 2, host: null, prefix: "/", nodes, total: nodes.length, truncated: false, ...over });
  const stub = () => stubFetch((path) => {
    if (path.includes("/urls/tree")) {
      if (path.includes("host=a.example.com")) return level(kids, { host: "a.example.com" });
      if (path.includes("depth=2") || path.includes("depth=3") || path.includes("depth=12")) return level([{ ...hosts[0], children: kids, children_total: 2 }, hosts[1]]);
      return level(hosts);
    }
    if (path.includes("/urls/summary")) return { scan_id: 2, total: 6, history_total: 6, funnel: null, by_tag: {}, top_shapes: [], hosts: [], latest: { id: 2, depth: "light", status: "done", finished_at: null } };
    return {};
  });
  const open = async () => {
    location.hash = "/program/acme/data?v=urls";
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Cây sitemap" }));
  };

  test("hosts first; an arrow loads and shows one level; the same arrow hides it again", async () => {
    const fetch = stub();
    await open();
    const tree = await screen.findByRole("tree", { name: "Sitemap" });
    expect(Array.from(tree.querySelectorAll(".tree-name")).map((n) => n.textContent)).toEqual(["a.example.com", "b.example.com"]);
    expect(fetch.mock.calls.some((c) => String(c[0]).includes("/urls/tree?") && String(c[0]).includes("min_score=0"))).toBe(true);   // the tree starts from every URL
    fireEvent.click(screen.getByRole("button", { name: "Mở a.example.com" }));
    expect(await screen.findByText("Alpha/")).toBeInTheDocument();
    expect(screen.getByText("zeta")).toBeInTheDocument();
    expect(fetch.mock.calls.some((c) => String(c[0]).includes("host=a.example.com") && String(c[0]).includes("prefix=%2F"))).toBe(true);
    expect(tree.querySelector('li[aria-level="1"]')).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByRole("button", { name: "Thu a.example.com" }));
    await waitFor(() => expect(screen.queryByText("Alpha/")).not.toBeInTheDocument());
  });

  test("keyboard: → opens, ← closes, ↓ moves; leaves have no arrow, copy and open-in-new-tab are offered", async () => {
    stub();
    await open();
    const first = (await screen.findByRole("tree", { name: "Sitemap" })).querySelector<HTMLElement>("[data-row]")!;
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(await screen.findByText("Alpha/")).toBeInTheDocument();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toMatch(/Alpha\//);
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });                 // from a closed child, ← goes to the parent
    expect(document.activeElement?.textContent).toMatch(/a\.example\.com/);
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    await waitFor(() => expect(screen.queryByText("Alpha/")).not.toBeInTheDocument());
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
    const zeta = (await screen.findByText("zeta")).closest("[data-row]") as HTMLElement;
    expect(within(zeta).queryByRole("button", { name: /Mở zeta|Thu zeta/ })).not.toBeInTheDocument();
    expect(within(zeta).queryByRole("link")).not.toBeInTheDocument();                 // rows stay compact: arrow, icon, name, count
    fireEvent.click(zeta);                                                            // the details (and the actions) live in the side panel
    const detail = await screen.findByTestId("tree-detail");
    expect(within(detail).getByRole("link", { name: /trong tab mới/ })).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(detail).getByRole("button", { name: "Chép URL" })).toBeInTheDocument();
    expect(detail).toHaveTextContent("a.example.com/zeta");
    expect(detail).toHaveTextContent(/Lịch sử — chỉ cho biết URL từng tồn tại/);
  });

  test("sorting asks the server; 'Mở tới cấp 2' opens everything it returned; searching shows a flat list by host and can reveal the URL in the tree", async () => {
    const fetch = stubFetch((path) => {
      if (/\/urls\?/.test(path) && path.includes("q=alpha")) {
        return { __total: 2, body: [
          { id: 1, url: "https://a.example.com/Alpha/x", host: "a.example.com", source: "katana", score: 4, verification: "observed", shape: null, tags: ["api"], first_seen_scan: 1, last_seen_scan: 2, is_new: false },
          { id: 2, url: "https://a.example.com/alpha-two", host: "a.example.com", source: "gau", score: 2, verification: "historical", shape: null, tags: [], first_seen_scan: 1, last_seen_scan: 1, is_new: true }] };
      }
      if (path.includes("/urls/tree")) {
        if (path.includes("prefix=%2FAlpha")) return level([node({ name: "x", display: "x", kind: "file", path: "/Alpha/x", url: "https://a.example.com/Alpha/x" })], { host: "a.example.com" });
        if (path.includes("host=a.example.com")) return level(kids, { host: "a.example.com" });
        if (path.includes("depth=2") || path.includes("depth=3") || path.includes("depth=12")) return level([{ ...hosts[0], children: kids, children_total: 2 }, hosts[1]]);
        return level(hosts);
      }
      if (path.includes("/urls/summary")) return { scan_id: 2, total: 6, history_total: 6, funnel: null, by_tag: {}, top_shapes: [], hosts: [], latest: { id: 2, depth: "light", status: "done", finished_at: null } };
      return {};
    });
    await open();
    await screen.findByRole("tree", { name: "Sitemap" });
    fireEvent.change(screen.getByLabelText("Sắp xếp cây"), { target: { value: "score" } });
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("/urls/tree?") && String(c[0]).includes("sort=score"))).toBe(true));
    fireEvent.click(screen.getByLabelText("Thư mục trước file"));
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("folders_first=true"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Mở tới cấp 2" }));
    expect(await screen.findByText("Alpha/")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Thu hết" }));
    await waitFor(() => expect(screen.queryByText("Alpha/")).not.toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Tìm URL"), { target: { value: "alpha" } });
    const results = await screen.findByTestId("tree-results");                                    // a list, not hundreds of opened branches
    await waitFor(() => expect(results).toHaveTextContent(/2.*URL khớp, nhóm theo host/));
    expect(within(results).getByRole("heading", { name: /a\.example\.com/ })).toBeInTheDocument();
    expect(screen.queryByRole("tree", { name: "Sitemap" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.some((c) => /\/urls\/tree\?/.test(String(c[0])) && String(c[0]).includes("q=alpha"))).toBe(false);   // the tree is not asked to search
    fireEvent.click(within(results).getByText(/a\.example\.com\/Alpha\/x/));
    const detail = await screen.findByTestId("tree-detail");
    expect(detail).toHaveTextContent("a.example.com › Alpha › x");                               // breadcrumb
    expect(detail).toHaveTextContent("katana");                                                  // source
    fireEvent.click(within(detail).getByRole("button", { name: "Xem trong cây" }));
    const tree = await screen.findByRole("tree", { name: "Sitemap" });                           // search cleared, tree walks to the folder
    await waitFor(() => expect(tree.querySelector(".tree-row.selected")).toBeTruthy());
    expect((tree.querySelector(".tree-row.selected .tree-name") as HTMLElement).textContent).toBe("x");     // the file itself, with its folders opened above it
    expect(tree.querySelector('li[aria-level="2"]')).toHaveAttribute("aria-expanded", "true");
    expect((screen.getByLabelText("Tìm URL") as HTMLInputElement).value).toBe("");
  });
});

describe("Tools page", () => {
  const row = (over: object) => ({ id: "x", kind: "binary", label: "x", purpose: "để làm gì", state: "ready", detail: "", required_for: ["light", "strong"], optional: false,
    used_by: [{ key: "nuclei", title: "Nuclei" }], pinned_version: "v1", version: null, checked_at: null, remedy: "", impact: { passive: "unused", light: "ok", strong: "ok" }, ...over });
  const report = (rows: object[], summary: object = {}) => ({ tools: rows, depths: ["passive", "light", "strong"], runtime: { os: "Linux", recon_supported: true },
    summary: { ready: 1, missing_required: [], missing_optional: [], missing_framework: [], ...summary } });

  test("routes: /tools and the focus parameter", () => {
    expect(parseRoute("/tools")).toEqual({ page: "tools", focus: "" });
    expect(parseRoute("/tools?focus=nuclei-templates")).toEqual({ page: "tools", focus: "nuclei-templates" });
  });

  test("a missing required tool says what is skipped; an optional one is not an alarm; deep check fills versions", async () => {
    let checked = false;
    const fetch = stubFetch((path, init) => {
      if (path === "/api/tools/check") { checked = true; }
      if (path.startsWith("/api/tools")) {
        const rows = [
          row({ id: "katana", label: "katana", state: checked ? "ready" : "missing_binary", detail: "Không thấy trên máy chủ.", remedy: "Build lại image.",
                impact: { passive: "unused", light: "Bước bị bỏ qua: Crawl chủ động", strong: "Bước bị bỏ qua: Crawl chủ động" }, version: checked ? "v1.8.0" : null }),
          row({ id: "bbscope", label: "bbscope", state: "missing_binary", detail: "Không thấy.", required_for: [], optional: true, used_by: [], impact: { passive: "optional", light: "optional", strong: "optional" } }),
        ];
        return report(rows, { missing_required: checked ? [] : ["katana"], missing_optional: ["bbscope"] });
      }
      return {};
    });
    location.hash = "/tools?focus=katana";
    render(<App />);
    const summary = await screen.findByTestId("tools-summary");
    expect(summary).toHaveTextContent(/Thiếu công cụ cần cho scan: katana/);
    expect(summary).toHaveTextContent(/Tùy chọn chưa cài \(không ảnh hưởng\): bbscope/);
    const katana = document.getElementById("tool-katana")!;
    expect(within(katana).getByText("Chưa cài")).toBeInTheDocument();
    expect(within(katana).getByText(/Build lại image/)).toBeInTheDocument();
    const bbscope = document.getElementById("tool-bbscope")!;
    expect(within(bbscope).getByText(/tùy chọn/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Kiểm phiên bản/ }));
    expect(await screen.findByText("v1.8.0")).toBeInTheDocument();
    expect(calls(fetch, "/api/tools/check", "POST")).toHaveLength(1);
    await waitFor(() => expect(screen.getByTestId("tools-summary")).toHaveTextContent(/Mọi công cụ cần cho/));
  });

  test("Review links a missing tool to the Tools page", async () => {
    stubFetch((path) => path === "/api/health" ? health() : path.endsWith("/review") ? baseReview() : path.endsWith("/config") ? baseConfig : {});
    location.hash = "/scan/4/review";
    render(<App />);
    const link = await screen.findByRole("link", { name: /Xem trang Công cụ/ });
    expect(link).toHaveAttribute("href", "#/tools?focus=nuclei");
  });
});

describe("Nuclei templates panel and per-scan custom templates", () => {
  const toolsReport = (templates: object) => ({ tools: [
    { id: "nuclei", kind: "binary", label: "nuclei", purpose: "p", state: "ready", detail: "", required_for: ["light"], optional: false, used_by: [], pinned_version: null, version: null, checked_at: null, remedy: "", impact: { passive: "unused", light: "ok", strong: "ok" } },
    { id: "nuclei-templates", kind: "data", label: "nuclei-templates", purpose: "p", state: "missing_data", detail: "", required_for: ["light"], optional: false, used_by: [], pinned_version: null, version: null, checked_at: null, remedy: "x", impact: { passive: "unused", light: "ok", strong: "ok" }, templates }],
    depths: ["passive", "light", "strong"], runtime: { os: "Linux", recon_supported: true }, summary: { ready: 1, missing_required: ["nuclei-templates"], missing_optional: [], missing_framework: [] } });
  const info = (over: object = {}) => ({ installed: false, count: 0, updated_at: null, source: null, version: null, job: null, custom: [], ...over });

  test("not installed -> install; a failed job says why and that the old set is kept; a custom template can be added and removed", async () => {
    let state = info();
    let custom: object[] = [];
    const fetch = stubFetch((path, init) => {
      if (path === "/api/tools/templates/update") { state = info({ job: { state: "failed", started_at: "2026-10-16T01:00:00Z", finished_at: "2026-10-16T01:00:05Z", message: "GitHub từ chối truy cập (403). Bộ template cũ (nếu có) vẫn được giữ.", count: null } }); return { job: state.job }; }
      if (path === "/api/tools/templates/custom" && init?.method === "POST") { custom = [{ id: "my-check", name: "My check", enabled: false, bytes: 120, added_at: "2026-10-16T01:00:00Z" }]; return custom[0]; }
      if (path.startsWith("/api/tools/templates/custom/") && init?.method === "DELETE") { custom = []; return { deleted: "my-check" }; }
      if (path === "/api/tools/templates") return { ...state, custom };
      if (path === "/api/tools") return toolsReport({ ...state, custom });
      return {};
    });
    vi.stubGlobal("confirm", () => true);
    location.hash = "/tools";
    render(<App />);
    const status = await screen.findByTestId("template-status");
    expect(status).toHaveTextContent(/Chưa cài/);
    fireEvent.click(screen.getByRole("button", { name: "Cài templates" }));
    await waitFor(() => expect(calls(fetch, "/api/tools/templates/update", "POST")).toHaveLength(1));
    expect(await screen.findByTestId("template-job")).toHaveTextContent(/thất bại.*403.*giữ/);
    fireEvent.click(screen.getByText(/Template riêng \(/));
    fireEvent.change(screen.getByLabelText("YAML template"), { target: { value: "id: my-check\ninfo: {name: My check}\nhttp: []" } });
    fireEvent.click(screen.getByRole("button", { name: "Thêm template" }));
    expect(await screen.findByText("My check")).toBeInTheDocument();
    expect(JSON.parse(calls(fetch, "/api/tools/templates/custom", "POST")[0][1]!.body as string).content).toMatch(/^id: my-check/);
    fireEvent.click(screen.getByRole("button", { name: "Xoá" }));
    await waitFor(() => expect(screen.queryByText("My check")).not.toBeInTheDocument());
  });

  test("Review lets you choose custom templates for this scan only, and sends the ids with the config", async () => {
    const fetch = stubFetch((path) => path === "/api/health" ? health() : path === "/api/tools/templates" ? info({ installed: true, count: 9000, custom: [{ id: "my-check", name: "My check", enabled: false, bytes: 1, added_at: "2026-10-16T01:00:00Z" }] })
      : path.endsWith("/review") ? baseReview() : path.endsWith("/config") ? baseConfig : path.endsWith("/launch") ? { scan_id: 4, status: "queued" } : {});
    location.hash = "/scan/4/review";
    render(<App />);
    fireEvent.click(await screen.findByLabelText(/Tôi đã đọc policy và program cho phép/));
    fireEvent.click(await screen.findByLabelText(/My check/));
    fireEvent.click(screen.getByRole("button", { name: "Launch scan" }));
    await waitFor(() => expect(calls(fetch, "/launch")).toHaveLength(1));
    expect(JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config.nuclei_custom).toEqual(["my-check"]);
  });
});

describe("Drafts cleanup and program lifecycle (archive / restore / delete)", () => {
  const summaryOf = (over: object = {}) => ({
    slug: "acme", source: "h1", handle: "acme", target_path: "/t/acme", hunt_command: "cd x", hunt_note: "",
    latest_scan: { id: 2, status: "done", depth: "light" }, last_completed_scan: { id: 2, status: "done", depth: "light" },
    changes: { new: 0, changed: 0, gone: 0 }, findings_by_severity: {}, assets_active: 1, top_surface: [], draft_count: 0, schedule: null, ...over,
  });

  test("Portfolio: filter drafts by name, select what is shown, delete in one request and report skipped ones", async () => {
    let drafts: object[] = [
      { id: 5, slug: "alpha-one", source: "raw", depth: "light", created_at: null, in: 1, out: 0 },
      { id: 6, slug: "alpha-two", source: "raw", depth: "light", created_at: null, in: 1, out: 0 },
      { id: 7, slug: "beta", source: "h1", depth: "light", created_at: null, in: 1, out: 0 },
    ];
    const fetch = stubFetch((path, init) => {
      if (path === "/api/drafts/delete") { drafts = drafts.filter((d: any) => d.id === 7); return { deleted: [5], skipped: [{ id: 6, reason: "launched" }] }; }
      return path.split("?")[0] === "/api/programs" ? [] : path === "/api/drafts" ? drafts : health();
    });
    vi.stubGlobal("confirm", () => true);
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Lọc bản nháp theo tên"), { target: { value: "alpha" } });
    expect(screen.queryByLabelText("Chọn bản nháp #7")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Chọn các bản đang hiện \(2\)/ }));
    fireEvent.click(screen.getByRole("button", { name: "Xoá 2 bản đã chọn" }));
    await waitFor(() => expect(calls(fetch, "/api/drafts/delete", "POST")).toHaveLength(1));
    expect(JSON.parse(calls(fetch, "/api/drafts/delete", "POST")[0][1]!.body as string).ids.sort()).toEqual([5, 6]);
    expect(await screen.findByText(/Đã xoá 1/)).toBeInTheDocument();
  });

  test("Portfolio: archived programs live under their own tab with a count, hidden from the main list", async () => {
    const live = { id: 2, slug: "live", source: "h1", asset_count: 3, new_count: 0, finding_count: 0, draft_count: 0, monitoring: false, archived_at: null, latest_scan: null };
    const old = { id: 1, slug: "old", source: "h1", asset_count: 1, new_count: 0, finding_count: 0, draft_count: 0, monitoring: false, archived_at: "2026-10-01T00:00:00Z", latest_scan: null };
    stubFetch((path) => path.startsWith("/api/programs") ? [live, old] : path === "/api/drafts" ? [] : health());
    render(<App />);
    expect(await screen.findByRole("heading", { name: "live" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "old" })).not.toBeInTheDocument();
    const views = screen.getByTestId("portfolio-views");
    expect(views).toHaveTextContent("Đang hoạt động (1)");
    fireEvent.click(within(views).getByRole("button", { name: "Đã lưu trữ (1)" }));
    expect(await screen.findByRole("heading", { name: "old" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "live" })).not.toBeInTheDocument();
    expect(screen.getByText("Đã lưu trữ", { selector: ".badge, span" })).toBeInTheDocument();
  });

  test("Program: archive asks first, then the banner offers restore", async () => {
    let archived: string | null = null;
    const fetch = stubFetch((path, init) => {
      if (path.endsWith("/archive")) { archived = "2026-10-16T00:00:00Z"; return { slug: "acme", archived_at: archived }; }
      if (path.endsWith("/restore")) { archived = null; return { slug: "acme", archived_at: null }; }
      return path.endsWith("/summary") ? summaryOf({ archived_at: archived }) : {};
    });
    vi.stubGlobal("confirm", () => true);
    location.hash = "/program/acme";
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Lưu trữ" }));
    const banner = await screen.findByTestId("archived-banner");
    expect(banner).toHaveTextContent(/Program đã lưu trữ/);
    expect(screen.queryByRole("button", { name: "Scan lại" })).not.toBeInTheDocument();
    fireEvent.click(within(banner).getByRole("button", { name: "Khôi phục" }));
    await waitFor(() => expect(screen.queryByTestId("archived-banner")).not.toBeInTheDocument());
    expect(calls(fetch, "/archive", "POST")).toHaveLength(1);
    expect(calls(fetch, "/restore", "POST")).toHaveLength(1);
  });

  test("Program: permanent delete lists what goes and needs the name typed", async () => {
    const fetch = stubFetch((path, init) => {
      if (path.endsWith("/delete-preview")) return { slug: "acme", archived: true, counts: { scans: 3, drafts: 0, asset: 40, url: 900, finding: 2, diff_event: 7 }, has_schedule: true,
        folder: { path: "/t/acme", files: 12, bytes: 20480 }, blockers: [] };
      if (init?.method === "DELETE") return { deleted: "acme" };
      if (path.split("?")[0] === "/api/programs" || path === "/api/drafts") return [];
      return path.endsWith("/summary") ? summaryOf({ archived_at: "2026-10-01T00:00:00Z", schedule: { interval: "daily", depth: "light", enabled: 0, next_run_at: null, paused_by_archive: 1 } }) : {};
    });
    location.hash = "/program/acme";
    render(<App />);
    expect(await screen.findByTestId("schedule-archived")).toHaveTextContent(/tạm dừng/);
    fireEvent.click(await screen.findByRole("button", { name: "Xóa vĩnh viễn…" }));
    const panel = await screen.findByTestId("delete-panel");
    expect(panel).toHaveTextContent(/900 URL/);
    expect(panel).toHaveTextContent(/\/t\/acme/);
    const button = within(panel).getByRole("button", { name: "Xóa vĩnh viễn" });
    expect(button).toBeDisabled();
    fireEvent.change(within(panel).getByLabelText("Gõ tên program để xác nhận xóa"), { target: { value: "acm" } });
    expect(button).toBeDisabled();
    fireEvent.change(within(panel).getByLabelText("Gõ tên program để xác nhận xóa"), { target: { value: "acme" } });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(calls(fetch, "/api/programs/acme", "DELETE")).toHaveLength(1));
    expect(JSON.parse(calls(fetch, "/api/programs/acme", "DELETE")[0][1]!.body as string)).toEqual({ confirm_slug: "acme" });
    await waitFor(() => expect(location.hash).toMatch(/^#?\/?$/));
  });

  test("Review: an archived program is flagged as restored by launching", async () => {
    stubFetch((path) => path === "/api/health" ? health() : path.endsWith("/review") ? baseReview({ archived: true }) : path.endsWith("/config") ? baseConfig : {});
    location.hash = "/scan/4/review";
    render(<App />);
    expect(await screen.findByTestId("review-archived")).toHaveTextContent(/khôi phục/);
  });
});

describe("Charts (V2): trend, distributions, severity matrix, stage timeline", () => {
  const chartData = (over: object = {}) => ({
    trend: [
      { id: 3, depth: "light", status: "done", finished_at: null, hosts: 5, live: 3, urls: 40, findings: 1, new: 3, changed: 0, gone: 0 },
      { id: 5, depth: "light", status: "done", finished_at: null, hosts: 7, live: 6, urls: 30, findings: 2, new: 4, changed: 1, gone: 2 },
    ],
    truncated: false,
    status: { classes: { "2xx": 5, "4xx": 2, none: 1 }, codes: [{ code: 200, count: 5 }], total: 8 },
    tech: [{ name: "nginx", count: 6 }],
    hosts_by_urls: [{ host: "a.example.com", urls: 120, top_score: 6.5 }],
    severity_matrix: { severities: ["critical", "high", "medium", "low", "info"], hosts: [{ host: "a.example.com", critical: 0, high: 2, medium: 0, low: 1, info: 0 }] },
    ...over,
  });
  const summary = { slug: "acme", source: "h1", handle: "acme", target_path: "/t/acme", hunt_command: "cd x", hunt_note: "", latest_scan: { id: 5, status: "done", depth: "light" },
    last_completed_scan: { id: 5, status: "done", depth: "light" }, changes: { new: 4, changed: 1, gone: 2 }, findings_by_severity: {}, assets_active: 8, top_surface: [], draft_count: 0, schedule: null };

  test("Overview prints the trend with deltas, a table alternative, distributions and the matrix", async () => {
    stubFetch((path) => path.endsWith("/charts") ? chartData() : path.endsWith("/summary") ? summary : {});
    location.hash = "/program/acme";
    render(<App />);
    const trend = await screen.findByTestId("trend");
    const urls = trend.querySelector('[data-metric="URL"]')!;
    expect(urls).toHaveTextContent("30");
    expect(urls).toHaveTextContent(/▼ .*10 so với scan trước/);                 // the direction is text, not only a line going down
    expect(trend.querySelector('svg[aria-label^="Thay đổi mỗi scan"]')!.getAttribute("aria-label")).toContain("#5: 4/1/2");
    fireEvent.click(screen.getByText("Xem dạng bảng"));
    expect(within(trend.querySelector("table")!).getByRole("link", { name: "#5" })).toHaveAttribute("href", "#/scan/5");
    const dist = screen.getByTestId("distributions");
    expect(dist).toHaveTextContent("2xx thành công");
    expect(dist).toHaveTextContent("Chưa probe HTTP");
    expect(dist).toHaveTextContent("nginx");
    expect(dist).toHaveTextContent(/a\.example\.com.*120/);
    const matrix = screen.getByTestId("severity-matrix");
    expect(within(matrix).getByRole("cell", { name: "2" })).toBeInTheDocument();
  });

  test("a single completed scan says a trend needs two, and an empty program draws nothing", async () => {
    stubFetch((path) => path.endsWith("/charts") ? chartData({ trend: chartData().trend.slice(1), hosts_by_urls: [], tech: [], severity_matrix: { severities: [], hosts: [] }, status: { classes: {}, codes: [], total: 0 } })
      : path.endsWith("/summary") ? summary : {});
    location.hash = "/program/acme";
    render(<App />);
    expect(await screen.findByTestId("trend-empty")).toHaveTextContent(/ít nhất hai scan/);
    expect(screen.getByText("Chưa có host.")).toBeInTheDocument();
    expect(screen.getByText(/Chưa có finding để lập ma trận/)).toBeInTheDocument();
  });

  test("Run: the stage timeline shows used vs budget and spells out an exhausted budget", async () => {
    const { ScanProgress } = await import("./components/ScanProgress");
    render(<ScanProgress data={{ stages: [
      { key: "discovery", label: "Khám phá", status: "ok", budget_s: 100, used_s: 40, commands: 3 },
      { key: "probe", label: "Probe", status: "timeout", budget_s: 60, used_s: 60, commands: 2 },
      { key: "deep", label: "Sâu", status: "empty", budget_s: 0, used_s: 0, commands: 0 },
    ] }} />);
    const timeline = screen.getByTestId("stage-timeline");
    expect(within(timeline).getAllByRole("listitem")).toHaveLength(2);           // a stage with no budget and no time is not drawn
    expect(timeline).toHaveTextContent("40s / 100s");
    expect(timeline).toHaveTextContent("60s / 60s — dùng hết ngân sách");
    expect(timeline.textContent).not.toContain("40s / 100s — dùng hết");
  });
});

describe("arc-bbp #65 audit: partial results, coverage split, funnel, data notes, first scan", () => {
  const phase = (over: object) => ({ key: "port_scan", title: "Quét cổng", what: "nmap", touches: true, status: "partial", status_label: "Chạy dở dang", reason: "Công cụ dừng giữa chừng",
    detail: "3 host, 8 cặp host/cổng mở (7 số cổng khác nhau) — DỞ DANG. 7 cặp nằm trên IP của Cloudflare (CDN/biên dùng chung): đây là cổng của CDN, chưa chứng minh là cổng của máy chủ gốc",
    count: 8, count_label: "cặp host/cổng", partial: true, files: [], view: { kind: "file", label: "Đọc kết quả nmap" }, ...over });
  const report = (extra: object = {}) => ({
    scan_id: 65, slug: "arc", status: "done_partial", depth: "strong", missing_tools: [], phases: [phase({})],
    funnel: { raw: 1990, in_scope: 456, from_probe: 33, stored: 489, out_of_scope: 1301, invalid: 0 },
    stages: [{ key: "probe", label: "Probe host đã khám phá", status: "timeout", budget_s: 300, used_s: 300, commands: 3, commands_ok: 2, commands_timeout: 1, commands_skipped: 0 }],
    coverage: { discovered: 126, probed: 35, unprobed: 91, explicit: 2, batches: 3, batches_done: 2, batches_timeout: 1, attempted: 126, responded: 35, completed: 84, unreached: 0 }, ...extra });

  test("Run: partial nmap says so, counts pairs, flags the CDN; coverage is split by evidence; the funnel adds up", async () => {
    stubFetch((path) => path.endsWith("/phases") ? report() : path.endsWith("/review") ? baseReview({ scan: { id: 65, depth: "strong", status: "done_partial" } }) : { id: 65, status: "done_partial", depth: "strong", program_id: 1 });
    location.hash = "/scan/65";
    render(<App />);
    const detail = await screen.findByTestId("detail-port_scan");
    expect(detail).toHaveTextContent(/8 cặp host\/cổng.*DỞ DANG/);
    expect(detail).toHaveTextContent(/cổng của CDN, chưa chứng minh/);
    const row = document.querySelector('[data-step="port_scan"]') as HTMLElement;
    expect(within(row).getByText("Chạy dở dang")).toBeInTheDocument();
    const split = await screen.findByTestId("coverage-split");
    expect(split).toHaveTextContent("35 host đã trả lời HTTP");
    expect(split).toHaveTextContent("84 host thuộc đợt chạy xong (2/3 đợt, 1 đợt bị cắt giờ)");
    expect(split).toHaveTextContent(/chưa biết là host chết hay chưa kịp thử/);
    const funnel = screen.getByText("URL thu được").closest("section")!;
    expect(funnel).toHaveTextContent(/456.*trong scope.*\+.*33.*probe HTTP.*=.*489/s);
    expect(document.querySelector('tr[data-stage="probe"]')).toHaveTextContent("1 bị cắt giờ");
  });

  test("Program: the first scan is initial data, not a change; recalculated numbers are announced", async () => {
    const summary = { slug: "arc", source: "h1", handle: "arc", target_path: "/t", hunt_command: "cd x", hunt_note: "", latest_scan: { id: 65, status: "done_partial", depth: "strong" },
      last_completed_scan: { id: 65, status: "done_partial", depth: "strong", baseline_scan_id: null }, changes: { new: 132, changed: 0, gone: 0 }, findings_by_severity: {}, assets_active: 132,
      top_surface: [], draft_count: 0, schedule: null, data_notes: [{ fix: "takeover_not_vulnerable", at: "2026-10-16", note: "Trước đây 124 dòng sạch bị lưu thành takeover High. Đã tính lại." }] };
    stubFetch((path) => path.endsWith("/summary") ? summary : path.endsWith("/charts") ? { trend: [], status: { classes: {}, codes: [], total: 0 }, tech: [], hosts_by_urls: [], severity_matrix: { severities: [], hosts: [] }, truncated: false } : {});
    location.hash = "/program/arc";
    render(<App />);
    expect(await screen.findByText("Ghi nhận lần đầu")).toBeInTheDocument();
    expect(screen.queryByText("Thay đổi")).not.toBeInTheDocument();
    expect(screen.getByText(/132 asset ghi nhận lần đầu \(chưa có scan trước để so sánh\)/)).toBeInTheDocument();
    expect(screen.queryByText(/so với scan trước\./)).not.toBeInTheDocument();
    expect(screen.getByTestId("data-notes")).toHaveTextContent(/124 dòng sạch bị lưu thành takeover High/);
  });

  test("Run: nuclei says how many live URLs it actually got, not just the installed template count", async () => {
    const nuclei = { key: "nuclei", title: "Nuclei", what: "nuclei", touches: true, status: "ran", status_label: "Đã chạy", reason: null,
      detail: "50/60 URL đang sống được đưa cho nuclei (giới hạn 50 URL mỗi lượt — phần còn lại KHÔNG được quét); nuclei tự báo đã chạy 120 template, 8200 request trên 50 host (khác với số template ĐÃ CÀI trong Công cụ & môi trường)",
      count: 2, count_label: "finding", partial: false, files: [], view: { kind: "findings", label: "Xem findings", filter: { type: "nuclei" } } };
    stubFetch((path) => path.endsWith("/phases") ? report({ phases: [nuclei] }) : path.endsWith("/review") ? baseReview({ scan: { id: 65, depth: "strong", status: "done" } }) : { id: 65, status: "done", depth: "strong", program_id: 1 });
    location.hash = "/scan/65";
    render(<App />);
    const detail = await screen.findByTestId("detail-nuclei");
    expect(detail).toHaveTextContent(/50\/60 URL đang sống được đưa cho nuclei/);
    expect(detail).toHaveTextContent(/giới hạn 50 URL mỗi lượt.*KHÔNG được quét/);
    expect(detail).toHaveTextContent(/120 template.*8200 request/);
    expect(detail).toHaveTextContent(/ĐÃ CÀI/);
    const row = document.querySelector('[data-step="nuclei"]') as HTMLElement;
    expect(within(row).getByText("Đã chạy")).toBeInTheDocument();     // truncation alone is not "Chạy dở dang"
  });
});

describe("Review: coverage by asset type, apex and repo confirmations", () => {
  const coverage = (over: object = {}) => ({
    assets: [
      { pattern: "*.arc.io", category: "wildcard", mode: "recon", label: "Recon đầy đủ theo mức quét", detail: "Liệt kê subdomain, probe HTTP. Chỉ subdomain; domain gốc không được cấp quyền.", needs_confirmation: false },
      { pattern: "repo:https://github.com/circlefin/malachite", category: "source_code", mode: "manual_confirm", label: "Khóa tự động: scope có giới hạn", detail: "BBASM chưa giới hạn được theo thư mục", instruction: "Only code/crates is in scope", needs_confirmation: true },
      { pattern: "app:com.arc", category: "mobile", mode: "manual", label: "Chỉ lưu để làm tay", detail: "BBASM không tải app" },
    ],
    summary: { recon: 1, manual_confirm: 1, manual: 1 },
    apex: [{ apex: "arc.io", wildcard: "*.arc.io", status: "not_in_scope", dropped_urls: 1301, selected: false, confirmed: false }],
    stage_shares: [{ key: "discovery", until: 0.25, seconds: 675 }, { key: "deep", until: 0.95, seconds: 2565 }],
    path_rules: { hosts: {}, enforcement: [], active_allowed: false }, ...over });
  const setup = () => stubFetch((path, init) => path === "/api/health" ? health() : path.endsWith("/coverage") ? coverage()
    : path.endsWith("/review") ? baseReview() : path.endsWith("/config") ? baseConfig : path.endsWith("/launch") ? { scan_id: 4, status: "queued" } : {});

  test("every asset says what will happen to it; Strong does not read as 'everything scanned'", async () => {
    setup();
    location.hash = "/scan/4/review";
    render(<App />);
    const panel = await screen.findByTestId("coverage-summary");
    expect(panel).toHaveTextContent("1 asset recon tự động · 1 chỉ lưu để làm tay · 1 bị khóa chờ bạn xác nhận");
    expect(screen.getByText("Khóa tự động: scope có giới hạn")).toBeInTheDocument();
    expect(screen.getByText(/Only code\/crates is in scope/)).toBeInTheDocument();
    expect(screen.getByText("Chỉ lưu để làm tay")).toBeInTheDocument();
  });

  test("the apex is a separate, explicit choice that needs its own confirmation before launch", async () => {
    const fetch = setup();
    location.hash = "/scan/4/review";
    render(<App />);
    const apex = await screen.findByTestId("apex");
    expect(apex).toHaveTextContent(/chỉ gồm subdomain; domain gốc arc\.io.*ngoài scope.*1\.301 URL/s);
    fireEvent.click(screen.getByLabelText(/Tôi đã đọc policy và program cho phép/));
    fireEvent.click(screen.getByLabelText("Thêm domain gốc arc.io"));
    expect(await screen.findByText(/Sẽ thêm vào IN:/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Launch scan" })).toBeDisabled();                       // chosen but not confirmed
    expect(screen.getByText(/xác nhận đã đối chiếu policy chính thức/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Xác nhận policy cho phép domain gốc"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Launch scan" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Launch scan" }));
    await waitFor(() => expect(calls(fetch, "/launch")).toHaveLength(1));
    const sent = JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config;
    expect(sent.include_apex).toEqual(["arc.io"]);
    expect(sent.apex_confirmed).toBe(true);
  });

  test("a repo whose scope text limits it stays manual until the user allows a whole-repo scan", async () => {
    const fetch = setup();
    location.hash = "/scan/4/review";
    render(<App />);
    fireEvent.click(await screen.findByLabelText("Cho phép quét cả repo repo:https://github.com/circlefin/malachite"));
    fireEvent.click(screen.getByLabelText(/Tôi đã đọc policy và program cho phép/));
    fireEvent.click(screen.getByRole("button", { name: "Launch scan" }));
    await waitFor(() => expect(calls(fetch, "/launch")).toHaveLength(1));
    expect(JSON.parse(calls(fetch, "/launch")[0][1]!.body as string).config.source_full_repo_ok).toEqual(["repo:https://github.com/circlefin/malachite"]);
  });
});

describe("Run/Overview: what the scan did with each asset", () => {
  test("Run lists assets that were not scanned in full, with the reason", async () => {
    stubFetch((path) => path.endsWith("/phases") ? { scan_id: 65, slug: "arc", status: "done_partial", depth: "strong", missing_tools: [], phases: [], funnel: null, stages: [], coverage: null,
      asset_coverage: [
        { pattern: "*.arc.io", category: "wildcard", mode: "recon", label: "Recon", detail: "x" },
        { pattern: "repo:https://github.com/circlefin/malachite", category: "source_code", mode: "manual_confirm", label: "Khóa", detail: "BBASM chưa giới hạn được theo thư mục" },
        { pattern: "app:com.arc", category: "mobile", mode: "manual", label: "Làm tay", detail: "BBASM không tải app" }] }
      : path.endsWith("/review") ? baseReview({ scan: { id: 65, depth: "strong", status: "done_partial" } }) : { id: 65, status: "done_partial", depth: "strong" });
    location.hash = "/scan/65";
    render(<App />);
    const note = await screen.findByTestId("asset-coverage");
    expect(note).toHaveTextContent("1/3 asset được recon tự động");
    expect(note).toHaveTextContent("2 asset không được quét đầy đủ");
    expect(note).toHaveTextContent("khóa — chờ xác nhận");
    expect(note).toHaveTextContent("BBASM chưa giới hạn được theo thư mục");
  });
});

describe("Dữ liệu › Cổng/Dịch vụ, Đường dẫn dò được (BACKLOG mục 4)", () => {
  test("Ports: shows pairs, flags CDN ports and a cut-off nmap, same as Run", async () => {
    stubFetch((path) => path.endsWith("/summary") ? programSummary() : path.endsWith("/ports") ? {
      found: true, scan_id: 65, hosts: 2, unique_ports: 3, complete: false,
      files: [], rows: [{ host: "rpc.acme.com", ip: "104.18.1.10", port: 80, proto: "tcp", service: "http", version: "" },
                         { host: "db.acme.com", ip: "192.0.2.7", port: 22, proto: "tcp", service: "OpenSSH", version: "8.9" }],
      cdn: ["Cloudflare"], cdn_hosts: ["rpc.acme.com"], cdn_pairs: 1,
    } : { scans: [] });
    location.hash = "/program/acme/data?v=ports";
    render(<App />);
    expect(await screen.findByText("Cổng/Dịch vụ.", { selector: "strong" })).toBeInTheDocument();
    expect(await screen.findByTestId("ports-partial")).toHaveTextContent("DỞ DANG: nmap dừng trước khi quét xong");
    expect(screen.getByTestId("ports-cdn")).toHaveTextContent(/1 cặp nằm trên IP của Cloudflare.*chưa chứng minh/);
    expect(screen.getByText("rpc.acme.com")).toBeInTheDocument();
    expect(screen.getByText("OpenSSH 8.9")).toBeInTheDocument();
  });

  test("Ports: no Strong scan yet says so instead of an empty table", async () => {
    stubFetch((path) => path.endsWith("/summary") ? programSummary() : path.endsWith("/ports") ? { found: false, scan_id: null, pairs: 0, rows: [] } : { scans: [] });
    location.hash = "/program/acme/data?v=ports";
    render(<App />);
    expect(await screen.findByText(/Chưa có dữ liệu cổng/)).toBeInTheDocument();
  });

  test("Dirs: groups by host, shows noise removed and a 403-only host", async () => {
    stubFetch((path) => path.endsWith("/summary") ? programSummary() : path.endsWith("/dirs") ? {
      found: true, scan_id: 65, total: 26, noise: 24, significant: 2, blocked_only: ["only403.acme.com"],
      hosts: [{ host: "rpc.acme.com", total: 26, noise: 24, by_status: { "200": 1, "301": 1 },
                significant: [{ url: "https://rpc.acme.com/admin", status: 200, length: 812 }, { url: "https://rpc.acme.com/api", status: 301, length: 0 }] }],
    } : { scans: [] });
    location.hash = "/program/acme/data?v=dirs";
    render(<App />);
    expect(await screen.findByTestId("dirs-summary")).toHaveTextContent("26 phản hồi trên 1 host; 24 giống hệt nhau");
    expect(screen.getByTestId("dirs-blocked-only")).toHaveTextContent("only403.acme.com");
    expect(screen.getByText("https://rpc.acme.com/admin")).toBeInTheDocument();
  });

  test("Ports/Dirs: a chosen older scan is forwarded to the API, not silently shown as 'latest' (V164_HOST_AUDIT.md)", async () => {
    const fetch = stubFetch((path) => path.endsWith("/summary") ? programSummary() : path.includes("/ports") ? {
      found: true, scan_id: 31, hosts: 1, unique_ports: 1, complete: true, files: [],
      rows: [{ host: "old.acme.com", ip: "192.0.2.1", port: 22, proto: "tcp", service: "ssh", version: "" }], cdn: [], cdn_hosts: [], cdn_pairs: 0,
    } : { scans: [] });
    location.hash = "/program/acme/data?v=ports&scan=31";
    render(<App />);
    expect(await screen.findByTestId("ports-scan")).toHaveTextContent("scan #31");
    await waitFor(() => expect(fetch.mock.calls.some((c) => String(c[0]).includes("/ports?") && String(c[0]).includes("scan=31"))).toBe(true));
  });
});
