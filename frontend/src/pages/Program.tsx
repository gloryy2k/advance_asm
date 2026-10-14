import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, apiPage } from "../api/client";
import type { Asset, Depth, Summary } from "../api/types";
import { HuntCard } from "../components/HuntCard";
import { Badge, CopyButton, EmptyState, ErrorBox, Loading, Pager, SeverityBadge, State, StatusBadge } from "../components/ui";
import { useData } from "../hooks/useData";
import { explain } from "../lib/errors";
import { go, programPath, TABS } from "../lib/router";
import { PRESETS } from "../lib/presets";
import { when } from "../lib/format";

const TAB_LABEL: Record<string, string> = {
  overview: "Overview",
  surface: "Surface",
  assets: "Assets",
  diff: "Diff",
  findings: "Findings",
  brief: "Brief",
  program: "Program",
};
const REASON_LABEL: Record<string, string> = {
  api: "API",
  auth: "đăng nhập/auth",
  fresh: "mới",
  tech_risk: "tech rủi ro",
  nuclei_medium_plus: "nuclei medium+",
  nuclei_low: "nuclei low",
  status_200: "HTTP 200",
  status_restricted: "401/403",
  nonproduction: "dev/staging",
};
const reasonText = (r: string) => REASON_LABEL[r] || r;

export function useAssets(path: string, revision = 0) {
  const [state, setState] = useState<{ items: Asset[]; total: number } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    setError("");
    apiPage<Asset>(path)
      .then((r) => live && setState(r))
      .catch((e) => live && setError(explain(e)));
    return () => {
      live = false;
    };
  }, [path, revision]);
  return { state, error };
}

export function AssetTable({ rows }: { rows: Asset[] }) {
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
                {r.category && r.category !== "web" && <Badge>{r.category}</Badge>}
                {r.title && <small>{r.title}</small>}
              </td>
              <td><Badge tone="rank">{r.rank_score ?? 0}</Badge></td>
              <td>{r.status_code || "—"}</td>
              <td>{(r.tech || []).map((t) => <Badge key={t}>{t}</Badge>)}</td>
              <td>{(r.reasons || []).map(reasonText).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="empty">Chưa có asset phù hợp.</p>
  );
}

function changeText(row: any): string {
  const d = row.detail || {};
  if (row.change === "new") {
    const a = d.after || {};
    return [a.status_code ? `HTTP ${a.status_code}` : "", (a.tech || []).join(", ")].filter(Boolean).join(" · ") || "xuất hiện lần đầu";
  }
  if (row.change === "gone") return "không còn xuất hiện trong scan hoàn tất";
  return Object.entries(d)
    .map(([k, v]: [string, any]) => {
      if (k === "tech") {
        const before = new Set<string>(v.before || []), after = new Set<string>(v.after || []);
        const plus = [...after].filter((x) => !before.has(x)), minus = [...before].filter((x) => !after.has(x));
        return "tech " + [plus.length ? "+" + plus.join(",") : "", minus.length ? "−" + minus.join(",") : ""].filter(Boolean).join(" ");
      }
      return `${k}: ${v?.before ?? "—"} → ${v?.after ?? "—"}`;
    })
    .join("; ");
}

