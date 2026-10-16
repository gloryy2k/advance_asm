import { useEffect, useMemo, useState } from "react";
import { api, apiPage } from "../api/client";
import type { UrlRow, UrlSummary } from "../api/types";
import { explain } from "../lib/errors";
import { when } from "../lib/format";
import { Chip } from "./layout";
import { SitemapTree } from "./SitemapTree";
import { CopyButton, EmptyState, ErrorBox, Pager } from "./ui";

const TAG_LABEL: Record<string, string> = {
  api: "API", auth: "đăng nhập", admin: "quản trị", sensitive: "nhạy cảm", "redirect-param": "chuyển hướng", "id-param": "tham số ID",
  "file-param": "tham số tệp", upload: "tải lên", js: "JS", docs: "tài liệu API", params: "có tham số",
};
const VERIFY_LABEL: Record<string, string> = { historical: "lịch sử — chưa kiểm chứng", observed: "đã crawl thấy", live: "live" };

/** The URLs that survived the scope gate, best first — with how each one was learned. */
export function UrlExplorer({ slug, initial }: { slug: string; initial?: Record<string, string> }) {
  const base = "/api/programs/" + encodeURIComponent(slug) + "/urls";
  const [summary, setSummary] = useState<UrlSummary | null>(null);
  const [rows, setRows] = useState<{ items: UrlRow[]; total: number } | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [tag, setTag] = useState(initial?.tag || "");
  const [verification, setVerification] = useState(initial?.verification || "");
  const [shape, setShape] = useState(initial?.shape || "");
  const [minScore, setMinScore] = useState(initial?.min_score || "1");  // default: hide plain content pages
  const [offset, setOffset] = useState(0);
  const [mode, setMode] = useState<"table" | "tree">(initial?.view === "tree" ? "tree" : "table");
  // Which scans the list speaks for: the newest completed one, everything on record, or what was known as of scan N.
  const [scope, setScope] = useState(initial?.scan || "latest");
  const limit = 50;

  useEffect(() => {
    let live = true;
    setSummary(null);
    api<UrlSummary>(base + "/summary?scan=" + encodeURIComponent(scope)).then((r) => live && setSummary(r)).catch((e) => live && setError(explain(e)));
    return () => { live = false; };
  }, [base, scope]);
  useEffect(() => {
    const t = setTimeout(() => {
      setTerm(q);
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);
  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (term) p.set("q", term);
    if (tag) p.set("tag", tag);
    if (verification) p.set("verification", verification);
    if (shape) p.set("shape", shape);
    p.set("min_score", minScore);
    p.set("scan", scope);
    return p;
  }, [term, tag, verification, shape, minScore, scope]);
  useEffect(() => {
    if (mode === "tree") return;   // the tree loads its own levels
    let live = true;
    const p = new URLSearchParams(query);
    p.set("limit", String(limit));
    p.set("offset", String(offset));
    apiPage<UrlRow>(base + "?" + p)
      .then((r) => live && (setRows(r), setError("")))
      .catch((e) => live && setError(explain(e)));
    return () => {
      live = false;
    };
  }, [base, query, offset, mode]);

  const funnel = summary?.funnel;
  const active = [tag && `nhãn ${TAG_LABEL[tag] || tag}`, verification && VERIFY_LABEL[verification], shape && `nhóm ${shape}`, term && `"${term}"`, minScore !== "1" && (minScore === "0" ? "mọi điểm" : `điểm ≥ ${minScore}`)].filter(Boolean);
  const clear = () => {
    setQ(""); setTag(""); setVerification(""); setShape(""); setMinScore("1"); setOffset(0);
  };
  const latest = summary?.latest;
  const asOf = /^\d+$/.test(scope);
  const noneInLatest = scope === "latest" && !!summary && summary.total === 0 && summary.history_total > 0;
  const exportHref = base + "/export?" + query;
  return (
    <div className="urlx">
      <div className="filters scopebar" role="group" aria-label="Phạm vi URL">
        <label>Phạm vi
          <select aria-label="Phạm vi scan" value={asOf ? "asof" : scope} onChange={(e) => { setScope(e.target.value === "asof" ? scope : e.target.value); setOffset(0); }}>
            <option value="latest">Scan mới nhất{latest ? ` (#${latest.id})` : ""}</option>
            <option value="all">Tất cả scan (lịch sử)</option>
            {asOf && <option value="asof">Ghi nhận tới scan #{scope}</option>}
          </select>
        </label>
        {summary && (
          <span className="muted" data-testid="url-scope-note">
            {scope === "latest" && (latest ? <>URL do scan #{latest.id} ({latest.depth}{latest.finished_at ? `, ${when(latest.finished_at)}` : ""}) nhìn thấy.</> : "Chưa có scan hoàn tất.")}
            {scope === "all" && <>Mọi URL đã ghi nhận qua các scan; cột “scan” cho biết lần đầu/gần nhất thấy.</>}
            {asOf && <>URL đã ghi nhận từ scan #{scope} trở về trước (có thể đã không còn xuất hiện ở scan sau).</>}
          </span>
        )}
      </div>
      <div className="viewswitch" role="group" aria-label="Kiểu hiển thị URL">
        <button type="button" className={mode === "table" ? "small" : "secondary small"} aria-pressed={mode === "table"} onClick={() => setMode("table")}>Bảng</button>
        <button type="button" className={mode === "tree" ? "small" : "secondary small"} aria-pressed={mode === "tree"}
          onClick={() => { setMode("tree"); if (minScore === "1") setMinScore("0"); }}>Cây sitemap</button>
      </div>
      {noneInLatest && (
        <p className="warnbox" role="status" data-testid="url-history-cta">
          Scan mới nhất (#{latest?.id}) không thu được URL nào, nhưng chương trình có <strong>{summary!.history_total.toLocaleString("vi-VN")}</strong> URL ghi nhận từ các scan trước.{" "}
          <button className="linklike" onClick={() => { setScope("all"); setMinScore("0"); setOffset(0); }}>Xem URL lịch sử →</button>
        </p>
      )}
      {funnel && (
        <div className="funnel" aria-label="Phễu URL">
          <div><strong>{funnel.raw.toLocaleString("vi-VN")}</strong><span>URL do tool tìm thấy</span></div>
          <span className="arrow" aria-hidden="true">→</span>
          <div className="good"><strong>{funnel.in_scope.toLocaleString("vi-VN")}</strong><span>từ recon, qua scope gate</span></div>
          {!!funnel.from_probe && (
            <>
              <span className="arrow" aria-hidden="true">+</span>
              <div className="good"><strong>{funnel.from_probe.toLocaleString("vi-VN")}</strong><span>từ probe HTTP (host trả lời)</span></div>
            </>
          )}
          {funnel.stored !== undefined && (
            <>
              <span className="arrow" aria-hidden="true">=</span>
              <div className="good"><strong>{funnel.stored.toLocaleString("vi-VN")}</strong><span>URL của scan này (đang xem)</span></div>
            </>
          )}
          <span className="arrow" aria-hidden="true">+</span>
          <div className={funnel.out_of_scope ? "warn" : ""}><strong>{funnel.out_of_scope.toLocaleString("vi-VN")}</strong><span>ngoài scope — đã loại</span></div>
          {!!funnel.excluded_by_rule && <div><strong>{funnel.excluded_by_rule}</strong><span>loại theo mẫu của bạn</span></div>}
        </div>
      )}
      {funnel?.out_of_scope_hosts && funnel.out_of_scope_hosts.length > 0 && (
        <p className="muted">Host ngoài scope bị loại nhiều nhất: {funnel.out_of_scope_hosts.slice(0, 4).map((h) => `${h.host} (${h.count})`).join(", ")}.</p>
      )}
      <p className="notice">URL lấy từ archive là <strong>lịch sử</strong>: chỉ cho biết URL từng tồn tại, chưa chứng minh còn chạy hay có lỗi. URL “đã crawl thấy” là do katana tìm được trên host đang chạy.</p>

      {summary && summary.top_shapes.length > 0 && (
        <details className="shapes" open={!shape && !tag && !term}>
          <summary>Nhóm URL theo dạng đường dẫn ({summary.top_shapes.length} nhóm nổi bật) — bấm để lọc</summary>
          <ul>
            {summary.top_shapes.map((s) => (
              <li key={s.shape}>
                <button className={"shape " + (shape === s.shape ? "on" : "")} onClick={() => { setShape(shape === s.shape ? "" : s.shape); setOffset(0); }}>
                  <code>{s.shape}</code> <span>{s.count.toLocaleString("vi-VN")} URL</span>
                  {s.max_score >= 3 && <Chip tone="warn">điểm cao nhất {s.max_score}</Chip>}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="filters">
        <input aria-label="Tìm URL" placeholder="Tìm trong URL…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Mức kiểm chứng" value={verification} onChange={(e) => { setVerification(e.target.value); setOffset(0); }}>
          <option value="">Mọi nguồn</option>
          <option value="observed">Đã crawl thấy</option>
          <option value="historical">Lịch sử (archive)</option>
        </select>
        <select aria-label="Điểm tối thiểu" value={minScore} onChange={(e) => { setMinScore(e.target.value); setOffset(0); }}>
          <option value="1">Đáng xem (điểm ≥ 1) — mặc định</option>
          <option value="0">Mọi URL (kể cả trang thường)</option>
          <option value="3">Điểm ≥ 3 (đáng xem)</option>
          <option value="5">Điểm ≥ 5 (ưu tiên)</option>
        </select>
        <a className="button secondary small" href={exportHref} download>Tải danh sách .txt ↓</a>
      </div>
      {summary && (
        <div className="chips-row" role="group" aria-label="Lọc theo nhãn">
          {Object.entries(summary.by_tag).filter(([t, n]) => n > 0 && TAG_LABEL[t]).sort((a, b) => b[1] - a[1]).map(([t, n]) => (
            <button key={t} className={"tagbtn " + (tag === t ? "on" : "")} aria-pressed={tag === t} onClick={() => { setTag(tag === t ? "" : t); setOffset(0); }}>
              {TAG_LABEL[t]} <small className="inline">{n.toLocaleString("vi-VN")}</small>
            </button>
          ))}
        </div>
      )}
      {mode === "table" && minScore === "1" && summary && rows && summary.total > rows.total && !term && !tag && !verification && !shape && (
        <p className="muted">Đang ẩn <strong>{(summary.total - rows.total).toLocaleString("vi-VN")}</strong> URL thông thường (trang nội dung, điểm &lt; 1). <button className="linklike" onClick={() => { setMinScore("0"); setOffset(0); }}>Hiện tất cả</button></p>
      )}
      {active.length > 0 && <p className="muted">Đang lọc: {active.join(" · ")} <button className="linklike" onClick={clear}>✕ Bỏ lọc</button></p>}
      <ErrorBox text={error} />
      {mode === "tree" ? <SitemapTree base={base} query={query} searching={!!term} /> : (
        <>
      {rows === null ? <p className="muted">Đang tải…</p> : rows.items.length === 0 ? (
        <EmptyState title="Không có URL phù hợp">{summary?.total ? "Thử bỏ bớt bộ lọc." : noneInLatest ? "Scan mới nhất không thu được URL; xem phần lịch sử ở trên." : "Chưa có URL: scan chưa thu thập URL, hoặc chưa có scan hoàn tất."}</EmptyState>
      ) : (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Bảng dữ liệu, cuộn được">
          <table className="urls">
            <thead><tr><th>Điểm</th><th>URL</th><th>Nhãn</th><th>Nguồn</th><th>Scan</th></tr></thead>
            <tbody>
              {rows.items.map((r) => (
                <tr key={r.id}>
                  <td><span className={"score s" + Math.min(5, Math.floor(r.score / 2))}>{r.score}</span></td>
                  <td className="urlcell">
                    <code title={r.url}>{r.url}</code>
                    <CopyButton text={r.url} label="Chép" />
                    {r.is_new && <Chip tone="good">mới</Chip>}
                  </td>
                  <td>{r.tags.filter((t) => TAG_LABEL[t]).map((t) => <Chip key={t}>{TAG_LABEL[t]}</Chip>)}</td>
                  <td><Chip tone={r.verification === "historical" ? "muted" : "good"}>{r.verification === "historical" ? "lịch sử" : "đã crawl"}</Chip> <small className="inline">{r.source}</small></td>
                  <td><small title="Lần đầu → gần nhất thấy">#{r.first_seen_scan}{r.last_seen_scan !== r.first_seen_scan ? `→#${r.last_seen_scan}` : ""}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows && <Pager total={rows.total} limit={limit} offset={offset} onChange={setOffset} />}
        </>
      )}
    </div>
  );
}
