import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, apiPage } from "../api/client";
import type { Asset, ChartsData, DataNote, Depth, Profile, Summary, Trust, UrlSummary } from "../api/types";
import { Distributions, SeverityMatrix, TrendChart } from "../components/Charts";
import { AssetCoverageNote, ScanProgress } from "../components/ScanProgress";
import { HuntCard } from "../components/HuntCard";
import { Chip, PageHead, Panel, Segmented, TrustBadge } from "../components/layout";
import { ArchivedBanner } from "../components/ProgramLifecycle";
import { UrlExplorer } from "../components/UrlExplorer";
import { Badge, CopyButton, EmptyState, ErrorBox, Loading, Pager, SeverityBadge, State, StatusBadge } from "../components/ui";
import { useData } from "../hooks/useData";
import { explain } from "../lib/errors";
import { when } from "../lib/format";
import { PRESETS } from "../lib/presets";
import { TABS, go, programPath, routeParams } from "../lib/router";

const TAB_LABEL: Record<string, string> = {
  overview: "Tổng quan", data: "Dữ liệu", findings: "Phát hiện", history: "Lịch sử", guide: "Hướng dẫn & scope",
};
const TAB_HINT: Record<string, string> = {
  overview: "Kết quả chính và việc nên làm tiếp.",
  data: "Host, URL và xếp hạng bề mặt tấn công thu được từ các scan.",
  findings: "Lỗi/dấu hiệu do nuclei, takeover và quét bí mật tìm thấy.",
  history: "Các lần scan và thay đổi giữa hai lần scan hoàn tất.",
  guide: "Brief cho agent, hướng dẫn riêng, scope/policy và xuất file.",
};
const REASON_LABEL: Record<string, string> = {
  api: "API", auth: "đăng nhập/auth", fresh: "mới", tech_risk: "tech rủi ro", nuclei_medium_plus: "nuclei medium+", nuclei_low: "nuclei low",
  status_200: "HTTP 200", status_restricted: "401/403", nonproduction: "dev/staging",
};
const reasonText = (r: string) => REASON_LABEL[r] || r;

export function useAssets(path: string, revision = 0) {
  const [state, setState] = useState<{ items: Asset[]; total: number } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    setError("");
    apiPage<Asset>(path).then((r) => live && setState(r)).catch((e) => live && setError(explain(e)));
    return () => { live = false; };
  }, [path, revision]);
  return { state, error };
}

