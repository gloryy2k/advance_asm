import { vi } from "vitest";

type Reply = unknown | { __error: { status: number; code?: string; message: string } } | { __total: number; body: unknown };

/** Route-table fetch stub: handler(path, init) returns the body (object → JSON, string → text). */
export function stubFetch(handler: (path: string, init?: RequestInit) => Reply) {
  const fn = vi.fn((path: string, init?: RequestInit) => {
    const reply: any = handler(path, init);
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

export const baseConfig = {
  depth: "light",
  threads: 50,
  rate_limit: 150,
  scan_timeout: 900,
  nuclei_severity: "low,medium",
  skip_nmap: true,
  skip_nuclei: false,
  skip_active_crawl: false,
  categories_enabled: ["web", "wildcard"],
  excluded_hosts: [],
};

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
