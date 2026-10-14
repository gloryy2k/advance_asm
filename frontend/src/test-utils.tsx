import { vi } from "vitest";

type Reply = unknown | { __error: { status: number; code?: string; message: string } } | { __total: number; body: unknown };

/** Route-table fetch stub: handler(path, init) returns the body (object → JSON, string → text). */
export function stubFetch(handler: (path: string, init?: RequestInit) => Reply) {
  const fn = vi.fn((path: string, init?: RequestInit) => {
    let reply: any = handler(path, init);
    // A handler that has no opinion about a path (undefined or {}) gets the realistic default shape.
    if (reply === undefined || (reply && typeof reply === "object" && !Array.isArray(reply) && Object.keys(reply).length === 0)) {
      reply = defaults(path, init) ?? reply;
    }
    if (reply instanceof Error) return Promise.reject(reply);
    if (reply?.__error) {
      const { status, code, message } = reply.__error;
      return Promise.resolve({
        ok: false,
        status,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ error: { code, message } }),
      });
    }
    const total = reply?.__total;
    const body = total !== undefined ? reply.body : reply;
    const isText = typeof body === "string";
    return Promise.resolve({
      ok: true,
      status: 200,
      headers: new Headers({
        "content-type": isText ? "text/markdown" : "application/json",
        ...(total !== undefined ? { "x-total-count": String(total) } : {}),
      }),
      json: async () => body,
      text: async () => body,
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const calls = (fn: ReturnType<typeof stubFetch>, suffix: string, method?: string) =>
  fn.mock.calls.filter(
    (c) => String(c[0]).endsWith(suffix) && (!method || (c[1] as RequestInit | undefined)?.method === method),
  );

export class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: any;
  onclose: any;
  onerror: any;
  onmessage: any;
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  emit(event: object) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

export const baseReview = (over: object = {}) => ({
  scan: { id: 4, depth: "light", status: "draft" },
  slug: "acme",
  source: "h1",
  handle: "acme",
  target_path: "/data/targets/acme",
  hunt_command: 'cd "/data/targets/acme" && claude',
  hunt_note: "",
  scope: [
    { pattern: "*.acme.com", kind: "in", asset_type: "WILDCARD", category: "wildcard", instruction: "Main" },
    { pattern: "api.acme.com", kind: "in", asset_type: "URL", category: "web", instruction: "" },
    { pattern: "10.0.0.0/24", kind: "in", asset_type: "CIDR", category: "cidr", instruction: "" },
    { pattern: "com.acme.app", kind: "in", asset_type: "mobile", category: "mobile", instruction: "" },
    { pattern: "legacy.acme.com", kind: "out", asset_type: "URL", category: "web", instruction: "retired" },
  ],
  trust: { level: "public", verified: false, label: "CHƯA XÁC MINH — dữ liệu công khai", detail: "Có thể đã cũ.", missing: ["policy đầy đủ"],
           checklist: ["Mở trang chính thức"], official_url: "https://hackerone.com/acme" },
  warnings: ["Dữ liệu từ nguồn công khai"],
  automation_ack: null,
  policy: { text: "No DoS. Automated scanning limited to 5 req/s.", source: "api", fetched_at: "2026-10-14T01:00:00Z", user_text: "" },
  stats: {},
  ...over,
});

export const health = (over: object = {}) => ({
  ok: true,
  tools: { nuclei: false, subfinder: true },
  missing_by_depth: { passive: [], light: ["nuclei"], strong: ["nuclei", "nmap"] },
  h1_api: false,
  ...over,
});

const recipe = (depth: string) => ({
  depth, threads: 50, rate_limit: 150,
  scan_timeout: { passive: 300, light: 900, strong: 2700 }[depth as "passive"],
  nuclei_severity: { passive: "", light: "low,medium", strong: "low,medium,high,critical" }[depth as "passive"],
  skip_nmap: depth !== "strong", skip_nuclei: depth === "passive", skip_active_crawl: depth === "passive", skip_ffuf: false,
  skip_historical: false, skip_takeover: false, skip_secrets: false, max_js_files: 100, url_exclude_patterns: [],
  brief_budget_kb: 12, brief_top_assets: 25, brief_top_urls: 12,
});
export const profilesReply = (custom: object[] = []) => ({
  builtin: ["passive", "light", "strong"].map((d) => ({ id: "builtin:" + d, name: d[0].toUpperCase() + d.slice(1), description: d, based_on: "", builtin: true, config: recipe(d) })),
  custom,
});
export const planReply = (over: Record<string, Partial<{ status: string; reason: string }>> = {}) => ({
  phases: [
    ["subdomain_enum", "Tìm subdomain", false, "hosts"], ["live_probe", "Probe HTTP", true, "hosts"], ["port_scan", "Quét cổng", true, "file"],
    ["url_history", "URL lịch sử", false, "urls"], ["url_crawl", "Crawl chủ động", true, "urls"], ["nuclei", "Nuclei", true, "findings"],
    ["takeover", "Takeover", true, "findings"], ["secrets", "Bí mật trong JS", true, "findings"],
  ].map(([key, title, touches, kind]) => ({ key, title, what: "mô tả " + title, touches, status: "on", reason: null, view: { kind, label: "Xem " + title }, forced: key === "port_scan", ...(over[key as string] || {}) })),
});
function defaults(path: string, init?: RequestInit): unknown {
  if (path === "/api/profiles") return profilesReply();
  if (path === "/api/meta/plan") return planReply();
  if (path === "/api/meta/phases") return planReply().phases.map((p) => ({ ...p, tools: [], count_label: "mục", files: [] }));
  if (/\/phases$/.test(path)) return { scan_id: 1, slug: "acme", status: "done", depth: "light", phases: [], funnel: null, missing_tools: [] };
  if (/\/urls\/summary$/.test(path)) return { scan_id: 1, total: 0, funnel: null, by_tag: {}, top_shapes: [], hosts: [] };
  if (/\/urls\?/.test(path)) return { __total: 0, body: [] };
  if (path === "/api/drafts") return [];
  return undefined;
}

export const baseConfig = { ...recipe("light"), categories_enabled: ["web", "wildcard"], excluded_hosts: [] as string[] };
