import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, go, type Config } from "./api";

const terminalStatuses = new Set(["done", "done_partial", "failed", "cancelled"]);

function useData(path: string, revision = 0, pollMs = 0) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    setData(null);
    setError("");
    async function refresh() {
      let finished = false;
      try {
        const result = await api(path, { signal: controller.signal });
        if (!live) return;
        setData(result);
        setError("");
        finished = terminalStatuses.has(result?.status);
      } catch (e: any) {
        if (live) setError(e.message);
      } finally {
        if (live && pollMs && !finished) timer = setTimeout(refresh, pollMs);
      }
    }
    void refresh();
    return () => {
      live = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [path, revision, pollMs]);
  return { data, error };
}
const ErrorBox = ({ text }: { text: string }) =>
  text ? (
    <div role="alert" className="error">
      {text}
    </div>
  ) : null;
export function Badge({ children }: { children: any }) {
  return (
    <span className={"badge " + String(children).toLowerCase()}>
      {children}
    </span>
  );
}
function State({
  data,
  error,
  children,
}: {
  data: any;
  error: string;
  children: any;
}) {
  if (error) return <ErrorBox text={error} />;
  if (data === null) return <p role="status">Đang tải…</p>;
  return children;
}

export function AssetTable({ rows }: { rows: any[] }) {
  return rows.length ? (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Host</th>
            <th>Rank</th>
            <th>Status</th>
            <th>Tech</th>
            <th>Lý do</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <strong>{r.host}</strong>
                <small>{r.title}</small>
              </td>
              <td>
                <Badge>{r.rank_score ?? 0}</Badge>
              </td>
              <td>{r.status_code || "—"}</td>
              <td>
                {(r.tech || []).map((t: string) => (
                  <Badge key={t}>{t}</Badge>
                ))}
              </td>
              <td>{(r.reasons || []).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="empty">Chưa có asset phù hợp.</p>
  );
}

function Portfolio() {
  const { data, error } = useData("/api/programs");
  const health = useData("/api/health");
  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">ATTACK SURFACE MANAGEMENT</p>
          <h1>Portfolio</h1>
          <p>Theo dõi thay đổi. Bắt đầu từ đúng scope.</p>
        </div>
        <a className="button" href="#/new">
          + New scan
        </a>
      </div>
      <State data={data} error={error}>
        <div className="metrics">
          <div>
            <strong>{data?.length || 0}</strong>Programs
          </div>
          <div>
            <strong>
              {data?.reduce((n: number, p: any) => n + p.asset_count, 0) || 0}
            </strong>
            Active assets
          </div>
          <div>
            <strong>
              {data?.reduce((n: number, p: any) => n + p.new_count, 0) || 0}
            </strong>
            New assets
          </div>
        </div>
        <div className="grid">
          {data?.map((p: any) => (
            <a className="card program" href={"#/target/" + p.slug} key={p.id}>
              <div>
                <Badge>{p.source}</Badge>
                <Badge>{p.latest_scan?.status || "no scans"}</Badge>
              </div>
              <h2>{p.slug}</h2>
              <p>
                {p.asset_count} assets{" "}
                <span className="accent">+{p.new_count} NEW</span>
              </p>
              <small>
                Scan #{p.latest_scan?.id || "—"} · {p.latest_scan?.depth || "—"}
              </small>
            </a>
          ))}
        </div>
        {data?.length === 0 && (
          <div className="empty">
            Chưa có program. Tạo scan để resolve scope trước khi launch.
          </div>
        )}
      </State>
      <details className="card">
        <summary>Tool health</summary>
        <ErrorBox text={health.error} />
        {Object.entries(health.data?.tools || {}).map(([name, ok]) => (
          <Badge key={name}>{name + ": " + (ok ? "ready" : "missing")}</Badge>
        ))}
      </details>
    </>
  );
}

export function ScanNew() {
  const [mode, setMode] = useState("raw"),
    [input, setInput] = useState(""),
    [scope, setScope] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function resolve(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api("/api/scope/resolve", {
        method: "POST",
        body: JSON.stringify({
          input: mode === "raw" ? "raw" : input,
          scope: mode === "raw" ? scope.split("\n") : [],
        }),
      });
      go("/scan/" + result.scan_id + "/review");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>New scan</h1>
      <p>Resolve scope trước. Kiểm tra cấu hình rồi mới chạy recon.</p>
      <form className="card form" onSubmit={resolve}>
        <label>
          Nguồn
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="raw">Raw scope</option>
            <option value="h1">HackerOne</option>
          </select>
        </label>
        {mode === "raw" ? (
          <label>
            Scope — mỗi dòng một asset
            <textarea
              required
              rows={9}
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              placeholder={"*.example.com\n127.0.0.1\n# OUT\nadmin.example.com"}
            />
          </label>
        ) : (
          <label>
            HackerOne handle hoặc URL
            <input
              required
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="h1:program"
            />
          </label>
        )}
        <ErrorBox text={error} />
        <button disabled={busy}>
          {busy ? "Đang resolve…" : "Resolve & review"}
        </button>
      </form>
    </>
  );
}

