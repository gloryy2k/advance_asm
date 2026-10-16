import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PhaseReport, ReviewData, ScanPhases, ScanRow, Summary } from "../api/types";
import { ArtifactViewer } from "../components/ArtifactViewer";
import { HuntCard } from "../components/HuntCard";
import { PageHead, Panel } from "../components/layout";
import { ScanLog } from "../components/ScanLog";
import { ScanProgress } from "../components/ScanProgress";
import { StepList, type StepRow } from "../components/StepList";
import { Badge, ErrorBox, StatusBadge } from "../components/ui";
import { useData } from "../hooks/useData";
import { useScanStream } from "../hooks/useScanStream";
import { explain } from "../lib/errors";
import { TERMINAL, durationLabel } from "../lib/format";
import { dataLink, go, programPath } from "../lib/router";

function Elapsed({ since, until, running }: { since?: string | null; until?: string | null; running: boolean }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  if (!since) return null;
  const end = until ? new Date(until).getTime() : now;  // a finished scan shows how long it took, not time since
  return <span className="muted">{until ? "Mất" : "Đã chạy"} {durationLabel(Math.max(0, (end - new Date(since).getTime()) / 1000))}</span>;
}

export function Run({ id }: { id: string }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [viewer, setViewer] = useState<PhaseReport | null>(null);
  const state = useData<ScanRow>("/api/scans/" + id, revision, 3000);
  const status = state.data?.status;
  const finished = TERMINAL.has(status || "");
  const info = useData<ReviewData>("/api/scans/" + id + "/review", finished ? 1 : 0);
  const report = useData<ScanPhases>(status === "draft" ? null : "/api/scans/" + id + "/phases", revision, 3000);
  const slugNow = info.data?.slug;
  const programSummary = useData<Summary>(slugNow && finished ? "/api/programs/" + encodeURIComponent(slugNow) + "/summary" : null);
  const stream = useScanStream(id, finished, () => setRevision((v) => v + 1));
  const [warningsOnly, setWarningsOnly] = useState(false);

  async function cancel() {
    try {
      await api("/api/scans/" + id + "/cancel", { method: "POST" });
      setConfirming(false);
      setRevision((v) => v + 1);
    } catch (e) { setError(explain(e)); }
  }
  async function again() {
    if (!info.data) return;
    try {
      const made = await api("/api/programs/" + encodeURIComponent(info.data.slug) + "/rescan", { method: "POST" });
      go("/scan/" + made.scan_id + "/review");
    } catch (e) { setError(explain(e)); }
  }
  const slug = info.data?.slug;
  const good = status === "done" || status === "done_partial";
  const rows: StepRow[] = (report.data?.phases || []).map((p) => ({
    key: p.key, title: p.title, what: p.what, touches: p.touches, status: p.status, statusLabel: p.status_label,
    reason: p.reason, detail: p.detail, count: p.count, countLabel: p.count_label,
  }));
  const byKey = new Map((report.data?.phases || []).map((p) => [p.key, p]));
  const funnel = report.data?.funnel;
  const running = !finished && status !== "draft";
  // Links open the program's data. An older scan is not the program's current view, and the page says so.
  const currentId = programSummary.data?.last_completed_scan?.id;
  const older = good && currentId !== undefined && currentId !== Number(id);
  const urlScan = older ? id : undefined;

  return (
    <>
      <PageHead eyebrow={running ? "BƯỚC 3/3 · ĐANG QUÉT" : "KẾT QUẢ SCAN"} title={<>Scan #{id} {slug && <small className="inline">· {slug}</small>}</>}
        sub={running ? "Bạn có thể đóng trang; scan vẫn chạy trong nền." : undefined} />
      <ErrorBox text={error || state.error} />
      <div className="statusrow">
        <span role="status" aria-label="Scan status"><StatusBadge status={status} /></span>
        {status === "draft" && <a href={"#/scan/" + id + "/review"}>Quay lại Xem lại →</a>}
        <Elapsed since={state.data?.started_at} until={finished ? state.data?.finished_at : null} running={status === "running"} />
        {running && (confirming ? (
          <>
            <button className="danger" onClick={cancel}>Xác nhận huỷ scan</button>
            <button className="secondary" onClick={() => setConfirming(false)}>Giữ lại</button>
          </>
        ) : <button className="secondary" disabled={!status} onClick={() => setConfirming(true)}>Cancel scan</button>)}
        {slug && <a href={"#" + programPath(slug)}>Mở program →</a>}
      </div>

      {older && (
        <p className="notice" role="note" data-testid="older-scan-note">
          Scan #{id} không phải scan mới nhất của program (hiện là #{currentId}). URL mở theo “ghi nhận tới scan #{id}”; Host, Findings và Brief là hiện trạng của program, không riêng scan này.
        </p>
      )}
      {status === "done_partial" && <p className="warnbox">Scan hoàn tất một phần: một số giai đoạn hết thời gian, nguồn lỗi hoặc host chưa được probe (xem "Giai đoạn & độ phủ"). Dữ liệu có được vẫn đã nạp; không suy ra host vắng là đã biến mất.</p>}
      {state.data?.error && good && <p className="muted" data-testid="partial-reason">Lý do: {state.data.error}</p>}
      {(status === "failed" || status === "cancelled") && (
        <Panel id="fail-h" title={status === "failed" ? "Scan lỗi" : "Scan đã huỷ"} tone="warn">
          {state.data?.error && <p className="error">{state.data.error}</p>}
          <p>Dữ liệu đã có (nếu có) vẫn xem được bên dưới. Tạo bản nháp mới với cùng scope để chỉnh và chạy lại.</p>
          <button onClick={again}>Tạo scan mới (cùng scope)</button>
        </Panel>
      )}
      {good && info.data && (
        <>
          <HuntCard command={info.data.hunt_command} note={info.data.hunt_note} title="Hoàn tất → bắt đầu hunt" />
          <p className="row">
            <a className="button" href={"#" + programPath(info.data.slug, "guide", "brief")}>{older ? `Xem Brief hiện hành (scan #${currentId})` : "Xem Brief"}</a>
            <a className="button secondary" href={"#" + programPath(info.data.slug)}>Tổng quan program</a>
          </p>
        </>
      )}

      {status !== "draft" && report.data && (
        <Panel id="stages-h" title="Giai đoạn & độ phủ"
          hint="Scan chạy theo giai đoạn có ngân sách thời gian riêng: khám phá → host nêu trong scope → probe host đã khám phá → quét sâu. Hết ngân sách thì giai đoạn dừng, dữ liệu đã có vẫn được nạp.">
          <ScanProgress data={report.data} partial={status === "done_partial"} />
        </Panel>
      )}

      {status !== "draft" && (
        <Panel id="steps-h" title="Kết quả theo bước"
          hint={running ? "Cập nhật mỗi 3 giây. Mỗi dòng là một chức năng: nó làm gì, đã chạy chưa, tìm được bao nhiêu, và xem kết quả ở đâu."
            : "Mỗi dòng là một chức năng: nó làm gì, đã chạy chưa, tìm được bao nhiêu, và xem kết quả ở đâu."}>
          {report.data === null ? <p className="muted">Đang tải…</p> : (
            <StepList rows={rows}
              action={(r) => {
                const phase = byKey.get(r.key);
                if (!phase || !slug) return null;
                const hasFiles = phase.files.some((f) => (f.lines ?? 1) > 0);
                return (
                  <span className="step-actions">
                    {phase.view.kind !== "file" && (r.status === "ran" || r.status === "partial" || r.status === "empty") && (
                      <a className="button small" href={dataLink(slug, phase.view, urlScan)}>{phase.view.label} →</a>
                    )}
                    {hasFiles && (
                      <button className="secondary small" onClick={() => setViewer(phase)}>
                        {phase.view.kind === "file" ? phase.view.label : "Đọc file thô"} ({phase.files.length})
                      </button>
                    )}
                  </span>
                );
              }} />
          )}
          {report.data?.missing_tools && report.data.missing_tools.length > 0 && (
            <p className="muted">Công cụ không có trên máy chủ: {report.data.missing_tools.join(", ")}. <a href={"#/tools?focus=" + report.data.missing_tools[0]}>Xem trang Công cụ →</a></p>
          )}
        </Panel>
      )}

      {funnel && (
        <Panel id="funnel-h" title="URL thu được" hint="Chỉ URL qua scope gate mới được giữ. URL lịch sử chưa được kiểm chứng.">
          <p>
            <strong>{funnel.raw.toLocaleString("vi-VN")}</strong> URL do tool tìm thấy → <strong>{funnel.in_scope.toLocaleString("vi-VN")}</strong> trong scope
            {!!funnel.from_probe && <> + <strong>{funnel.from_probe.toLocaleString("vi-VN")}</strong> URL từ probe HTTP (host trả lời) = <strong>{(funnel.stored ?? funnel.in_scope + funnel.from_probe).toLocaleString("vi-VN")}</strong> URL lưu cho scan này</>}
            {funnel.out_of_scope > 0 && <>, <Badge tone="medium">{funnel.out_of_scope.toLocaleString("vi-VN")} ngoài scope đã loại</Badge></>}
            {!!funnel.excluded_by_rule && <>, {funnel.excluded_by_rule} loại theo mẫu của bạn</>}
            {!!funnel.path_rule_blocked && <>, <Badge tone="medium">{funnel.path_rule_blocked.toLocaleString("vi-VN")} chặn theo OUT đường dẫn</Badge></>}.{" "}
            {slug && <a href={dataLink(slug, { kind: "urls" }, urlScan)}>Xem URL →</a>}
          </p>
        </Panel>
      )}

      {status !== "draft" && (
        <details className="adv">
          <summary>Nhật ký kỹ thuật ({stream.events.length} dòng · {stream.connection})</summary>
          <label className="check"><input type="checkbox" checked={warningsOnly} onChange={(e) => setWarningsOnly(e.target.checked)} />Chỉ hiện cảnh báo/lỗi</label>
          <ScanLog events={stream.events} connection={stream.connection} onlyWarnings={warningsOnly} />
          {running && stream.connection.startsWith("Mất") && <p className="muted"><Badge tone="medium">WebSocket gián đoạn</Badge> Trạng thái vẫn được cập nhật mỗi 3 giây qua REST.</p>}
        </details>
      )}
      {viewer && <ArtifactViewer scanId={id} title={viewer.title} files={viewer.files.filter((f) => (f.lines ?? 1) > 0)} onClose={() => setViewer(null)} />}
    </>
  );
}
