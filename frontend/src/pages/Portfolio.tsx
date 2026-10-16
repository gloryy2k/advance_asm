import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { Draft, Health, ProgramCard } from "../api/types";
import { Badge, EmptyState, ErrorBox, State, StatusBadge } from "../components/ui";
import { useData } from "../hooks/useData";
import { useHealth } from "../hooks/useHealth";
import { explain } from "../lib/errors";
import { programPath } from "../lib/router";
import { when } from "../lib/format";

function attention(p: ProgramCard): string[] {
  const out: string[] = [];
  const s = p.latest_scan?.status;
  if (s === "failed") out.push("Scan lỗi");
  if (s === "running" || s === "queued") out.push("Đang quét");
  if (p.draft_count) out.push(`${p.draft_count} bản nháp chờ review`);
  if (!p.monitoring) out.push("Chưa bật monitoring");
  return out;
}

export function Portfolio() {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const programs = useData<ProgramCard[]>("/api/programs" + (showArchived ? "?archived=include" : ""), revision);
  const drafts = useData<Draft[]>("/api/drafts", revision);
  const health = useHealth();
  const list = programs.data || [];
  const totalNew = list.reduce((n, p) => n + p.new_count, 0);

  async function remove(id: number) {
    if (!confirm("Xoá bản nháp này?")) return;
    try {
      await api("/api/scans/" + id, { method: "DELETE" });
      setRevision((v) => v + 1);
    } catch (e) {
      setError(explain(e));
    }
  }
  // Bulk cleanup: filter, sort and pick by hand. Nothing is selected for you.
  const [find, setFind] = useState("");
  const [sort, setSort] = useState<"new" | "old" | "name">("new");
  const [origin, setOrigin] = useState("");
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [result, setResult] = useState("");
  const shownDrafts = useMemo(() => {
    const items = (drafts.data || []).filter((d) => (!origin || d.source === origin) && (!find || d.slug.toLowerCase().includes(find.toLowerCase())));
    return [...items].sort((a, b) => sort === "name" ? a.slug.localeCompare(b.slug) : sort === "old" ? a.id - b.id : b.id - a.id);
  }, [drafts.data, find, sort, origin]);
  const toggle = (id: number) => setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  async function removePicked() {
    const chosen = (drafts.data || []).filter((d) => picked.has(d.id));
    if (!chosen.length) return;
    if (!confirm(`Xoá ${chosen.length} bản nháp?\n` + chosen.slice(0, 15).map((d) => `#${d.id} ${d.slug}`).join("\n") + (chosen.length > 15 ? `\n… và ${chosen.length - 15} bản nữa` : ""))) return;
    try {
      const r = await api<{ deleted: number[]; skipped: { id: number; reason: string }[] }>("/api/drafts/delete", { method: "POST", body: JSON.stringify({ ids: chosen.map((d) => d.id) }) });
      setResult(`Đã xoá ${r.deleted.length} bản nháp.` + (r.skipped.length ? ` Bỏ qua ${r.skipped.length} bản (đã được launch hoặc không còn): ${r.skipped.map((x) => "#" + x.id).join(", ")}.` : ""));
      setPicked(new Set());
      setRevision((v) => v + 1);
    } catch (e) { setError(explain(e)); }
  }
  const toolsMissing = health.data?.missing_by_depth?.light?.length || 0;
  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">ATTACK SURFACE MANAGEMENT</p>
          <h1>Danh mục</h1>
          <p>Theo dõi thay đổi của các program. Bắt đầu từ đúng scope.</p>
        </div>
        <a className="button" href="#/new">+ Thêm program</a>
      </div>
      <ErrorBox text={error} />
      {health.data?.runtime && !health.data.runtime.recon_supported && <p className="warnbox">⚠ {health.data.runtime.reason}</p>}
      {(drafts.data?.length || 0) > 0 && (
        <section className="card" aria-labelledby="drafts-h">
          <h2 id="drafts-h">Bản nháp chờ review ({drafts.data!.length})</h2>
          <p className="muted">Bản nháp chưa launch tự bị xoá sau 7 ngày. Chọn tay những bản muốn xoá ngay; bản đã được launch sẽ không bị đụng tới.</p>
          <div className="filters" role="group" aria-label="Lọc bản nháp">
            <input aria-label="Lọc bản nháp theo tên" placeholder="Lọc theo tên program…" value={find} onChange={(e) => setFind(e.target.value)} />
            <select aria-label="Nguồn bản nháp" value={origin} onChange={(e) => setOrigin(e.target.value)}>
              <option value="">Mọi nguồn</option><option value="h1">HackerOne</option><option value="raw">Nhập tay</option>
            </select>
            <select aria-label="Sắp xếp bản nháp" value={sort} onChange={(e) => setSort(e.target.value as "new" | "old" | "name")}>
              <option value="new">Mới nhất trước</option><option value="old">Cũ nhất trước</option><option value="name">Theo tên</option>
            </select>
            <button type="button" className="secondary small" onClick={() => setPicked(new Set(shownDrafts.map((d) => d.id)))}>Chọn các bản đang hiện ({shownDrafts.length})</button>
            <button type="button" className="secondary small" onClick={() => setPicked(new Set())} disabled={picked.size === 0}>Bỏ chọn</button>
            <button type="button" className="danger small" onClick={removePicked} disabled={picked.size === 0}>Xoá {picked.size} bản đã chọn</button>
          </div>
          {result && <p className="okline" role="status">{result}</p>}
          {shownDrafts.map((d) => (
            <div className="draftrow" key={d.id}>
              <label className="check inline">
                <input type="checkbox" aria-label={"Chọn bản nháp #" + d.id} checked={picked.has(d.id)} onChange={() => toggle(d.id)} />
                <span><strong>{d.slug}</strong> · scan #{d.id} · {d.source} · {d.in} IN / {d.out} OUT · {when(d.created_at)}</span>
              </label>
              <span>
                <a className="button small" href={"#/scan/" + d.id + "/review"}>Tiếp tục review</a>{" "}
                <button className="secondary small" onClick={() => remove(d.id)}>Xoá</button>
              </span>
            </div>
          ))}
          {shownDrafts.length === 0 && <p className="muted">Không có bản nháp nào khớp bộ lọc.</p>}
        </section>
      )}
      <label className="check inline"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />Hiện cả program đã lưu trữ</label>
      <State data={programs.data} error={programs.error} retry={() => setRevision((v) => v + 1)}>
        {list.length > 0 && (
          <div className="metrics">
            <div><strong>{list.length}</strong>Programs</div>
            <div><strong>{list.reduce((n, p) => n + p.asset_count, 0)}</strong>Host trong inventory</div>
            <div><strong>{totalNew}</strong>Asset mới (scan gần nhất)</div>
          </div>
        )}
        <div className="grid">
          {list.map((p) => {
            const flags = attention(p);
            return (
              <a className={"card program" + (p.archived_at ? " archived" : "")} href={"#" + programPath(p.slug)} key={p.id}>
                <div>
                  <Badge>{p.source}</Badge>{p.archived_at && <Badge tone="muted">Đã lưu trữ</Badge>}
                  <StatusBadge status={p.latest_scan?.status} />
                </div>
                <h2>{p.slug}</h2>
                <p>
                  {p.asset_count} host {p.new_count > 0 && <span className="accent">+{p.new_count} NEW</span>}
                  {p.finding_count > 0 && <span className="muted"> · {p.finding_count} findings</span>}
                </p>
                <small>
                  Scan #{p.latest_scan?.id || "—"} · {p.latest_scan?.depth || "—"}
                </small>
                {flags.length > 0 && <small className="flags">{flags.join(" · ")}</small>}
              </a>
            );
          })}
        </div>
        {list.length === 0 && (
          <EmptyState
            title="Chưa có program nào"
            action={<a className="button" href="#/new">Thêm program đầu tiên</a>}
          >
            Quy trình 3 bước: <strong>1.</strong> nhập scope (HackerOne hoặc raw) → <strong>2.</strong> xem lại policy, scope,
            mức quét → <strong>3.</strong> chạy; xong bạn nhận thư mục + brief để <code>cd … &amp;&amp; claude</code>.
            Nên bắt đầu bằng mức <em>Passive</em> để thử mà không chạm target.
          </EmptyState>
        )}
      </State>
      <details className="card">
        <summary>
          Tình trạng công cụ{health.data && toolsMissing > 0 ? ` — thiếu ${health.data.missing_by_depth.light.join(", ")} cho mức Light` : ""}
        </summary>
        <p><a href="#/tools">Mở trang Công cụ &amp; môi trường →</a></p>
        <ErrorBox text={health.error} />
        {Object.entries(health.data?.tools || {}).map(([name, ok]) => {
          const optional = !ok && (health.data?.optional_tools || []).includes(name);   // nothing in a scan depends on it
          return <Badge key={name} tone={ok ? "done" : optional ? "muted" : "failed"}>{name + ": " + (ok ? "sẵn sàng" : optional ? "tùy chọn, chưa cài" : "thiếu")}</Badge>;
        })}
      </details>
    </>
  );
}
