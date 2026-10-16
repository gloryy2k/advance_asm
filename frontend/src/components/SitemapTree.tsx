import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, apiPage } from "../api/client";
import type { TreeLevel, TreeNode, UrlRow } from "../api/types";
import { explain } from "../lib/errors";
import { Chip } from "./layout";
import { CopyButton, ErrorBox, Pager } from "./ui";

type Sort = "az" | "score" | "count";
type Level = { nodes: TreeNode[]; total: number };
type Selected = { kind: "node"; node: TreeNode } | { kind: "result"; row: UrlRow };
const TAG_LABEL: Record<string, string> = {
  api: "API", auth: "đăng nhập", admin: "quản trị", sensitive: "nhạy cảm", "redirect-param": "chuyển hướng", "id-param": "tham số ID",
  "file-param": "tham số tệp", upload: "tải lên", js: "JS", docs: "tài liệu API", params: "có tham số",
};
const keyOf = (host: string, path: string) => host + "\u0000" + path;
const nodeKey = (n: TreeNode) => keyOf(n.host, n.path);
const PAGE = 200;
const RESULTS = 50;
const DEEP = 12;   // deep enough for any real path; the server stops at its node budget and says so

/** A long path may break after any "/" so it never widens the panel. */
const Breakable = ({ text }: { text: string }) => (
  <>{text.split("/").map((part, i, all) => <Fragment key={i}>{part}{i < all.length - 1 && <>/<wbr /></>}</Fragment>)}</>
);

