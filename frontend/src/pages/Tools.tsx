import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Depth, ToolRow, ToolsReport } from "../api/types";
import { PageHead, Panel } from "../components/layout";
import { Badge, ErrorBox, State } from "../components/ui";
import { useData } from "../hooks/useData";
import { explain } from "../lib/errors";
import { when } from "../lib/format";
import { TemplatePanel } from "../components/TemplatePanel";

const STATE_LABEL: Record<ToolRow["state"], string> = {
  ready: "Sẵn sàng", missing_binary: "Chưa cài", missing_data: "Thiếu dữ liệu", wrong_binary: "Sai công cụ",
};
const DEPTH_LABEL: Record<Depth, string> = { passive: "Passive", light: "Light", strong: "Strong" };

function ImpactChips({ row }: { row: ToolRow }) {
  return (
    <span className="impact">
      {(Object.keys(DEPTH_LABEL) as Depth[]).map((d) => {
        const text = row.impact[d];
        if (text === "unused") return null;
        const bad = text.startsWith("Bước bị bỏ qua");
        return <span key={d} className={"chip " + (bad ? "warn" : text === "optional" ? "muted" : "good")} title={bad ? text : undefined}>{DEPTH_LABEL[d]}{bad ? " ✕" : ""}</span>;
      })}
    </span>
  );
}

function Row({ row, focused }: { row: ToolRow; focused: boolean }) {
  const ref = useRef<HTMLTableRowElement>(null);
  useEffect(() => { if (focused) ref.current?.scrollIntoView?.({ block: "center" }); }, [focused]);
  const tone = row.state === "ready" ? "done" : row.optional || row.kind === "framework" ? (row.kind === "framework" ? "failed" : "muted") : "failed";
  return (
    <tr ref={ref} className={focused ? "focusrow" : ""} id={"tool-" + row.id}>
      <td><strong>{row.label}</strong><small>{row.purpose}</small></td>
      <td>
        <Badge tone={tone}>{STATE_LABEL[row.state]}{row.state !== "ready" && row.optional && row.kind === "binary" ? " · tùy chọn" : ""}</Badge>
        {row.state !== "ready" && <small>{row.detail}</small>}
      </td>
      <td>
        {row.version ? <>{row.version}{row.checked_at && <small>kiểm lúc {when(row.checked_at)}</small>}</> : <span className="muted">chưa kiểm</span>}
        {row.pinned_version && <small>ghim: {row.pinned_version}</small>}
      </td>
      <td>{row.used_by.length ? row.used_by.map((u) => u.title).join(", ") : <span className="muted">—</span>}</td>
      <td>
        <ImpactChips row={row} />
        {row.state !== "ready" && row.remedy && <small className="remedy">{row.remedy}</small>}
      </td>
    </tr>
  );
}

function Group({ title, hint, rows, focus }: { title: string; hint: string; rows: ToolRow[]; focus: string }) {
  if (!rows.length) return null;
  return (
    <Panel title={title} hint={hint}>
      <div className="table-wrap" tabIndex={0} role="region" aria-label={title}>
        <table>
          <thead><tr><th>Công cụ</th><th>Trạng thái</th><th>Phiên bản</th><th>Dùng ở bước</th><th>Ảnh hưởng theo mức quét</th></tr></thead>
          <tbody>{rows.map((r) => <Row key={r.id} row={r} focused={focus === r.id} />)}</tbody>
        </table>
      </div>
    </Panel>
  );
}

export function Tools({ focus }: { focus: string }) {
  const [revision, setRevision] = useState(0);
  const report = useData<ToolsReport>("/api/tools", revision);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fresh, setFresh] = useState<ToolsReport | null>(null);
  const data = fresh || report.data;
  async function check() {
    setBusy(true); setError("");
    try { setFresh(await api<ToolsReport>("/api/tools/check", { method: "POST" })); } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }
  const rows = data?.tools || [];
  const summary = data?.summary;
  return (
    <>
      <PageHead eyebrow="MÔI TRƯỜNG" title="Công cụ & môi trường"
        sub="Công cụ và dữ liệu mà các bước quét cần. Trang này chỉ tìm tệp; không chạy công cụ hay chạm target (trừ nút kiểm phiên bản bên dưới)."
        actions={<button onClick={check} disabled={busy}>{busy ? "Đang kiểm…" : "Kiểm phiên bản (chạy -version)"}</button>} />
      <ErrorBox text={error} />
      <State data={data} error={report.error} retry={() => setRevision((v) => v + 1)}>
        {summary && (
          <p className={summary.missing_required.length ? "warnbox" : "okline"} role="status" data-testid="tools-summary">
            {summary.missing_required.length
              ? <>Thiếu công cụ cần cho scan: <strong>{summary.missing_required.join(", ")}</strong>. Các bước dùng chúng sẽ bị bỏ qua ở mức quét tương ứng; không phải scan nào cũng hỏng.</>
              : <>Mọi công cụ cần cho Passive/Light/Strong đều có.</>}
            {summary.missing_optional.length > 0 && <> Tùy chọn chưa cài (không ảnh hưởng): {summary.missing_optional.join(", ")}.</>}
          </p>
        )}
        <Group title="Cần cho các mức quét" hint="Thiếu một công cụ: bước dùng nó bị bỏ qua và Review ghi rõ." rows={rows.filter((r) => r.required_for.length > 0)} focus={focus} />
        <TemplatePanel info={rows.find((r) => r.id === "nuclei-templates")?.templates} nucleiReady={rows.find((r) => r.id === "nuclei")?.state === "ready"}
          onChanged={() => { setFresh(null); setRevision((v) => v + 1); }} />
        <Group title="Tùy chọn" hint="Không scan nào phụ thuộc. Thiếu chỉ làm mất một bước phụ." rows={rows.filter((r) => r.required_for.length === 0 && r.kind !== "framework")} focus={focus} />
        <Group title="Bộ khung recon" hint="Tệp của bộ khung đi kèm. Thiếu nghĩa là cấu hình sai đường dẫn." rows={rows.filter((r) => r.kind === "framework")} focus={focus} />
      </State>
    </>
  );
}
