import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { TreeLevel, TreeNode } from "../api/types";
import { explain } from "../lib/errors";
import { Chip } from "./layout";
import { CopyButton, ErrorBox } from "./ui";

type Sort = "az" | "score" | "count";
type Level = { nodes: TreeNode[]; total: number };
const TAG_LABEL: Record<string, string> = {
  api: "API", auth: "đăng nhập", admin: "quản trị", sensitive: "nhạy cảm", "redirect-param": "chuyển hướng", "id-param": "tham số ID",
  "file-param": "tham số tệp", upload: "tải lên", js: "JS", docs: "tài liệu API", params: "có tham số",
};
const keyOf = (host: string, path: string) => host + "\u0000" + path;
const nodeKey = (n: TreeNode) => keyOf(n.host, n.path);
const PAGE = 200;

/** URL inventory as a sitemap (host → folders → files), loaded one level at a time. */
export function SitemapTree({ base, query, searching }: { base: string; query: URLSearchParams; searching: boolean }) {
  const [sort, setSort] = useState<Sort>("az");
  const [foldersFirst, setFoldersFirst] = useState(false);
  const [levels, setLevels] = useState<Record<string, Level>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [focus, setFocus] = useState("");
  const treeRef = useRef<HTMLUListElement>(null);
  const generation = useRef(0);   // answers that arrive after a filter/sort change are ignored

  const params = useMemo(() => {
    const p = new URLSearchParams(query);
    p.delete("limit"); p.delete("offset");
    p.set("sort", sort);
    p.set("folders_first", String(foldersFirst));
    return p.toString();
  }, [query, sort, foldersFirst]);

  const ingest = useCallback((into: Record<string, Level>, openAll: Set<string> | null, key: string, nodes: TreeNode[], total: number) => {
    into[key] = { nodes, total };
    for (const node of nodes) {
      if (node.children) {
        const child = nodeKey(node);
        into[child] = { nodes: node.children, total: node.children_total ?? node.children.length };
        if (openAll) openAll.add(child);
        ingest(into, openAll, child, node.children, node.children_total ?? node.children.length);
      }
    }
  }, []);

  const fetchLevel = useCallback(async (host: string | null, path: string, extra: Record<string, string> = {}) => {
    const p = new URLSearchParams(params);
    if (host) { p.set("host", host); p.set("prefix", path); }
    p.set("limit", String(PAGE));
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return api<TreeLevel>(`${base}/tree?${p}`);
  }, [base, params]);

  // Root level: reload whenever the filters or the sort change. A search opens the matching branches by itself.
  useEffect(() => {
    const mine = ++generation.current;
    setError(""); setNote("");
    const depth = searching ? 3 : 1;
    fetchLevel(null, "", { depth: String(depth) }).then((r) => {
      if (mine !== generation.current) return;
      const next: Record<string, Level> = {};
      const open = searching ? new Set<string>() : null;
      ingest(next, open, "", r.nodes, r.total);
      setLevels(next);
      setExpanded(open || new Set());
      if (r.truncated) setNote("Kết quả rất lớn nên chỉ hiện một phần; thu hẹp bằng bộ lọc.");
      setFocus((f) => f || (r.nodes[0] ? nodeKey(r.nodes[0]) : ""));
    }).catch((e) => mine === generation.current && setError(explain(e)));
  }, [fetchLevel, ingest, searching]);

  async function open(node: TreeNode) {
    const key = nodeKey(node);
    if (!levels[key] && !busy.has(key)) {
      const mine = generation.current;
      setBusy((b) => new Set(b).add(key));
      try {
        const r = await fetchLevel(node.host, node.kind === "host" ? "/" : node.path);
        if (mine === generation.current) setLevels((l) => ({ ...l, [key]: { nodes: r.nodes, total: r.total } }));
      } catch (e) { setError(explain(e)); }
      finally { setBusy((b) => { const n = new Set(b); n.delete(key); return n; }); }
    }
    setExpanded((s) => new Set(s).add(key));
  }
  const close = (node: TreeNode) => setExpanded((s) => { const n = new Set(s); n.delete(nodeKey(node)); return n; });
  const toggle = (node: TreeNode) => (expanded.has(nodeKey(node)) ? close(node) : open(node));

  async function more(parent: TreeNode | null) {
    const key = parent ? nodeKey(parent) : "";
    const have = levels[key]?.nodes.length ?? 0;
    try {
      const r = await fetchLevel(parent ? parent.host : null, parent ? (parent.kind === "host" ? "/" : parent.path) : "", { offset: String(have) });
      setLevels((l) => ({ ...l, [key]: { nodes: [...(l[key]?.nodes ?? []), ...r.nodes], total: r.total } }));
    } catch (e) { setError(explain(e)); }
  }

  async function expandTo(depth: number) {
    const mine = ++generation.current;
    setError(""); setNote("");
    try {
      const r = await fetchLevel(null, "", { depth: String(depth) });
      if (mine !== generation.current) return;
      const next: Record<string, Level> = {};
      const open = new Set<string>();
      ingest(next, open, "", r.nodes, r.total);
      setLevels(next); setExpanded(open);
      if (r.truncated) setNote("Cây quá lớn nên chỉ mở được một phần; mở từng nhánh hoặc thu hẹp bằng bộ lọc.");
    } catch (e) { setError(explain(e)); }
  }

  const visibleRows = () => Array.from(treeRef.current?.querySelectorAll<HTMLElement>("[data-row]") ?? []);
  function onKeyDown(event: React.KeyboardEvent, node: TreeNode, parent: TreeNode | null) {
    const rows = visibleRows();
    const index = rows.findIndex((r) => r.dataset.id === nodeKey(node));
    const go = (row?: HTMLElement) => { if (row) { setFocus(row.dataset.id!); row.focus(); event.preventDefault(); } };
    const isOpen = expanded.has(nodeKey(node));
    if (event.key === "ArrowDown") go(rows[index + 1]);
    else if (event.key === "ArrowUp") go(rows[index - 1]);
    else if (event.key === "Home") go(rows[0]);
    else if (event.key === "End") go(rows[rows.length - 1]);
    else if (event.key === "ArrowRight") {
      if (node.has_children && !isOpen) { event.preventDefault(); void open(node); }
      else if (isOpen) go(rows[index + 1]);
    } else if (event.key === "ArrowLeft") {
      if (isOpen) { event.preventDefault(); close(node); }
      else if (parent) go(rows.find((r) => r.dataset.id === nodeKey(parent)));
    } else if ((event.key === "Enter" || event.key === " ") && node.has_children) { event.preventDefault(); toggle(node); }
  }

  function renderLevel(key: string, parent: TreeNode | null, depth: number) {
    const level = levels[key];
    if (!level) return null;
    return (
      <ul role={parent ? "group" : "tree"} className={parent ? "tree-group" : "tree-root"} ref={parent ? undefined : treeRef} aria-label={parent ? undefined : "Sitemap"}>
        {level.nodes.map((node) => {
          const id = nodeKey(node);
          const isOpen = expanded.has(id);
          return (
            <li key={id} role="treeitem" aria-level={depth} aria-expanded={node.has_children ? isOpen : undefined} aria-selected={focus === id}>
              <div className={"tree-row " + node.kind} data-row data-id={id} tabIndex={focus === id ? 0 : -1} style={{ paddingLeft: (depth - 1) * 18 }}
                onFocus={() => setFocus(id)} onKeyDown={(e) => onKeyDown(e, node, parent)}>
                {node.has_children ? (
                  <button type="button" tabIndex={-1} className="tree-arrow" aria-label={(isOpen ? "Thu " : "Mở ") + node.display} onClick={() => toggle(node)}>
                    {busy.has(id) ? "…" : isOpen ? "▾" : "▸"}
                  </button>
                ) : <span className="tree-arrow spacer" aria-hidden="true" />}
                <span className="tree-name" title={node.display}>{node.kind === "host" ? <strong>{node.display}</strong> : node.display}{node.kind === "dir" ? "/" : ""}</span>
                <small className="tree-count" title="Số URL trong nhánh này">{node.count.toLocaleString("vi-VN")}</small>
                {node.variants > 1 && <Chip title="Cùng đường dẫn, khác tham số">?{node.variants} biến thể</Chip>}
                {node.max_score >= 1 && <span className={"score s" + Math.min(5, Math.floor(node.max_score / 2))} title="Điểm cao nhất trong nhánh">{node.max_score}</span>}
                {node.tags.filter((t) => TAG_LABEL[t]).map((t) => <Chip key={t}>{TAG_LABEL[t]}</Chip>)}
                <Chip tone={node.verification === "historical" ? "muted" : "good"}>{node.verification === "historical" ? "lịch sử" : "đã crawl"}</Chip>
                {node.is_new && <Chip tone="good">mới</Chip>}
                {node.first_seen_scan != null && <small className="inline" title="Thấy lần đầu → gần nhất">#{node.first_seen_scan}{node.last_seen_scan !== node.first_seen_scan ? `→#${node.last_seen_scan}` : ""}</small>}
                {node.url && (
                  <span className="tree-actions">
                    <CopyButton text={node.url} label="Chép" />
                    <a className="button secondary small" href={node.url} target="_blank" rel="noopener noreferrer" aria-label={"Mở " + node.url + " trong tab mới"}>↗</a>
                  </span>
                )}
              </div>
              {isOpen && renderLevel(id, node, depth + 1)}
              {isOpen && levels[id] && levels[id].nodes.length < levels[id].total && (
                <button type="button" className="linklike tree-more" style={{ marginLeft: depth * 18 + 8 }} onClick={() => more(node)}>
                  Xem thêm ({(levels[id].total - levels[id].nodes.length).toLocaleString("vi-VN")} mục)
                </button>
              )}
            </li>
          );
        })}
      </ul>
    );
  }

  const root = levels[""];
  return (
    <div className="sitemap">
      <div className="filters" role="group" aria-label="Điều khiển cây">
        <label>Sắp xếp
          <select aria-label="Sắp xếp cây" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="az">A → Z</option><option value="score">Điểm cao nhất trước</option><option value="count">Nhiều URL nhất trước</option>
          </select>
        </label>
        <label className="treecheck"><input type="checkbox" checked={foldersFirst} onChange={(e) => setFoldersFirst(e.target.checked)} />Thư mục trước file</label>
        <button type="button" className="secondary small" onClick={() => setExpanded(new Set())}>Thu hết</button>
        <button type="button" className="secondary small" onClick={() => expandTo(2)}>Mở tới cấp 2</button>
        <button type="button" className="secondary small" onClick={() => expandTo(3)}>Mở tới cấp 3</button>
        <button type="button" className="secondary small" onClick={() => expandTo(6)}>Mở hết</button>
      </div>
      <ErrorBox text={error} />
      {note && <p className="muted" role="status">{note}</p>}
      {!root ? (error ? null : <p className="muted">Đang tải…</p>) : root.nodes.length === 0 ? <p className="empty">Không có URL phù hợp với bộ lọc.</p> : (
        <div className="tree-wrap">
          {renderLevel("", null, 1)}
          {root.nodes.length < root.total && (
            <button type="button" className="linklike tree-more" onClick={() => more(null)}>Xem thêm ({(root.total - root.nodes.length).toLocaleString("vi-VN")} host)</button>
          )}
        </div>
      )}
    </div>
  );
}