function Overview({ slug, summary, detail, reload }: { slug: string; summary: Summary; detail: any; reload: () => void }) {
  const [interval, setInterval] = useState(summary.schedule?.interval || "daily");
  const [depth, setDepth] = useState<Depth>(summary.schedule?.depth || summary.last_completed_scan?.depth || "light");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState("");
  const enabled = !!summary.schedule?.enabled;
  const base = "/api/programs/" + encodeURIComponent(slug);
  async function schedule(on: boolean) {
    setError("");
    try {
      await api(base + "/schedule", { method: "POST", body: JSON.stringify({ interval, depth, enabled: on }) });
      setAck(false);
      reload();
    } catch (e) {
      setError(explain(e));
    }
  }
  const scans: any[] = detail?.scans || [];
  const c = summary.changes;
  const total = Object.values(summary.findings_by_severity).reduce((a, b) => a + b, 0);
  return (
    <>
      <div className="metrics four">
        <div><strong>{summary.assets_active}</strong>Asset hoạt động</div>
        <div><strong>{c.new}</strong>Mới</div>
        <div><strong>{c.changed}</strong>Thay đổi</div>
        <div><strong>{c.gone}</strong>Biến mất</div>
      </div>
      <div className="review-grid">
        <section className="card">
          <h2>Top 5 surface</h2>
          {summary.top_surface.length === 0 ? (
            <p className="muted">Chưa có dữ liệu — chạy một scan hoàn tất.</p>
          ) : (
            <ol className="toplist">
              {summary.top_surface.map((a) => (
                <li key={a.id}>
                  <strong>{a.host}</strong> <Badge tone="rank">{a.rank_score ?? 0}</Badge>
                  <small>{(a.reasons || []).map(reasonText).join(", ")}</small>
                </li>
              ))}
            </ol>
          )}
          <a href={"#" + programPath(slug, "surface")}>Xem toàn bộ surface →</a>
        </section>
        <section className="card">
          <h2>Findings ({total})</h2>
          {total === 0 ? <p className="muted">Chưa có finding.</p> : (
            <p>{(["critical", "high", "medium", "low", "info"] as const).filter((s) => summary.findings_by_severity[s]).map((s) => (
              <span key={s}><SeverityBadge severity={s} /> {summary.findings_by_severity[s]} </span>
            ))}</p>
          )}
          <a href={"#" + programPath(slug, "findings")}>Xem findings →</a>
        </section>
        <section className="card">
          <h2>Scans</h2>
          {scans.length === 0 && <p className="muted">Chưa có scan.</p>}
          {scans.slice(0, 8).map((s) => (
            <p key={s.id}>
              <a href={s.status === "draft" ? "#/scan/" + s.id + "/review" : "#/scan/" + s.id}>#{s.id} · {s.depth}</a>{" "}
              <StatusBadge status={s.status} /> <small className="inline">{when(s.finished_at || s.started_at)}</small>
            </p>
          ))}
        </section>
        <section className="card form">
          <h2>Giám sát liên tục</h2>
          <p className="muted">
            {enabled
              ? `Đang bật (${summary.schedule!.interval}, mức ${summary.schedule!.depth}). Lần kế tiếp: ${when(summary.schedule!.next_run_at)}.`
              : "Tự quét lại theo lịch với scope hiện hành, không qua review từng lần; chỉ bật cho program cho phép automation."}
          </p>
          <ErrorBox text={error} />
          <label>
            Tần suất
            <select aria-label="Interval" value={interval} onChange={(e) => setInterval(e.target.value)}>
              <option value="6h">Mỗi 6 giờ</option>
              <option value="daily">Hằng ngày</option>
              <option value="weekly">Hằng tuần</option>
            </select>
          </label>
          <label>
            Mức quét
            <select aria-label="Monitoring depth" value={depth} onChange={(e) => { setDepth(e.target.value as Depth); setAck(false); }}>
              {PRESETS.map((p) => <option key={p.depth} value={p.depth}>{p.title} — {p.eta}</option>)}
            </select>
          </label>
          {depth !== "passive" && (
            <label className="check">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              Program cho phép scan tự động theo lịch ở mức này.
            </label>
          )}
          <div className="actions">
            <button disabled={depth !== "passive" && !ack} onClick={() => schedule(true)}>{enabled ? "Cập nhật lịch" : "Bật giám sát"}</button>
            {enabled && <button className="secondary" onClick={() => schedule(false)}>Tắt giám sát</button>}
          </div>
        </section>
      </div>
    </>
  );
}

function AssetsTab({ base, kind }: { base: string; kind: "surface" | "assets" }) {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [category, setCategory] = useState("");
  const [state, setState] = useState("active");
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => { setTerm(q); setOffset(0); }, 300);
    return () => clearTimeout(t);
  }, [q]);
  const limit = kind === "surface" ? 25 : 50;
  const params = new URLSearchParams({ limit: String(limit), offset: String(kind === "surface" ? 0 : offset) });
  const path = kind === "surface"
    ? base + "/surface?" + params
    : base + "/assets?" + new URLSearchParams([...params, ["state", state], ...(term ? [["q", term]] : []), ...(category ? [["category", category]] : [])] as [string, string][]);
  const result = useAssets(path);
  return (
    <>
      {kind === "assets" && (
        <div className="filters">
          <input aria-label="Tìm host" placeholder="Tìm host…" value={q} onChange={(e) => setQ(e.target.value)} />
          <select aria-label="Nhóm" value={category} onChange={(e) => { setCategory(e.target.value); setOffset(0); }}>
            <option value="">Mọi nhóm</option>
            {["web", "wildcard", "ip", "cidr", "source_code"].map((c) => <option key={c}>{c}</option>)}
          </select>
          <select aria-label="Trạng thái" value={state} onChange={(e) => { setState(e.target.value); setOffset(0); }}>
            <option value="active">Đang hoạt động</option>
            <option value="gone">Đã biến mất</option>
          </select>
        </div>
      )}
      <State data={result.state} error={result.error}>
        <AssetTable rows={result.state?.items || []} />
        {kind === "assets" && <Pager total={result.state?.total || 0} limit={limit} offset={offset} onChange={setOffset} />}
      </State>
    </>
  );
}