function Review({ id }: { id: string }) {
  const state = useData("/api/scans/" + id);
  const [config, setConfig] = useState<Config | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Config>("/api/scans/" + id + "/config")
      .then(setConfig)
      .catch((e) => setError(e.message));
  }, [id]);
  const edit = (key: keyof Config, value: any) =>
    setConfig((c) => (c ? { ...c, [key]: value } : c));
  async function launch() {
    if (!config) return;
    setBusy(true);
    setError("");
    try {
      await api("/api/scans/" + id + "/launch", {
        method: "POST",
        body: JSON.stringify({ config }),
      });
      go("/scan/" + id);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  const entries = state.data
    ? JSON.parse(state.data.stats_json || "{}").resolved_scope || []
    : [];
  return (
    <>
      <p className="eyebrow">RESOLVE → REVIEW → LAUNCH</p>
      <h1>Review scan #{id}</h1>
      <ErrorBox text={error || state.error} />
      {!config ? (
        <p>Đang tải cấu hình…</p>
      ) : (
        <div className="review-grid">
          <section className="card form">
            <label>
              Depth
              <select
                aria-label="Depth"
                value={config.depth}
                onChange={(e) => {
                  const d = e.target.value as Config["depth"];
                  setConfig({
                    ...config,
                    depth: d,
                    scan_timeout: { passive: 300, light: 900, strong: 2700 }[d],
                    skip_nmap: d !== "strong",
                    skip_nuclei: d === "passive",
                    skip_active_crawl: d === "passive",
                    nuclei_severity: {
                      passive: "",
                      light: "low,medium",
                      strong: "low,medium,high,critical",
                    }[d],
                  });
                }}
              >
                {["passive", "light", "strong"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            {(["threads", "rate_limit", "scan_timeout"] as const).map((key) => (
              <label key={key}>
                {key}
                <input
                  type="number"
                  min="1"
                  value={config[key]}
                  onChange={(e) => edit(key, Number(e.target.value))}
                />
              </label>
            ))}
            <label>
              Nuclei severity
              <input
                value={config.nuclei_severity}
                onChange={(e) => edit("nuclei_severity", e.target.value)}
              />
            </label>
            {(["skip_nmap", "skip_nuclei", "skip_active_crawl"] as const).map(
              (key) => (
                <label className="check" key={key}>
                  <input
                    type="checkbox"
                    checked={config[key]}
                    onChange={(e) => edit(key, e.target.checked)}
                  />
                  {key}
                </label>
              ),
            )}
            <label>
              Excluded hosts
              <textarea
                value={config.excluded_hosts.join("\n")}
                onChange={(e) =>
                  edit(
                    "excluded_hosts",
                    e.target.value.split("\n").filter(Boolean),
                  )
                }
              />
            </label>
          </section>
          <section className="card">
            <h2>Scope đã resolve</h2>
            {Array.from(new Set(entries.map((e: any) => e.category))).map(
              (category) => (
                <div key={String(category)} className="scope-group">
                  <label className="check">
                    <input
                      type="checkbox"
                      disabled={["mobile", "other"].includes(String(category))}
                      checked={config.categories_enabled.includes(
                        String(category),
                      )}
                      onChange={(e) =>
                        edit(
                          "categories_enabled",
                          e.target.checked
                            ? [...config.categories_enabled, category]
                            : config.categories_enabled.filter(
                                (c) => c !== category,
                              ),
                        )
                      }
                    />
                    <strong>{String(category)}</strong>
                  </label>
                  {entries
                    .filter((e: any) => e.category === category)
                    .map((entry: any) => (
                      <p key={entry.pattern + entry.kind}>
                        {entry.kind === "in" &&
                          !["mobile", "other"].includes(entry.category) && (
                            <input
                              type="checkbox"
                              aria-label={"Include " + entry.pattern}
                              checked={
                                !config.excluded_hosts.includes(entry.pattern)
                              }
                              onChange={(e) =>
                                edit(
                                  "excluded_hosts",
                                  e.target.checked
                                    ? config.excluded_hosts.filter(
                                        (h) => h !== entry.pattern,
                                      )
                                    : [...config.excluded_hosts, entry.pattern],
                                )
                              }
                            />
                          )}
                        <Badge>{entry.kind}</Badge>
                        {entry.pattern}
                        {entry.instruction && (
                          <small>{entry.instruction}</small>
                        )}
                      </p>
                    ))}
                </div>
              ),
            )}
            <p className="muted">
              Mobile/other là manual. Kiểm tra cả IN và OUT trước khi launch.
            </p>
            {config.depth === "strong" && (
              <p className="error">
                Strong scan ồn ào; chỉ dùng khi scope cho phép active scan.
              </p>
            )}
            <button
              disabled={busy || state.data?.status !== "draft"}
              onClick={launch}
            >
              {busy ? "Đang launch…" : "Launch scan"}
            </button>
          </section>
        </div>
      )}
    </>
  );
}

export function ScanLog({ id, onDone, finished = false }: { id: string; onDone?: () => void; finished?: boolean }) {
  const finishedRef = useRef(finished);
  finishedRef.current = finished;
  const [events, setEvents] = useState<any[]>([]),
    [connection, setConnection] = useState("Đang kết nối");
  useEffect(() => {
    let stopped = false,
      after = 0,
      done = false,
      ws: WebSocket;
    let timer: ReturnType<typeof setTimeout>;
    function connect() {
      if (stopped) return;
      ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/scan/${id}?after=${after}`,
      );
      ws.onopen = () => setConnection("Live");
      ws.onmessage = (e) => {
        const event = JSON.parse(e.data);
        after = Math.max(after, event.id || 0);
        setEvents((list) => [...list, event].slice(-1000));
        if (event.type === "done") {
          done = true;
          setConnection(event.status);
          onDone?.();
        }
      };
      ws.onclose = () => {
        if (!stopped && !done && !finishedRef.current) {
          setConnection("Mất kết nối — đang thử lại");
          timer = setTimeout(() => { if (!finishedRef.current) connect(); }, 1500);
        }
      };
      ws.onerror = () => ws.close();
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [id]);
  return (
    <section className="card">
      <div className="split">
        <h2>Scan log</h2>
        <Badge>{connection}</Badge>
      </div>
      <div className="logs" role="log">
        {events.length === 0
          ? "Đang chờ log…"
          : events.map((e, i) => (
              <div key={i}>
                <span>{e.type}</span>{" "}
                {e.message || e.phase || e.status || JSON.stringify(e)}
              </div>
            ))}
      </div>
    </section>
  );
}
function ScanPage({ id }: { id: string }) {
  const [revision, setRevision] = useState(0);
  const state = useData("/api/scans/" + id, revision, 3000);
  const [error, setError] = useState("");
  return (
    <>
      <h1>Scan #{id}</h1>
      <ErrorBox text={error || state.error} />
      <p>
        <span role="status" aria-label="Scan status"><Badge>{state.data?.status || "loading"}</Badge></span>{" "}
        <button
          className="secondary"
          disabled={terminalStatuses.has(state.data?.status)}
          onClick={() =>
            api("/api/scans/" + id + "/cancel", { method: "POST" })
              .then(() => setRevision((v) => v + 1))
              .catch((e) => setError(e.message))
          }
        >
          Cancel scan
        </button>{" "}
        <a href="#/">Portfolio →</a>
      </p>
      <ScanLog id={id} finished={terminalStatuses.has(state.data?.status)} onDone={() => setRevision((v) => v + 1)} />
    </>
  );
}

function Target({ slug }: { slug: string }) {
  const [tab, setTab] = useState("Overview"),
    [revision, setRevision] = useState(0),
    [error, setError] = useState(""),
    [include, setInclude] = useState(true),
    [edit, setEdit] = useState(""),
    [interval, setInterval] = useState("daily");
  const base = "/api/programs/" + encodeURIComponent(slug);
  const detail = useData(base, revision);
  const endpoint =
    tab === "Overview"
      ? base
      : tab === "Brief"
        ? base + "/brief"
        : tab === "Program"
          ? base + "/program"
          : base + "/" + tab.toLowerCase();
  const content = useData(endpoint, revision);
  useEffect(() => {
    if (tab === "Program" && typeof content.data === "string")
      setEdit(
        content.data
          .split("<!-- user-editable -->")[1]
          ?.split("<!-- /user-editable -->")[0]
          ?.trim() || "",
      );
  }, [tab, content.data]);
  async function action(fn: () => Promise<any>) {
    setError("");
    try {
      await fn();
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">PROGRAM</p>
          <h1>{slug}</h1>
          <p>
            {detail.data?.source} · {detail.data?.scans?.length || 0} scans
          </p>
        </div>
        <div>
          <label className="check">
            <input
              type="checkbox"
              checked={include}
              onChange={(e) => setInclude(e.target.checked)}
            />
            Include raw recon
          </label>
          <a
            className="button"
            href={base + "/export?include_recon=" + include}
          >
            Export ZIP ↓
          </a>
        </div>
      </div>
      <nav className="tabs">
        {[
          "Overview",
          "Surface",
          "Assets",
          "Diff",
          "Findings",
          "Brief",
          "Program",
        ].map((t) => (
          <button
            className={t === tab ? "active" : "secondary"}
            key={t}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </nav>
      <ErrorBox text={error} />
      <State data={content.data} error={content.error}>
        {tab === "Overview" ? (
          <div className="review-grid">
            <section className="card">
              <h2>Scans</h2>
              {detail.data?.scans?.map((s: any) => (
                <p key={s.id}>
                  <a href={"#/scan/" + s.id}>
                    #{s.id} · {s.depth}
                  </a>{" "}
                  <Badge>{s.status}</Badge>
                </p>
              ))}
              {detail.data?.scans?.length === 0 && <p>Chưa có scan.</p>}
            </section>
            <section className="card form">
              <h2>Continuous monitoring</h2>
              <p>Chạy theo cấu hình đã lưu, không qua review từng lần.</p>
              <select
                aria-label="Interval"
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
              >
                <option value="6h">Every 6 hours</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
              <button
                onClick={() =>
                  action(() =>
                    api(base + "/schedule", {
                      method: "POST",
                      body: JSON.stringify({
                        interval,
                        depth: detail.data?.scans?.[0]?.depth || "light",
                        enabled: !detail.data?.schedule?.enabled,
                      }),
                    }),
                  )
                }
              >
                {detail.data?.schedule?.enabled
                  ? "Disable monitoring"
                  : "Enable monitoring"}
              </button>
              <small>Next: {detail.data?.schedule?.next_run_at || "—"}</small>
            </section>
          </div>
        ) : tab === "Surface" || tab === "Assets" ? (
          <AssetTable rows={content.data || []} />
        ) : tab === "Brief" || tab === "Program" ? (
          <section className="card markdown">
            {tab === "Brief" ? (
              <>
                <button
                  onClick={() =>
                    action(() => api(base + "/brief", { method: "POST" }))
                  }
                >
                  Regenerate brief
                </button>
                <button
                  className="secondary"
                  onClick={() =>
                    action(async () => {
                      const r = await api(base + "/brief", { method: "POST" });
                      await navigator.clipboard.writeText(
                        "cd " +
                          JSON.stringify(
                            r.path.replace(/[\\/]AGENT_BRIEF.md$/, ""),
                          ),
                      );
                    })
                  }
                >
                  Copy target path
                </button>
              </>
            ) : (
              <>
                <label>
                  Phần user-editable
                  <textarea
                    rows={5}
                    value={edit}
                    onChange={(e) => setEdit(e.target.value)}
                  />
                </label>
                <button
                  onClick={() =>
                    action(() =>
                      api(base + "/program", {
                        method: "PUT",
                        body: JSON.stringify({ content: edit }),
                      }),
                    )
                  }
                >
                  Save instructions
                </button>
              </>
            )}
            <ReactMarkdown>
              {typeof content.data === "string" ? content.data : ""}
            </ReactMarkdown>
          </section>
        ) : (
          <section className="card">
            {content.data?.length === 0 ? (
              <p className="empty">Chưa có dữ liệu.</p>
            ) : (
              content.data?.map((r: any) => (
                <div className="finding" key={r.id}>
                  <Badge>{r.change || r.severity}</Badge>
                  <strong>{r.entity_ref || r.name}</strong>
                  <small>{r.type || r.entity}</small>
                  <pre>{JSON.stringify(r.detail, null, 2)}</pre>
                </div>
              ))
            )}
          </section>
        )}
      </State>
    </>
  );
}

export function App() {
  const [route, setRoute] = useState(location.hash.slice(1) || "/"),
    [dark, setDark] = useState(localStorage.getItem("theme") !== "light");
  useEffect(() => {
    const update = () => setRoute(location.hash.slice(1) || "/");
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  const parts = route.split("/");
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="#/">
          ◈ BBASM<span>Attack surface workspace</span>
        </a>
        <nav>
          <a href="#/">▦ Portfolio</a>
          <a href="#/new">＋ New scan</a>
        </nav>
        <div className="sidebar-bottom">
          <p>
            Scope first.
            <br />
            Hunt with context.
          </p>
          <button className="secondary" onClick={() => setDark(!dark)}>
            {dark ? "☀ Light mode" : "☾ Dark mode"}
          </button>
        </div>
      </aside>
      <main>
        {parts[1] === "new" ? (
          <ScanNew />
        ) : parts[1] === "scan" && parts[3] === "review" ? (
          <Review key={route} id={parts[2]} />
        ) : parts[1] === "scan" ? (
          <ScanPage key={route} id={parts[2]} />
        ) : parts[1] === "target" ? (
          <Target key={route} slug={decodeURIComponent(parts[2])} />
        ) : (
          <Portfolio />
        )}
        <footer>
          BBASM · Resolve → review → launch · Agent bridge creates folders only
        </footer>
      </main>
    </div>
  );
}