export function AssetTable({ rows }: { rows: Asset[] }) {
  return rows.length ? (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Bảng dữ liệu, cuộn được">
      <table>
        <thead><tr><th>Host</th><th>Rank</th><th>Status</th><th>Tech</th><th>Lý do</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td><strong>{r.host}</strong>{r.category && r.category !== "web" && <Badge>{r.category}</Badge>}{r.title && <small>{r.title}</small>}</td>
              <td><Badge tone="rank">{r.rank_score ?? 0}</Badge></td>
              <td>{r.status_code || <span className="muted" title="Chưa có phản hồi HTTP nào được ghi nhận (scan Passive không probe)">chưa có HTTP</span>}</td>
              <td>{(r.tech || []).map((t) => <Badge key={t}>{t}</Badge>)}</td>
              <td>{(r.reasons || []).map(reasonText).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : <p className="empty">Chưa có asset phù hợp.</p>;
}

function changeText(row: any): string {
  const d = row.detail || {};
  if (row.change === "new") {
    const a = d.after || {};
    return [a.status_code ? `HTTP ${a.status_code}` : "", (a.tech || []).join(", ")].filter(Boolean).join(" · ") || "xuất hiện lần đầu";
  }
  if (row.change === "gone") return "không còn xuất hiện trong scan hoàn tất";
  return Object.entries(d).map(([k, v]: [string, any]) => {
    if (k === "tech") {
      const before = new Set<string>(v.before || []), after = new Set<string>(v.after || []);
      const plus = [...after].filter((x) => !before.has(x)), minus = [...before].filter((x) => !after.has(x));
      return "tech " + [plus.length ? "+" + plus.join(",") : "", minus.length ? "−" + minus.join(",") : ""].filter(Boolean).join(" ");
    }
    return `${k}: ${v?.before ?? "—"} → ${v?.after ?? "—"}`;
  }).join("; ");
}

/* ───────────── Tổng quan ───────────── */
function Tile({ label, value, sub, href, tone }: { label: string; value: number | string; sub?: string; href: string; tone?: string }) {
  return (
    <a className={"tile " + (tone || "")} href={href}>
      <span className="tile-label">{label}</span>
      <strong>{value}</strong>
      {sub && <small>{sub}</small>}
      <span className="tile-go">Xem →</span>
    </a>
  );
}

function Overview({ slug, summary, detail, urls, reload }: { slug: string; summary: Summary & { trust?: Trust }; detail: any; urls: UrlSummary | null; reload: () => void }) {
  const [interval, setInterval] = useState(summary.schedule?.interval || "daily");
  const [depth, setDepth] = useState<Depth>(summary.schedule?.depth || summary.last_completed_scan?.depth || "light");
  const [ack, setAck] = useState(false);
  const [skipHeader, setSkipHeader] = useState(false);
  const [error, setError] = useState("");
  const charts = useData<ChartsData>(summary.last_completed_scan ? "/api/programs/" + encodeURIComponent(slug) + "/charts" : null);
  const enabled = !!summary.schedule?.enabled;
  // A schedule starts from the program's saved defaults (profile, header), exactly like a new draft does.
  const savedNames = (summary.request_headers || []).map((h) => h.split(":")[0].trim());
  const hintsOpen = depth === "passive" ? [] : (summary.request_header_hints || []).filter((n) => !savedNames.some((x) => x.toLowerCase() === n.toLowerCase()));
  const base = "/api/programs/" + encodeURIComponent(slug);
  async function schedule(on: boolean) {
    setError("");
    try {
      await api(base + "/schedule", { method: "POST", body: JSON.stringify({ interval, depth, enabled: on, automation_ack: on && depth !== "passive" && ack, skipped_headers: on && skipHeader ? hintsOpen : [] }) });
      setAck(false);
      setSkipHeader(false);
      reload();
    } catch (e) { setError(explain(e)); }
  }
  const c = summary.changes;
  // The first completed scan has nothing to be compared with: its "changes" are the initial inventory, not a difference.
  const firstScan = !!summary.last_completed_scan && (summary.last_completed_scan as any).baseline_scan_id == null;
  const total = Object.values(summary.findings_by_severity).reduce((a, b) => a + b, 0);
  const hotTags = [["api", "API"], ["admin", "quản trị"], ["sensitive", "nhạy cảm"], ["auth", "đăng nhập"]] as const;
  const tags = urls?.by_tag || {};
  const hot = hotTags.filter(([t]) => (tags[t] || 0) > 0).map(([t, label]) => `${label} ${tags[t].toLocaleString("vi-VN")}`);
  const todo: { text: string; href?: string }[] = [];
  if (!summary.last_completed_scan) todo.push({ text: "Chạy scan đầu tiên để có dữ liệu." });
  if (summary.trust && !summary.trust.verified && summary.trust.level === "public") todo.push({ text: "Đối chiếu scope và policy với trang chính thức (nguồn đang CHƯA XÁC MINH).", href: "#" + programPath(slug, "guide", "scope") });
  if (hot.length > 0) todo.push({ text: `Xem URL đáng chú ý: ${hot.join(" · ")}.`, href: `#/program/${encodeURIComponent(slug)}/data?v=urls&min_score=3` });
  if (total > 0) todo.push({ text: `Xem ${total} finding.`, href: "#" + programPath(slug, "findings") });
  if (c.new + c.changed + c.gone > 0) todo.push({ text: firstScan ? `Xem ${c.new + c.changed + c.gone} asset ghi nhận lần đầu (chưa có scan trước để so sánh).` : `Xem ${c.new + c.changed + c.gone} thay đổi so với scan trước.`, href: "#" + programPath(slug, "history", "diff") });
  if (summary.last_completed_scan && !enabled) todo.push({ text: "Bật giám sát nếu program cho phép quét tự động, để biết khi có asset mới." });
  const active = summary.latest_scan && ["queued", "running"].includes(summary.latest_scan.status) ? summary.latest_scan : null;
  const dataScan = summary.last_completed_scan;
  const dataStats = (dataScan as any)?.stats || {};
  return (
    <>
      {dataScan && (
        <p className={"databanner " + (active || dataScan.status === "done_partial" ? "warnbox" : "muted")} role="status" data-testid="data-scan">
          {active && <><strong>Scan #{active.id} ({active.depth}) đang {active.status === "queued" ? "chờ chạy" : "chạy"}</strong> — số liệu dưới đây vẫn là của </>}
          {!active && <>Số liệu dưới đây là của </>}
          <strong>scan #{dataScan.id}</strong> ({dataScan.depth}, {dataScan.status === "done_partial" ? "hoàn tất MỘT PHẦN" : "hoàn tất"}
          {dataScan.finished_at ? ` lúc ${when(dataScan.finished_at)}` : ""}).
          {active && " Kết quả của scan đang chạy chỉ xem được ở trang Run."}
          {dataScan.status === "done_partial" && dataStats.coverage?.unprobed > 0 && <> Còn {dataStats.coverage.unprobed.toLocaleString("vi-VN")} host khám phá chưa probe.</>}
          {" "}<a href={"#/scan/" + (active ? active.id : dataScan.id)}>Mở scan #{active ? active.id : dataScan.id} →</a>
        </p>
      )}
      {dataScan && dataScan.status !== "done_partial" && <AssetCoverageNote rows={dataStats.asset_coverage} />}
      {(summary.data_notes || []).length > 0 && (
        <div className="notice" role="note" data-testid="data-notes">
          <strong>Số liệu của scan này đã được tính lại sau khi nâng cấp:</strong>
          <ul>{summary.data_notes!.map((n, i) => <li key={i}>{n.note}</li>)}</ul>
        </div>
      )}
      {dataScan?.status === "done_partial" && <ScanProgress data={dataStats} partial />}
      <div className="tiles">
        <Tile label="Host" value={summary.assets_active} sub={summary.assets_live !== undefined ? `trong inventory · ${summary.assets_live} có HTTP · ${Math.max(0, summary.assets_active - summary.assets_live)} chưa probe${summary.assets_gone ? ` · ${summary.assets_gone} biến mất` : ""}` : "trong inventory"} href={`#/program/${encodeURIComponent(slug)}/data?v=hosts`} />
        <Tile label="URL" value={(urls?.total ?? 0).toLocaleString("vi-VN")} sub={urls?.funnel ? `${urls.funnel.out_of_scope.toLocaleString("vi-VN")} ngoài scope đã loại` : "trong scope"} href={`#/program/${encodeURIComponent(slug)}/data?v=urls`} />
        <Tile label="Findings" value={total} sub={total ? Object.entries(summary.findings_by_severity).filter(([, n]) => n).map(([s, n]) => `${n} ${s}`).join(" · ") : "chưa có"} href={"#" + programPath(slug, "findings")} tone={total ? "warn" : ""} />
        {firstScan
          ? <Tile label="Ghi nhận lần đầu" value={c.new + c.changed + c.gone} sub="dữ liệu khởi tạo — chưa có scan trước để so sánh" href={"#" + programPath(slug, "history", "diff")} />
          : <Tile label="Thay đổi" value={c.new + c.changed + c.gone} sub={`${c.new} mới · ${c.changed} đổi · ${c.gone} mất`} href={"#" + programPath(slug, "history", "diff")} />}
      </div>
      {todo.length > 0 && (
        <Panel id="todo-h" title="Việc nên làm tiếp">
          <ul className="todo">{todo.map((t) => <li key={t.text}>{t.href ? <a href={t.href}>{t.text}</a> : t.text}</li>)}</ul>
        </Panel>
      )}
      {summary.last_completed_scan && <HuntCard command={summary.hunt_command} note={summary.hunt_note} />}
      {charts.data && Array.isArray(charts.data.trend) && (
        <>
          <Panel id="trend-h" title="Xu hướng qua các scan" hint="Số liệu của từng scan hoàn tất (host live, URL, finding) và thay đổi so với scan trước nó.">
            <TrendChart trend={charts.data.trend} truncated={charts.data.truncated} />
          </Panel>
          <Panel id="dist-h" title="Bề mặt hiện tại" hint="Tính từ inventory đang theo dõi (host chưa biến mất).">
            <Distributions data={charts.data} />
          </Panel>
          <Panel id="matrix-h" title="Finding theo host × mức nghiêm trọng" hint="Tối đa 8 host nhiều finding nhất.">
            <SeverityMatrix matrix={charts.data.severity_matrix} />
          </Panel>
        </>
      )}
      <div className="review-grid">
        <Panel id="top-h" title="Top 5 bề mặt đáng xem" hint="Xếp hạng theo tín hiệu (API, đăng nhập, tech rủi ro, mới…).">
          {summary.top_surface.length === 0 ? <p className="muted">Chưa có dữ liệu — chạy một scan hoàn tất.</p> : (
            <ol className="toplist">
              {summary.top_surface.map((a) => (
                <li key={a.id}><strong>{a.host}</strong> <Badge tone="rank">{a.rank_score ?? 0}</Badge><small>{(a.reasons || []).map(reasonText).join(", ")}</small></li>
              ))}
            </ol>
          )}
          <a href={`#/program/${encodeURIComponent(slug)}/data?v=surface`}>Xem đầy đủ →</a>
        </Panel>
        <Panel id="mon-h" title="Giám sát liên tục" hint={enabled ? `Đang bật (${summary.schedule!.interval}, mức ${summary.schedule!.depth}). Lần kế tiếp: ${when(summary.schedule!.next_run_at)}.` : "Tự quét lại theo lịch với scope hiện hành, không qua xem lại từng lần. Chỉ bật cho program cho phép automation."}
          output="Mỗi lần chạy tạo một scan mới trong Lịch sử và cập nhật Diff.">
          <ErrorBox text={error} />
          {summary.archived_at && (
            <p className="warnbox" role="note" data-testid="schedule-archived">
              Program đã lưu trữ nên không đổi được lịch.{summary.schedule?.paused_by_archive ? " Lịch trước đó đã bị tạm dừng; khôi phục program rồi bật lại giám sát nếu cần." : ""}
            </p>
          )}
          {enabled && summary.schedule?.last_error && (
            <p className="warnbox" role="alert" data-testid="schedule-error">
              Lần chạy theo lịch gần nhất ({when(summary.schedule.last_error_at)}) <strong>đã bị bỏ qua</strong>: {summary.schedule.last_error}
              {" "}Sửa điều kiện này (Scan lại để xem lại scope/policy) hoặc tắt giám sát.
            </p>
          )}
          <div className="form">
            <label>Tần suất
              <select aria-label="Interval" value={interval} onChange={(e) => setInterval(e.target.value)}>
                <option value="6h">Mỗi 6 giờ</option><option value="daily">Hằng ngày</option><option value="weekly">Hằng tuần</option>
              </select>
            </label>
            <label>Mức quét
              <select aria-label="Monitoring depth" value={depth} onChange={(e) => { setDepth(e.target.value as Depth); setAck(false); }}>
                {PRESETS.map((p) => <option key={p.depth} value={p.depth}>{p.title} — {p.eta}</option>)}
              </select>
            </label>
            <p className="muted" data-testid="schedule-preview">
              Mỗi lần chạy: <strong>{depth}</strong>
              {depth !== "passive" && <> · header gửi kèm: {savedNames.length ? <strong>{savedNames.join(", ")}</strong> : "không có"}</>}
              {summary.default_profile_id ? " · theo profile mặc định của program (nếu cùng mức quét)" : ""}.
              {enabled && summary.schedule?.config && <> Lịch đang bật: {summary.schedule.config.depth}, {summary.schedule.config.threads} luồng, {summary.schedule.config.rate_limit} req/s
                {summary.schedule.config.request_header_names.length > 0 && <>, header {summary.schedule.config.request_header_names.join(", ")}</>}.</>}
            </p>
            {depth !== "passive" && hintsOpen.length > 0 && (
              <p className="warnbox" role="status">
                Policy nhắc tới header <strong>{hintsOpen.join(", ")}</strong> nhưng program chưa lưu header mặc định.{" "}
                <button className="linklike" onClick={() => api(base + "/rescan", { method: "POST" }).then((m) => go("/scan/" + m.scan_id + "/review")).catch((e) => setError(explain(e)))}>Mở Review để nhập và lưu →</button>
              </p>
            )}
            {depth !== "passive" && hintsOpen.length > 0 && (
              <label className="check"><input type="checkbox" checked={skipHeader} onChange={(e) => setSkipHeader(e.target.checked)} />Tôi đã đọc policy và lịch này không gửi header {hintsOpen.join(", ")}.</label>
            )}
            {depth !== "passive" && <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />Program cho phép scan tự động theo lịch ở mức này.</label>}
            <div className="actions">
              <button disabled={!!summary.archived_at || (depth !== "passive" && (!ack || (hintsOpen.length > 0 && !skipHeader)))} onClick={() => schedule(true)}>{enabled ? "Cập nhật lịch" : "Bật giám sát"}</button>
              {enabled && <button className="secondary" onClick={() => schedule(false)}>Tắt giám sát</button>}
            </div>
          </div>
        </Panel>
      </div>
    </>
  );
}

/* ───────────── Dữ liệu ───────────── */
function HostsView({ base, kind }: { base: string; kind: "surface" | "assets" }) {
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
  const path = kind === "surface" ? base + "/surface?" + params
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
            <option value="active">Trong inventory (đang theo dõi)</option><option value="gone">Đã biến mất</option>
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

function DataArea({ slug, view }: { slug: string; view: string }) {
  const base = "/api/programs/" + encodeURIComponent(slug);
  const current = ["hosts", "urls", "surface", "ports", "dirs"].includes(view) ? view : "urls";
  const params = routeParams();
  const initial: Record<string, string> = {};
  for (const k of ["tag", "verification", "shape", "min_score", "scan"]) if (params.get(k)) initial[k] = params.get(k)!;
  const info = {
    hosts: ["Danh sách host", "Mọi host/IP thuộc scope mà các bước tìm subdomain và probe HTTP thu được: trạng thái, tiêu đề, công nghệ.", "Từ bước “Tìm subdomain” và “Probe HTTP”."],
    urls: ["URL & endpoint", "URL đã qua scope gate, xếp theo điểm đáng xem. Biết rõ URL lấy từ đâu và đã kiểm chứng chưa.", "Từ bước “URL lịch sử”, “Crawl chủ động” và “Phân tích JavaScript”."],
    surface: ["Xếp hạng bề mặt", "Host được chấm điểm theo tín hiệu (API, đăng nhập, tech rủi ro, mới, nuclei…).", "Tính tự động sau mỗi scan."],
    ports: ["Cổng/Dịch vụ", "Cổng mở và dịch vụ nmap tìm thấy trên host đang chạy, của scan gần nhất (hoặc scan bạn chọn).", "Từ bước “Quét cổng”. Chỉ chạy ở mức Strong."],
    dirs: ["Đường dẫn dò được", "Đường dẫn ffuf dò thấy, đã loại trang chặn/mặc định giống nhau lặp lại (nhiễu).", "Từ bước “Dò thư mục”. Chỉ chạy ở mức Strong."],
  }[current]!;
  return (
    <>
      <Segmented label="Loại dữ liệu" value={current as any} onChange={(v) => go(programPath(slug, "data", v))}
        options={[{ value: "urls", label: "URL & endpoint" }, { value: "hosts", label: "Host" }, { value: "surface", label: "Xếp hạng" },
                  { value: "ports", label: "Cổng/Dịch vụ" }, { value: "dirs", label: "Đường dẫn dò được" }]} />
      <p className="viewintro"><strong>{info[0]}.</strong> {info[1]} <span className="muted">{info[2]}</span></p>
      {current === "urls" ? <UrlExplorer key={JSON.stringify(initial)} slug={slug} initial={initial} />
        : current === "ports" ? <PortsView base={base} />
        : current === "dirs" ? <DirsView base={base} />
        : <HostsView key={current} base={base} kind={current === "surface" ? "surface" : "assets"} />}
    </>
  );
}

/* ───────────── Cổng/Dịch vụ (nmap), Đường dẫn dò được (ffuf) — BACKLOG mục 4: bảng riêng, không chỉ đọc lúc dựng Run ───────────── */
function PortsView({ base }: { base: string }) {
  const result = useData<any>(base + "/ports");
  return (
    <State data={result.data} error={result.error}>
      {!result.data?.found ? (
        <EmptyState title="Chưa có dữ liệu cổng">nmap chỉ chạy ở mức Strong khi chưa tắt. Quét Strong để có dữ liệu cổng/dịch vụ.</EmptyState>
      ) : (
        <>
          {!result.data.complete && <p className="muted" data-testid="ports-partial">DỞ DANG: nmap dừng trước khi quét xong, chỉ gồm các host đã xong.</p>}
          {result.data.cdn.length > 0 && (
            <p className="muted" data-testid="ports-cdn">{result.data.cdn_pairs} cặp nằm trên IP của {result.data.cdn.join(", ")} (CDN/biên dùng chung): đây là cổng của CDN, chưa chứng minh là cổng của máy chủ gốc (origin) hay của ứng dụng.</p>
          )}
          {result.data.rows.length === 0 ? (
            <EmptyState title="Không có cổng mở">nmap đã chạy nhưng không tìm thấy cổng mở nào trên host đã quét.</EmptyState>
          ) : (
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Bảng dữ liệu, cuộn được">
              <table>
                <thead><tr><th>Host</th><th>IP</th><th>Cổng</th><th>Giao thức</th><th>Dịch vụ</th></tr></thead>
                <tbody>
                  {result.data.rows.map((r: any, i: number) => (
                    <tr key={i}>
                      <td><strong>{r.host}</strong>{result.data.cdn_hosts.includes(r.host) && <Badge>CDN</Badge>}</td>
                      <td>{r.ip}</td><td>{r.port}</td><td>{r.proto}</td><td>{[r.service, r.version].filter(Boolean).join(" ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </State>
  );
}

function DirsView({ base }: { base: string }) {
  const result = useData<any>(base + "/dirs");
  return (
    <State data={result.data} error={result.error}>
      {!result.data?.found ? (
        <EmptyState title="Chưa có dữ liệu dò thư mục">ffuf chỉ chạy ở mức Strong khi chưa tắt. Quét Strong để có dữ liệu.</EmptyState>
      ) : (
        <>
          <p className="muted" data-testid="dirs-summary">{result.data.total} phản hồi trên {result.data.hosts.length} host; {result.data.noise} giống hệt nhau (trang chặn/trang mặc định chung) đã loại, còn {result.data.significant} đáng xem.</p>
          {result.data.blocked_only.length > 0 && (
            <p className="muted" data-testid="dirs-blocked-only">Chỉ có HTTP 403 ở: {result.data.blocked_only.join(", ")} — 403 không chứng minh đường dẫn tồn tại.</p>
          )}
          {result.data.hosts.length === 0 ? (
            <EmptyState title="Không có kết quả">ffuf đã chạy nhưng chưa có host nào trả kết quả.</EmptyState>
          ) : result.data.hosts.map((h: any) => (
            <div key={h.host} className="panel">
              <h4>{h.host} <span className="muted">({h.total - h.noise}/{h.total} đáng xem)</span></h4>
              {h.significant.length === 0 ? <p className="muted">Toàn nhiễu (trang chặn/mặc định giống nhau) — không có đường dẫn đáng xem.</p> : (
                <div className="table-wrap" tabIndex={0} role="region" aria-label="Bảng dữ liệu, cuộn được">
                  <table>
                    <thead><tr><th>URL</th><th>Mã</th><th>Kích thước</th></tr></thead>
                    <tbody>
                      {h.significant.map((r: any, i: number) => (
                        <tr key={i}><td>{r.url}</td><td>{r.status}</td><td>{r.length}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </State>
  );
}

/* ───────────── Phát hiện ───────────── */
function FindingsTab({ base, notes }: { base: string; notes?: DataNote[] }) {
  const params = routeParams();
  const [severity, setSeverity] = useState("");
  const [type, setType] = useState(params.get("type") || "");
  const [offset, setOffset] = useState(0);
  const result = useAssets(base + "/findings?" + new URLSearchParams({ limit: "50", offset: String(offset), ...(severity ? { severity } : {}), ...(type ? { type } : {}) }));
  return (
    <>
      <p className="viewintro"><strong>Findings.</strong> Dấu hiệu lỗi hoặc rò rỉ do nuclei, takeover và quét bí mật tìm thấy. <span className="muted">0 finding không có nghĩa target an toàn — chỉ là công cụ đã chạy không thấy gì. Takeover và secret là <em>ứng viên chưa xác minh</em>, không phải lỗi đã chứng minh.</span></p>
      {(notes || []).length > 0 && <div className="notice" role="note" data-testid="findings-notes">{notes!.map((n, i) => <p key={i}>{n.note}</p>)}</div>}
      <div className="filters">
        <select aria-label="Mức nghiêm trọng" value={severity} onChange={(e) => { setSeverity(e.target.value); setOffset(0); }}>
          <option value="">Mọi mức</option>{["critical", "high", "medium", "low", "info"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <select aria-label="Loại" value={type} onChange={(e) => { setType(e.target.value); setOffset(0); }}>
          <option value="">Mọi loại</option>{["nuclei", "takeover", "secret", "js-endpoint"].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <State data={result.state} error={result.error}>
        {(result.state?.items.length || 0) === 0 ? (
          <EmptyState title="Chưa có finding">Finding xuất hiện khi nuclei/takeover/secrets tìm thấy kết quả. Kiểm tra tab Lịch sử → scan → “Kết quả theo bước” để biết các bước đó đã chạy chưa.</EmptyState>
        ) : (
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Bảng dữ liệu, cuộn được">
            <table>
              <thead><tr><th>Mức</th><th>Tên</th><th>Loại</th><th>Asset</th><th>Chi tiết</th></tr></thead>
              <tbody>
                {(result.state!.items as any[]).map((f) => (
                  <tr key={f.id}>
                    <td><SeverityBadge severity={f.severity} /></td><td><strong>{f.name}</strong></td><td>{f.type}</td><td>{f.host || "—"}</td>
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

/* ───────────── Lịch sử ───────────── */
function HistoryArea({ slug, view, summary, detail }: { slug: string; view: string; summary: Summary; detail: any }) {
  const current = view === "diff" ? "diff" : "scans";
  const base = "/api/programs/" + encodeURIComponent(slug);
  return (
    <>
      <Segmented label="Lịch sử" value={current as any} onChange={(v) => go(programPath(slug, "history", v))}
        options={[{ value: "scans", label: "Các lần scan" }, { value: "diff", label: "So sánh thay đổi" }]} />
      {current === "scans" ? (
        <>
          <p className="viewintro"><strong>Các lần scan.</strong> Bấm vào một scan để xem từng bước đã chạy gì, tìm được bao nhiêu và đọc file kết quả.</p>
          {(detail?.scans || []).length === 0 ? <EmptyState title="Chưa có scan">Hãy bấm “Scan lại” để tạo bản nháp đầu tiên.</EmptyState> : (
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Bảng dữ liệu, cuộn được">
              <table>
                <thead><tr><th>Scan</th><th>Mức</th><th>Trạng thái</th><th>Kết quả</th><th>Lúc</th></tr></thead>
                <tbody>
                  {(detail.scans as any[]).map((s) => (
                    <tr key={s.id}>
                      <td><a href={s.status === "draft" ? "#/scan/" + s.id + "/review" : "#/scan/" + s.id}>#{s.id}</a> {s.trigger === "scheduled" && <Chip>theo lịch</Chip>}</td>
                      <td>{s.depth}</td><td><StatusBadge status={s.status} /></td>
                      <td>{s.stats?.observed !== undefined ? `${s.stats.subs ?? 0} host · ${(s.stats.urls ?? 0).toLocaleString("vi-VN")} URL · ${s.stats.findings ?? 0} finding` : "—"}</td>
                      <td>{when(s.finished_at || s.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : <DiffView base={base} summary={summary} />}
    </>
  );
}

function DiffView({ base, summary }: { base: string; summary: Summary }) {
  const [change, setChange] = useState("");
  const [offset, setOffset] = useState(0);
  const result = useAssets(base + "/diff?" + new URLSearchParams({ limit: "50", offset: String(offset), ...(change ? { change } : {}) }));
  const baseline = (summary.last_completed_scan as any)?.baseline_scan_id;
  const latest = summary.last_completed_scan?.id;
  const emptyText = change ? "Không có thay đổi thuộc loại này." : baseline ? `Đã so sánh #${latest} với #${baseline}: không phát hiện thay đổi.`
    : "Chưa có scan hoàn tất trước đó để so sánh. Diff xuất hiện từ lần scan hoàn tất thứ hai.";
  return (
    <>
      <p className="viewintro"><strong>So sánh thay đổi.</strong> {latest ? <>Scan #{latest} so với {baseline ? <>scan hoàn tất gần nhất trước đó (#{baseline})</> : "— chưa có scan hoàn tất trước đó để so"}.</> : "Cần ít nhất hai scan hoàn tất."} <span className="muted">Scan bị huỷ hoặc lỗi không dùng làm mốc.</span></p>
      <div className="filters" role="group" aria-label="Lọc thay đổi">
        {[["", "Tất cả"], ["new", "Mới"], ["changed", "Thay đổi"], ["gone", "Biến mất"]].map(([v, label]) => (
          <button key={v} className={change === v ? "active small" : "secondary small"} onClick={() => { setChange(v); setOffset(0); }}>{label}</button>
        ))}
      </div>
      <State data={result.state} error={result.error}>
        {(result.state?.items.length || 0) === 0 ? <EmptyState title="Không có thay đổi">{emptyText}</EmptyState> : (
          <section className="card">
            {(result.state!.items as any[]).map((r) => (
              <div className="finding" key={r.id}>
                <Badge tone={r.change}>{{ new: "MỚI", changed: "THAY ĐỔI", gone: "BIẾN MẤT" }[r.change as string] || r.change}</Badge>
                <strong>{r.entity_ref}</strong><small>{changeText(r)}</small>
              </div>
            ))}
            <Pager total={result.state!.total} limit={50} offset={offset} onChange={setOffset} />
          </section>
        )}
      </State>
    </>
  );
}

/* ───────────── Hướng dẫn & scope ───────────── */
function BriefView({ base, summary }: { base: string; summary: Summary }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const brief = useData<string>(base + "/brief", revision);
  async function regenerate() {
    setError("");
    try { await api(base + "/brief", { method: "POST" }); setRevision((v) => v + 1); } catch (e) { setError(explain(e)); }
  }
  if (brief.code === "no_completed_scan")
    return <EmptyState title="Chưa có brief" action={<a className="button" href="#/new">Tạo scan</a>}>Brief được sinh sau scan hoàn tất đầu tiên. Bạn vẫn có thể sửa hướng dẫn cho agent ở mục bên cạnh ngay bây giờ.</EmptyState>;
  const text = typeof brief.data === "string" ? brief.data : "";
  return (
    <section className="card markdown">
      <p className="viewintro"><strong>AGENT_BRIEF.md.</strong> Tệp duy nhất agent cần đọc để bắt đầu: scope, số liệu, host/URL đáng xem, gợi ý test. Bên dưới là đúng nội dung agent đọc.</p>
      <div className="actions">
        <button onClick={regenerate}>Tạo lại brief</button>
        <CopyButton text={summary.hunt_command} label="Sao chép lệnh hunt" />
        {text && <span className="muted">{new Blob([text]).size.toLocaleString("vi-VN")} / 12.000 byte</span>}
      </div>
      <ErrorBox text={error} />
      <State data={brief.data} error={brief.error}><pre className="rawdoc" tabIndex={0} aria-label="AGENT_BRIEF.md">{text}</pre></State>
    </section>
  );
}

function InstructionsView({ base }: { base: string }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const doc = useData<string>(base + "/program", revision);
  const original = typeof doc.data === "string" ? doc.data.split("<!-- user-editable -->")[1]?.split("<!-- /user-editable -->")[0]?.trim() || "" : "";
  const [edit, setEdit] = useState("");
  useEffect(() => setEdit(original), [original]);
  const dirty = edit !== original;
  async function save() {
    setError("");
    try {
      await api(base + "/program", { method: "PUT", body: JSON.stringify({ content: edit }) });
      setSaved(true); setRevision((v) => v + 1); setTimeout(() => setSaved(false), 2000);
    } catch (e) { setError(explain(e)); }
  }
  return (
    <section className="card markdown">
      <p className="viewintro"><strong>PROGRAM.md.</strong> Luật chơi bền của program (policy, scope, ghi chú của bạn). Agent đọc tệp này trước. Chỉ phần ghi chú của bạn sửa được; phần còn lại do hệ thống sinh.</p>
      <label>Ghi chú của bạn (auth, OOS, severity guideline…) — phần duy nhất được sửa
        <textarea rows={6} value={edit} onChange={(e) => setEdit(e.target.value)} />
      </label>
      <div className="actions">
        <button onClick={save} disabled={!dirty}>Save instructions</button>
        {dirty && <span className="muted">Chưa lưu</span>}{saved && <span className="okline">Đã lưu ✓</span>}
      </div>
      <ErrorBox text={error} />
      <State data={doc.data} error={doc.error}><ReactMarkdown>{typeof doc.data === "string" ? doc.data : ""}</ReactMarkdown></State>
    </section>
  );
}

function ScopeView({ slug, summary, detail, reload }: { slug: string; summary: Summary & { trust?: Trust }; detail: any; reload: () => void }) {
  const profiles = useData<{ builtin: Profile[]; custom: Profile[] }>("/api/profiles");
  const [error, setError] = useState("");
  const rules: any[] = detail?.scope || [];
  const policy = detail?.policy || {};
  const text = policy.policy_text || policy.program?.policy || "";
  const userText = (policy.user_policy_text || "").trim();
  async function setDefault(value: string) {
    try {
      await api("/api/programs/" + encodeURIComponent(slug) + "/default-profile", { method: "PUT", body: JSON.stringify({ profile_id: value ? Number(value) : null }) });
      reload();
    } catch (e) { setError(explain(e)); }
  }
  return (
    <>
      <p className="viewintro"><strong>Scope & policy.</strong> Scope hiện hành của program (đã xác nhận ở lần launch gần nhất) và policy lấy được.</p>
      <TrustBadge trust={summary.trust} full />
      <div className="review-grid">
        <Panel id="in-h" title={`IN scope (${rules.filter((r) => r.kind === "in").length})`}>
          <ul className="plain">{rules.filter((r) => r.kind === "in").map((r) => <li key={r.id}><code>{r.pattern}</code> <Chip>{r.asset_type}</Chip></li>)}</ul>
        </Panel>
        <Panel id="out-h" title={`OUT scope (${rules.filter((r) => r.kind === "out").length})`} hint="Luôn bị chặn.">
          <ul className="plain">{rules.filter((r) => r.kind === "out").map((r) => <li key={r.id}><code>{r.pattern}</code></li>)}</ul>
        </Panel>
      </div>
      <Panel id="pol-h" title="Policy">
        {text && <><h3 className="subhead">Policy từ nguồn{policy.policy_source ? ` (${policy.policy_source === "api" ? "API HackerOne" : policy.policy_source === "public_page" ? "trang công khai HackerOne" : policy.policy_source})` : ""}</h3>
          <div className="policy-text open"><ReactMarkdown>{text}</ReactMarkdown></div></>}
        {userText && <><h3 className="subhead">Policy bạn đã dán thêm</h3><div className="policy-text open" data-testid="user-policy"><ReactMarkdown>{userText}</ReactMarkdown></div></>}
        {!text && !userText && <p className="muted">Chưa có nội dung policy. Dán policy của program ở bước nhập scope (Thêm program) rồi Resolve lại.</p>}
      </Panel>
      <Panel id="prof-h" title="Profile mặc định" hint="Scan mới của program này sẽ bắt đầu từ profile này thay vì Light. Tạo profile ở trang Profile quét.">
        <ErrorBox text={error} />
        <select aria-label="Profile mặc định" value={summary.default_profile_id ? String(summary.default_profile_id) : ""} onChange={(e) => setDefault(e.target.value)}>
          <option value="">Light (mặc định hệ thống)</option>
          {profiles.data?.custom.map((p) => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
        </select>
      </Panel>
    </>
  );
}

function ExportView({ base, slug }: { base: string; slug: string }) {
  const modes = [
    ["filtered", "Đã lọc scope (khuyến nghị)", "Brief, scope, PROGRAM.md và recon — các dòng recon ngoài scope đã bị loại. An toàn để chuyển cho người/agent khác."],
    ["brief", "Chỉ brief", "Gọn nhất: AGENT_BRIEF.md, PROGRAM.md, CLAUDE.md, .scope, findings/, notes/, reports/. Không có recon."],
    ["full", "Recon thô", "Mọi file recon nguyên bản. CÓ THỂ chứa URL/host ngoài scope. Chỉ dùng cho mình."],
  ] as const;
  return (
    <>
      <p className="viewintro"><strong>Xuất ZIP.</strong> Đóng gói thư mục <code>{slug}/</code> để mang sang máy khác hoặc đưa cho agent. Giải nén ra đúng cấu trúc để <code>cd</code> và chạy <code>claude</code>.</p>
      <div className="cards3">
        {modes.map(([mode, title, text]) => (
          <section className={"panel " + (mode === "full" ? "warn" : mode === "filtered" ? "accent" : "")} key={mode}>
            <h2>{title}</h2><p className="hint">{text}</p>
            <a className="button" href={base + "/export?mode=" + mode}>Tải ZIP ↓</a>
          </section>
        ))}
      </div>
    </>
  );
}

function GuideArea({ slug, view, summary, detail, reload }: { slug: string; view: string; summary: Summary; detail: any; reload: () => void }) {
  const base = "/api/programs/" + encodeURIComponent(slug);
  const current = ["brief", "instructions", "scope", "export"].includes(view) ? view : "brief";
  return (
    <>
      <Segmented label="Hướng dẫn & scope" value={current as any} onChange={(v) => go(programPath(slug, "guide", v))}
        options={[{ value: "brief", label: "Brief" }, { value: "instructions", label: "Hướng dẫn cho agent" }, { value: "scope", label: "Scope & policy" }, { value: "export", label: "Xuất ZIP" }]} />
      {current === "brief" ? (summary ? <BriefView base={base} summary={summary} /> : <Loading />)
        : current === "instructions" ? <InstructionsView base={base} />
        : current === "scope" ? <ScopeView slug={slug} summary={summary} detail={detail} reload={reload} />
        : <ExportView base={base} slug={slug} />}
    </>
  );
}

/* ───────────── Trang Program ───────────── */
export function Program({ slug, tab, view }: { slug: string; tab: string; view: string }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const base = "/api/programs/" + encodeURIComponent(slug);
  const summary = useData<Summary & { trust?: Trust }>(base + "/summary", revision);
  const detail = useData<any>(base, revision);
  const urls = useData<UrlSummary>(tab === "overview" ? base + "/urls/summary" : null, revision);

  async function rescan() {
    try {
      const made = await api(base + "/rescan", { method: "POST" });
      go("/scan/" + made.scan_id + "/review");
    } catch (e) { setError(explain(e)); }
  }
  async function archive() {
    if (!window.confirm(`Lưu trữ “${slug}”? Program sẽ bị ẩn khỏi danh sách chính và lịch giám sát tạm dừng. Dữ liệu vẫn còn; tìm lại ở Danh mục → “Đã lưu trữ” để khôi phục.`)) return;
    try { await api(base + "/archive", { method: "POST" }); setRevision((v) => v + 1); } catch (e) { setError(explain(e)); }
  }
  const s = summary.data;
  const archived = !!s?.archived_at;
  return (
    <>
      <PageHead eyebrow="PROGRAM" title={slug}
        sub={<>{s?.source} · <StatusBadge status={s?.latest_scan?.status} />{s?.latest_scan && <> scan #{s.latest_scan.id} · {s.latest_scan.depth}</>}</>}
        actions={archived ? undefined : <><button onClick={rescan}>Scan lại</button> <button className="secondary" onClick={archive}>Lưu trữ</button></>} />
      {s?.archived_at && <ArchivedBanner slug={slug} archivedAt={s.archived_at} reload={() => setRevision((v) => v + 1)} />}
      {s?.trust && s.trust.level !== "manual" && <TrustBadge trust={s.trust} />}
      <ErrorBox text={error} />
      <nav className="tabs" role="tablist" aria-label="Program">
        {TABS.map((t) => (
          <a key={t} role="tab" aria-selected={t === tab} className={t === tab ? "tab active" : "tab"} href={"#" + programPath(slug, t)} title={TAB_HINT[t]}>
            {TAB_LABEL[t]}
          </a>
        ))}
      </nav>
      <State data={s} error={summary.error} retry={() => setRevision((v) => v + 1)}>
        {s && (tab === "overview" ? <Overview slug={slug} summary={s} detail={detail.data} urls={urls.data} reload={() => setRevision((v) => v + 1)} />
          : tab === "data" ? <DataArea slug={slug} view={view} />
          : tab === "findings" ? <FindingsTab base={base} notes={s.data_notes} />
          : tab === "history" ? <HistoryArea slug={slug} view={view} summary={s} detail={detail.data} />
          : <GuideArea slug={slug} view={view} summary={s} detail={detail.data} reload={() => setRevision((v) => v + 1)} />)}
      </State>
    </>
  );
}