function DiffTab({ base }: { base: string }) {
  const [change, setChange] = useState("");
  const [offset, setOffset] = useState(0);
  const path = base + "/diff?" + new URLSearchParams({ limit: "50", offset: String(offset), ...(change ? { change } : {}) });
  const result = useAssets(path);
  return (
    <>
      <div className="filters" role="group" aria-label="Lọc thay đổi">
        {[["", "Tất cả"], ["new", "Mới"], ["changed", "Thay đổi"], ["gone", "Biến mất"]].map(([v, label]) => (
          <button key={v} className={change === v ? "active small" : "secondary small"} onClick={() => { setChange(v); setOffset(0); }}>{label}</button>
        ))}
      </div>
      <State data={result.state} error={result.error}>
        {(result.state?.items.length || 0) === 0 ? (
          <EmptyState title="Không có thay đổi">Diff xuất hiện sau khi program có từ hai scan hoàn tất.</EmptyState>
        ) : (
          <section className="card">
            {(result.state!.items as any[]).map((r) => (
              <div className="finding" key={r.id}>
                <Badge tone={r.change}>{{ new: "MỚI", changed: "THAY ĐỔI", gone: "BIẾN MẤT" }[r.change as string] || r.change}</Badge>
                <strong>{r.entity_ref}</strong>
                <small>{changeText(r)}</small>
              </div>
            ))}
            <Pager total={result.state!.total} limit={50} offset={offset} onChange={setOffset} />
          </section>
        )}
      </State>
    </>
  );
}