const Icon = ({ kind }: { kind: TreeNode["kind"] }) => (
  <svg className={"tree-icon " + kind} viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false">
    {kind === "host" && <><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.3" /><path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12" fill="none" stroke="currentColor" strokeWidth="1.1" /></>}
    {kind === "dir" && <path d="M1.5 4.5h4l1.3 1.5h7.7v7h-13z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />}
    {kind === "file" && <path d="M3.5 1.5h6l3 3v10h-9z M9.5 1.5v3h3" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />}
  </svg>
);

function pathParts(url: string): { host: string; segments: string[] } {
  try {
    const u = new URL(url);
    return { host: u.host, segments: u.pathname.split("/").filter(Boolean) };
  } catch { return { host: "", segments: [] }; }
}
const decode = (s: string) => { try { return decodeURIComponent(s); } catch { return s; } };

const VERIFY = { historical: "Lịch sử — chỉ cho biết URL từng tồn tại", observed: "Đã crawl thấy trên host đang chạy", live: "Đang chạy" } as const;

function Detail({ item, onReveal }: { item: Selected | null; onReveal: (row: UrlRow) => void }) {
  if (!item) return <p className="muted">Chọn một mục trong cây để xem đường dẫn đầy đủ, nguồn và các scan đã thấy nó.</p>;
  const isNode = item.kind === "node";
  const url = isNode ? item.node.url : item.row.url;
  const host = isNode ? item.node.host : pathParts(item.row.url).host;
  const path = isNode ? (item.node.kind === "host" ? "/" : item.node.path) : "/" + pathParts(item.row.url).segments.join("/");
  const tags = isNode ? item.node.tags : item.row.tags;
  const verification = (isNode ? item.node.verification : item.row.verification) as keyof typeof VERIFY;
  const first = isNode ? item.node.first_seen_scan : item.row.first_seen_scan;
  const last = isNode ? item.node.last_seen_scan : item.row.last_seen_scan;
  const crumbs = isNode ? [host, ...path.split("/").filter(Boolean).map(decode)] : [host, ...pathParts(item.row.url).segments.map(decode)];
  const sources = isNode ? item.node.sources || [] : [item.row.source];
  return (
    <div className="tree-detail" data-testid="tree-detail">
      <p className="tree-label">Đường dẫn đầy đủ</p>
      <p className="tree-fullpath"><Breakable text={decode(`${host}${path}`)} /></p>
      <p className="tree-crumb" aria-label="Vị trí trong cây">{crumbs.join(" › ")}</p>
      <dl className="tree-facts">
        <div><dt>URL trong nhánh</dt><dd>{(isNode ? item.node.count : 1).toLocaleString("vi-VN")}</dd></div>
        {isNode && item.node.variants > 1 && <div><dt>Biến thể query</dt><dd>?{item.node.variants} biến thể (cùng đường dẫn, khác tham số)</dd></div>}
        <div><dt>Điểm {isNode ? "cao nhất" : ""}</dt><dd>{isNode ? item.node.max_score : item.row.score}</dd></div>
        <div><dt>Mức kiểm chứng</dt><dd>{VERIFY[verification] || verification}</dd></div>
        <div><dt>Nguồn</dt><dd>{sources.length ? sources.join(", ") : "—"}</dd></div>
        <div><dt>Scan thấy</dt><dd>{first != null ? `#${first}${last !== first ? ` → #${last}` : ""}` : "—"}{(isNode ? item.node.is_new : item.row.is_new) && <> <Chip tone="good">mới</Chip></>}</dd></div>
      </dl>
      {tags.filter((t) => TAG_LABEL[t]).length > 0 && <p className="tree-tags">{tags.filter((t) => TAG_LABEL[t]).map((t) => <Chip key={t}>{TAG_LABEL[t]}</Chip>)}</p>}
      {url && (
        <>
          <p className="tree-label">{isNode && item.node.kind !== "file" ? "URL đại diện" : "URL"}</p>
          <p className="tree-url"><code><Breakable text={url} /></code></p>
          <div className="actions">
            <CopyButton text={url} label="Chép URL" />
            <a className="button secondary small" href={url} target="_blank" rel="noopener noreferrer" aria-label={"Mở " + url + " trong tab mới"}>Mở tab mới ↗</a>
            {!isNode && <button type="button" className="secondary small" onClick={() => onReveal(item.row)}>Xem trong cây</button>}
          </div>
        </>
      )}
    </div>
  );
}

/** URL inventory as a sitemap (host → folders → files), loaded one level at a time. Rows are compact; details live in the side panel. */
export function SitemapTree({ base, query, term, onClearSearch }: { base: string; query: URLSearchParams; term: string; onClearSearch: () => void }) {
  const searching = !!term;
  const [sort, setSort] = useState<Sort>("az");
  const [foldersFirst, setFoldersFirst] = useState(false);
  const [levels, setLevels] = useState<Record<string, Level>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [focus, setFocus] = useState("");
  const [selected, setSelected] = useState<Selected | null>(null);
  const [results, setResults] = useState<{ items: UrlRow[]; total: number } | null>(null);
  const [offset, setOffset] = useState(0);
  const treeRef = useRef<HTMLUListElement>(null);
  const generation = useRef(0);   // answers that arrive after a filter/sort change are ignored
  const pendingReveal = useRef<UrlRow | null>(null);

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
    p.delete("q");   // the tree shows the whole inventory; a search is answered by the flat result list
    if (host) { p.set("host", host); p.set("prefix", path); }
    p.set("limit", String(PAGE));
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return api<TreeLevel>(`${base}/tree?${p}`);
  }, [base, params]);

  // Tree: reload whenever the filters (other than the search text) or the sort change.
  const treeParams = useMemo(() => { const p = new URLSearchParams(params); p.delete("q"); return p.toString(); }, [params]);
  useEffect(() => {
    const mine = ++generation.current;
    setError(""); setNote("");
    fetchLevel(null, "", { depth: "1" }).then(async (r) => {
      if (mine !== generation.current) return;
      const next: Record<string, Level> = {};
      ingest(next, null, "", r.nodes, r.total);
      setLevels(next);
      setExpanded(new Set());
      setFocus((f) => f || (r.nodes[0] ? nodeKey(r.nodes[0]) : ""));
      const wanted = pendingReveal.current;
      if (wanted) { pendingReveal.current = null; await revealRow(wanted, next, mine); }
    }).catch((e) => mine === generation.current && setError(explain(e)));
  }, [treeParams, ingest]);   // eslint-disable-line react-hooks/exhaustive-deps

  // "Xem trong cây": once the search is cleared and the tree is showing, walk to the URL that was picked.
  useEffect(() => {
    const wanted = pendingReveal.current;
    if (searching || !wanted || !levels[""]) return;
    pendingReveal.current = null;
    void revealRow(wanted, levels, generation.current);
  }, [searching, levels]);   // eslint-disable-line react-hooks/exhaustive-deps

  // Search: a flat list grouped by host, never hundreds of auto-opened branches.
  useEffect(() => { setOffset(0); }, [term, params]);
  useEffect(() => {
    if (!searching) { setResults(null); return; }
    let live = true;
    const p = new URLSearchParams(query);
    p.set("limit", String(RESULTS)); p.set("offset", String(offset));
    apiPage<UrlRow>(`${base}?${p}`).then((r) => live && (setResults(r), setError(""))).catch((e) => live && setError(explain(e)));
    return () => { live = false; };
  }, [searching, base, query, offset]);

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
      if (r.truncated) setNote(`Cây có ${(r.matched ?? 0).toLocaleString("vi-VN")} URL, quá lớn để mở hết cùng lúc: chỉ một phần được mở. Mở từng nhánh hoặc thu hẹp bằng bộ lọc.`);
    } catch (e) { setError(explain(e)); }
  }

  /** Open the host and every folder on the way to a URL, one level request each, then select it. */
  async function revealRow(row: UrlRow, start: Record<string, Level>, mine: number) {
    const { host, segments } = pathParts(row.url);
    let local = { ...start };
    const openKeys = new Set<string>();
    let parentNodes = local[""]?.nodes || [];
    let target: TreeNode | undefined = parentNodes.find((n) => n.kind === "host" && n.host === host.toLowerCase());
    if (!target) { setNote("Không tìm thấy vị trí này trong cây với bộ lọc hiện tại."); return; }
    let reached: TreeNode = target;       // the deepest node that exists (a filter can hide the last steps)
    try {
      for (let i = 0; i < segments.length; i++) {
        if (!target || !target.has_children) break;
        const key = nodeKey(target);
        if (!local[key]) {
          const r = await fetchLevel(target.host, target.kind === "host" ? "/" : target.path);
          if (mine !== generation.current) return;
          local = { ...local, [key]: { nodes: r.nodes, total: r.total } };
        }
        openKeys.add(key);
        target = local[key].nodes.find((n) => n.name === segments[i]);
        if (target) reached = target;
      }
    } catch (e) { setError(explain(e)); return; }
    setLevels(local);
    setExpanded(openKeys);
    setSelected({ kind: "node", node: reached });
    setFocus(nodeKey(reached));
    setTimeout(() => treeRef.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(nodeKey(reached))}"]`)?.scrollIntoView?.({ block: "center" }), 0);
  }
  function reveal(row: UrlRow) {
    pendingReveal.current = row;
    onClearSearch();          // the tree then reloads itself and walks to the URL
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
          const isSel = selected?.kind === "node" && nodeKey(selected.node) === id;
          return (
            <li key={id} role="treeitem" aria-level={depth} aria-expanded={node.has_children ? isOpen : undefined} aria-selected={isSel}>
              <div className={"tree-row " + node.kind + (isSel ? " selected" : "")} data-row data-id={id} tabIndex={focus === id ? 0 : -1}
                onFocus={() => { setFocus(id); setSelected({ kind: "node", node }); }} onClick={() => { setFocus(id); setSelected({ kind: "node", node }); }}
                onKeyDown={(e) => onKeyDown(e, node, parent)}>
                {node.has_children ? (
                  <button type="button" tabIndex={-1} className="tree-arrow" aria-label={(isOpen ? "Thu " : "Mở ") + node.display} onClick={(e) => { e.stopPropagation(); void toggle(node); }}>
                    {busy.has(id) ? "…" : isOpen ? "▾" : "▸"}
                  </button>
                ) : <span className="tree-arrow spacer" aria-hidden="true" />}
                <Icon kind={node.kind} />
                <span className="tree-name" title={node.display}>{node.kind === "host" ? <strong>{node.display}</strong> : node.display}{node.kind === "dir" ? "/" : ""}</span>
                <small className="tree-count" title="Số URL trong nhánh này">{node.count.toLocaleString("vi-VN")}</small>
              </div>
              {isOpen && renderLevel(id, node, depth + 1)}
              {isOpen && levels[id] && levels[id].nodes.length < levels[id].total && (
                <button type="button" className="linklike tree-more" onClick={() => more(node)}>
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
  const grouped = useMemo(() => {
    const map = new Map<string, UrlRow[]>();
    for (const row of results?.items || []) {
      const host = row.host || pathParts(row.url).host;
      map.set(host, [...(map.get(host) || []), row]);
    }
    return [...map.entries()];
  }, [results]);
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
        <button type="button" className="secondary small" onClick={() => expandTo(DEEP)}>Mở hết</button>
      </div>
      <ErrorBox text={error} />
      {note && <p className="muted" role="status">{note}</p>}
      <div className="tree-split">
        <section className="tree-panel" aria-label={searching ? "Kết quả tìm kiếm" : "Cây sitemap"}>
          {searching ? (
            <div className="tree-results" data-testid="tree-results">
              <p className="tree-filter-note" role="status">
                {results === null ? "Đang tìm…" : <>Tìm “<strong>{term}</strong>”: <strong>{results.total.toLocaleString("vi-VN")}</strong> URL khớp, nhóm theo host.</>}{" "}
                <button type="button" className="linklike" onClick={onClearSearch}>Xóa tìm kiếm</button>
              </p>
              {results && results.items.length === 0 && <p className="empty">Không có URL khớp.</p>}
              {grouped.map(([host, rows]) => (
                <div key={host} className="result-group">
                  <h3 className="result-host">{host} <small>{rows.length}</small></h3>
                  {rows.map((row) => {
                    const { segments } = pathParts(row.url);
                    const active = selected?.kind === "result" && selected.row.id === row.id;
                    return (
                      <button type="button" key={row.id} className={"result" + (active ? " selected" : "")} aria-pressed={active} onClick={() => setSelected({ kind: "result", row })}>
                        <span className="result-url"><Breakable text={decode(row.url.replace(/^https?:\/\//, ""))} /></span>
                        <small className="result-crumb">{[host, ...segments.map(decode)].join(" › ")}</small>
                      </button>
                    );
                  })}
                </div>
              ))}
              {results && <Pager total={results.total} limit={RESULTS} offset={offset} onChange={setOffset} />}
            </div>
          ) : !root ? (error ? null : <p className="muted">Đang tải…</p>) : root.nodes.length === 0 ? <p className="empty">Không có URL phù hợp với bộ lọc.</p> : (
            <div className="tree-wrap">
              {renderLevel("", null, 1)}
              {root.nodes.length < root.total && (
                <button type="button" className="linklike tree-more" onClick={() => more(null)}>Xem thêm ({(root.total - root.nodes.length).toLocaleString("vi-VN")} host)</button>
              )}
            </div>
          )}
        </section>
        <aside className="tree-side" aria-label="Chi tiết" aria-live="polite">
          <Detail item={selected} onReveal={reveal} />
        </aside>
      </div>
    </div>
  );
}
