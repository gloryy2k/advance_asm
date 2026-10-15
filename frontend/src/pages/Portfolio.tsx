import { useState } from "react";
import { api } from "../api/client";
import type { Draft, Health, ProgramCard } from "../api/types";
import { Badge, EmptyState, ErrorBox, State, StatusBadge } from "../components/ui";
import { useData } from "../hooks/useData";
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
  const programs = useData<ProgramCard[]>("/api/programs", revision);
  const drafts = useData<Draft[]>("/api/drafts", revision);
  const health = useData<Health>("/api/health");
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
          {drafts.data!.map((d) => (
            <div className="draftrow" key={d.id}>
              <span><strong>{d.slug}</strong> · scan #{d.id} · {d.in} IN / {d.out} OUT · {when(d.created_at)}</span>
              <span>
                <a className="button small" href={"#/scan/" + d.id + "/review"}>Tiếp tục review</a>{" "}
                <button className="secondary small" onClick={() => remove(d.id)}>Xoá</button>
              </span>
            </div>
          ))}
        </section>
      )}
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
              <a className="card program" href={"#" + programPath(p.slug)} key={p.id}>
                <div>
                  <Badge>{p.source}</Badge>
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
        <ErrorBox text={health.error} />
        {Object.entries(health.data?.tools || {}).map(([name, ok]) => {
          const optional = !ok && (health.data?.optional_tools || []).includes(name);   // nothing in a scan depends on it
          return <Badge key={name} tone={ok ? "done" : optional ? "muted" : "failed"}>{name + ": " + (ok ? "sẵn sàng" : optional ? "tùy chọn, chưa cài" : "thiếu")}</Badge>;
        })}
      </details>
    </>
  );
}