function FindingsTab({ base }: { base: string }) {
  const [severity, setSeverity] = useState("");
  const [type, setType] = useState("");
  const [offset, setOffset] = useState(0);
  const result = useAssets(base + "/findings?" + new URLSearchParams({ limit: "50", offset: String(offset), ...(severity ? { severity } : {}), ...(type ? { type } : {}) }));
  return (
    <>
      <div className="filters">
        <select aria-label="Mức nghiêm trọng" value={severity} onChange={(e) => { setSeverity(e.target.value); setOffset(0); }}>
          <option value="">Mọi mức</option>
          {["critical", "high", "medium", "low", "info"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <select aria-label="Loại" value={type} onChange={(e) => { setType(e.target.value); setOffset(0); }}>
          <option value="">Mọi loại</option>
          {["nuclei", "takeover", "secret", "js-endpoint"].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <State data={result.state} error={result.error}>
        {(result.state?.items.length || 0) === 0 ? (
          <EmptyState title="Chưa có finding">Finding xuất hiện khi nuclei/takeover/secrets tìm thấy kết quả.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Mức</th><th>Tên</th><th>Loại</th><th>Asset</th><th>Chi tiết</th></tr></thead>
              <tbody>
                {(result.state!.items as any[]).map((f) => (
                  <tr key={f.id}>
                    <td><SeverityBadge severity={f.severity} /></td>
                    <td><strong>{f.name}</strong></td>
                    <td>{f.type}</td>
                    <td>{f.host || "—"}</td>
                    <td>{f.detail?.matched_at || (f.detail?.verified ? "đã xác minh" : "") || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager total={result.state!.total} limit={50} offset={offset} onChange={setOffset} />
          </div>
        )}
      </State>
    </>
  );
}

function BriefTab({ base, slug, summary }: { base: string; slug: string; summary: Summary }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const brief = useData<string>(base + "/brief", revision);
  async function regenerate() {
    setError("");
    try {
      await api(base + "/brief", { method: "POST" });
      setRevision((v) => v + 1);
    } catch (e) {
      setError(explain(e));
    }
  }
  if (brief.code === "no_completed_scan")
    return (
      <EmptyState title="Chưa có brief" action={<a className="button" href="#/new">Tạo scan</a>}>
        Brief được sinh sau scan hoàn tất đầu tiên. Bạn vẫn có thể sửa PROGRAM.md ở tab Program ngay bây giờ.
      </EmptyState>
    );
  const text = typeof brief.data === "string" ? brief.data : "";
  return (
    <section className="card markdown">
      <div className="actions">
        <button onClick={regenerate}>Tạo lại brief</button>
        <CopyButton text={summary.hunt_command} label="Sao chép lệnh hunt" />
        {text && <span className="muted">{new Blob([text]).size.toLocaleString("vi-VN")} / 12.000 byte</span>}
      </div>
      <ErrorBox text={error} />
      <State data={brief.data} error={brief.error}>
        <ReactMarkdown>{text}</ReactMarkdown>
      </State>
    </section>
  );
}

function ProgramTab({ base }: { base: string }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const doc = useData<string>(base + "/program", revision);
  const original = typeof doc.data === "string"
    ? doc.data.split("<!-- user-editable -->")[1]?.split("<!-- /user-editable -->")[0]?.trim() || ""
    : "";
  const [edit, setEdit] = useState("");
  useEffect(() => setEdit(original), [original]);
  const dirty = edit !== original;
  async function save() {
    setError("");
    try {
      await api(base + "/program", { method: "PUT", body: JSON.stringify({ content: edit }) });
      setSaved(true);
      setRevision((v) => v + 1);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(explain(e));
    }
  }
  return (
    <section className="card markdown">
      <label>
        Ghi chú của bạn (auth, OOS, severity guideline…) — phần duy nhất được sửa
        <textarea rows={6} value={edit} onChange={(e) => setEdit(e.target.value)} />
      </label>
      <div className="actions">
        <button onClick={save} disabled={!dirty}>Save instructions</button>
        {dirty && <span className="muted">Chưa lưu</span>}
        {saved && <span className="okline">Đã lưu ✓</span>}
      </div>
      <ErrorBox text={error} />
      <State data={doc.data} error={doc.error}>
        <ReactMarkdown>{typeof doc.data === "string" ? doc.data : ""}</ReactMarkdown>
      </State>
    </section>
  );
}

export function Program({ slug, tab }: { slug: string; tab: string }) {
  const [revision, setRevision] = useState(0);
  const [include, setInclude] = useState(true);
  const [error, setError] = useState("");
  const base = "/api/programs/" + encodeURIComponent(slug);
  const summary = useData<Summary>(base + "/summary", revision);
  const detail = useData<any>(base, revision);

  async function rescan() {
    try {
      const made = await api(base + "/rescan", { method: "POST" });
      go("/scan/" + made.scan_id + "/review");
    } catch (e) {
      setError(explain(e));
    }
  }
  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">PROGRAM</p>
          <h1>{slug}</h1>
          <p>
            {summary.data?.source} · <StatusBadge status={summary.data?.latest_scan?.status} />
            {summary.data?.latest_scan && <> scan #{summary.data.latest_scan.id} · {summary.data.latest_scan.depth}</>}
          </p>
        </div>
        <div className="head-actions">
          <button onClick={rescan}>Scan lại</button>
          <details className="menu">
            <summary className="button secondary">Export ▾</summary>
            <div className="card">
              <label className="check">
                <input type="checkbox" checked={include} onChange={(e) => setInclude(e.target.checked)} />
                Kèm raw recon (lớn hơn)
              </label>
              <a className="button" href={base + "/export?include_recon=" + include}>Tải ZIP ↓</a>
            </div>
          </details>
        </div>
      </div>
      <ErrorBox text={error} />
      {summary.data?.last_completed_scan && <HuntCard command={summary.data.hunt_command} note={summary.data.hunt_note} />}
      <nav className="tabs" role="tablist" aria-label="Program">
        {TABS.map((t) => (
          <a key={t} role="tab" aria-selected={t === tab} className={t === tab ? "tab active" : "tab"} href={"#" + programPath(slug, t)}>
            {TAB_LABEL[t]}
          </a>
        ))}
      </nav>
      {tab === "overview" ? (
        <State data={summary.data} error={summary.error} retry={() => setRevision((v) => v + 1)}>
          {summary.data && <Overview slug={slug} summary={summary.data} detail={detail.data} reload={() => setRevision((v) => v + 1)} />}
        </State>
      ) : tab === "surface" || tab === "assets" ? (
        <AssetsTab key={tab} base={base} kind={tab} />
      ) : tab === "diff" ? (
        <DiffTab base={base} />
      ) : tab === "findings" ? (
        <FindingsTab base={base} />
      ) : tab === "brief" ? (
        summary.data ? <BriefTab base={base} slug={slug} summary={summary.data} /> : <Loading />
      ) : (
        <ProgramTab base={base} />
      )}
    </>
  );
}
