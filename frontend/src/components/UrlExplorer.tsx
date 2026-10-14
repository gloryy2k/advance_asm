import { useEffect, useMemo, useState } from "react";
import { api, apiPage } from "../api/client";
import type { UrlRow, UrlSummary } from "../api/types";
import { explain } from "../lib/errors";
import { Chip } from "./layout";
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
  const [minScore, setMinScore] = useState("0");
  const [offset, setOffset] = useState(0);
  const limit = 50;

  useEffect(() => {
    api<UrlSummary>(base + "/summary").then(setSummary).catch((e) => setError(explain(e)));
  }, [base]);
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
    if (minScore !== "0") p.set("min_score", minScore);
    return p;
  }, [term, tag, verification, shape, minScore]);
  useEffect(() => {
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
  }, [base, query, offset]);

  const funnel = summary?.funnel;
  const active = [tag && `nhãn ${TAG_LABEL[tag] || tag}`, verification && VERIFY_LABEL[verification], shape && `nhóm ${shape}`, term && `"${term}"`, minScore !== "0" && `điểm ≥ ${minScore}`].filter(Boolean);
  const clear = () => {
    setQ(""); setTag(""); setVerification(""); setShape(""); setMinScore("0"); setOffset(0);
  };
  const exportHref = base + "/export?" + query;
  return (
    <div className="urlx">
      {funnel && (
        <div className="funnel" aria-label="Phễu URL">
          <div><strong>{funnel.raw.toLocaleString("vi-VN")}</strong><span>URL do tool tìm thấy</span></div>
          <span className="arrow" aria-hidden="true">→</span>
          <div className="good"><strong>{funnel.in_scope.toLocaleString("vi-VN")}</strong><span>trong scope (đang xem)</span></div>
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
          <option value="0">Mọi điểm</option>
          <option value="1">Điểm ≥ 1</option>
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
      {active.length > 0 && <p className="muted">Đang lọc: {active.join(" · ")} <button className="linklike" onClick={clear}>✕ Bỏ lọc</button></p>}
      <ErrorBox text={error} />
      {rows === null ? <p className="muted">Đang tải…</p> : rows.items.length === 0 ? (
        <EmptyState title="Không có URL phù hợp">{summary?.total ? "Thử bỏ bớt bộ lọc." : "Chưa có URL: scan chưa thu thập URL, hoặc chưa có scan hoàn tất."}</EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="urls">
            <thead><tr><th>Điểm</th><th>URL</th><th>Nhãn</th><th>Nguồn</th></tr></thead>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows && <Pager total={rows.total} limit={limit} offset={offset} onChange={setOffset} />}
    </div>
  );
}
