import type { ScanProgressData, StageRecord } from "../api/types";
import { Chip } from "./layout";

const STAGE_TONE: Record<string, string> = { ok: "good", running: "warn", error: "warn", timeout: "bad", skipped_budget: "bad", empty: "muted" };
const STAGE_LABEL: Record<string, string> = {
  ok: "xong", running: "đang chạy", error: "có lệnh lỗi", timeout: "hết thời gian", skipped_budget: "không chạy (hết ngân sách)", empty: "không có việc",
};
const SOURCE_LABEL: Record<string, string> = { timeout: "quá thời gian", error: "lỗi", ok: "ổn" };

/** Time used against the budget of each stage, on one scale. Overruns are hatched and spelled out, not only coloured. */
function StageTimeline({ stages }: { stages: StageRecord[] }) {
  const rows = stages.filter((st) => st.budget_s > 0 || st.used_s > 0);
  if (rows.length === 0) return null;
  const scale = Math.max(1, ...rows.map((st) => Math.max(st.budget_s, st.used_s)));
  return (
    <ul className="timeline" aria-label="Thời gian đã dùng so với ngân sách của từng giai đoạn" data-testid="stage-timeline">
      {rows.map((st) => {
        const over = st.budget_s > 0 && st.used_s >= st.budget_s;
        return (
          <li key={st.key}>
            <span title={st.label}>{st.label}</span>
            <span className="tl-track" aria-hidden="true" style={{ width: `${Math.max(8, (st.budget_s || st.used_s) / scale * 100)}%` }}>
              <span className={"tl-used" + (over ? " over" : "")} style={{ width: `${Math.min(100, st.budget_s ? (st.used_s / st.budget_s) * 100 : 100)}%` }} />
            </span>
            <span>{st.used_s}s{st.budget_s ? ` / ${st.budget_s}s` : ""}{over ? " — dùng hết ngân sách" : ""}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** How far a scan really got: which stage ran how long, how many discovered hosts were probed, which sources failed. */
export function ScanProgress({ data, partial }: { data: ScanProgressData; partial?: boolean }) {
  const stages = data.stages || [];
  const coverage = data.coverage;
  const failedSources = (data.sources || []).filter((s) => s.status !== "ok");
  const pathRules = Object.entries(data.path_rule_hosts || {});
  const hasAnything = stages.length > 0 || !!coverage || failedSources.length > 0 || pathRules.length > 0 || (data.partial_inputs || []).length > 0;
  if (!hasAnything) return null;
  return (
    <div data-testid="scan-progress">
      {coverage && coverage.discovered > 0 && (
        <p className={coverage.unprobed > 0 ? "warnbox" : ""} aria-label="Phủ host khám phá">
          Host khám phá được: <strong>{coverage.discovered.toLocaleString("vi-VN")}</strong> · đã probe{" "}
          <strong>{coverage.probed.toLocaleString("vi-VN")}</strong> · chưa probe{" "}
          <strong>{coverage.unprobed.toLocaleString("vi-VN")}</strong>
          {coverage.unprobed > 0 && (
            <> — scan chưa đầy đủ. Host chưa probe <strong>không</strong> bị coi là đã biến mất khỏi diff.</>
          )}
        </p>
      )}
      {stages.length > 0 && <StageTimeline stages={stages} />}
      {stages.length > 0 && (
        <table className="stages">
          <caption className="sr-only">Các giai đoạn của scan</caption>
          <thead><tr><th>Giai đoạn</th><th>Trạng thái</th><th>Thời gian</th><th>Lệnh</th></tr></thead>
          <tbody>
            {stages.map((st) => (
              <tr key={st.key} data-stage={st.key}>
                <td>{st.label}</td>
                <td><Chip tone={STAGE_TONE[st.status]}>{STAGE_LABEL[st.status] || st.status}</Chip></td>
                <td>{st.budget_s ? `${st.used_s}s / ${st.budget_s}s` : st.used_s ? `${st.used_s}s` : "—"}</td>
                <td>{st.commands}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {failedSources.length > 0 && (
        <p className="warnbox">
          Nguồn thụ động không trọn vẹn:{" "}
          {failedSources.map((s, i) => <span key={i}>{i > 0 && ", "}<strong>{s.source}</strong> {SOURCE_LABEL[s.status]} sau {s.seconds}s</span>)}
          . Kết quả nguồn đó dừng ở chỗ đã có; các nguồn khác vẫn được dùng.
        </p>
      )}
      {(data.partial_inputs || []).length > 0 && (
        <p className="muted">
          {data.partial_inputs!.reduce((n, p) => n + p.in_scope, 0)} host được nhập từ các file nguồn dở dang (bước gộp chưa kịp chạy); tất cả đã qua scope gate.
        </p>
      )}
      {(data.tool_notes || []).map((n, i) => (
        <p className="muted" key={i} data-testid="tool-note"><strong>{n.tool}</strong>: {n.note}</p>
      ))}
      {pathRules.length > 0 && (
        <p className="muted" data-testid="path-rules">
          OUT theo đường dẫn: {pathRules.map(([h, paths]) => `${h} (${paths.length})`).join(", ")} — các host này chỉ được probe, trừ khi bạn bật quét chủ động cho chúng.
        </p>
      )}
      {partial && stages.length === 0 && <p className="muted">Scan này chạy trước khi dashboard ghi lại các giai đoạn.</p>}
    </div>
  );
}
