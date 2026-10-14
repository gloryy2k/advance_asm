import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ReviewData, ScanRow } from "../api/types";
import { HuntCard } from "../components/HuntCard";
import { ScanLog } from "../components/ScanLog";
import { Stepper } from "../components/Stepper";
import { Badge, ErrorBox, StatusBadge } from "../components/ui";
import { useData } from "../hooks/useData";
import { useScanStream } from "../hooks/useScanStream";
import { explain } from "../lib/errors";
import { TERMINAL, durationLabel } from "../lib/format";
import { go, programPath } from "../lib/router";

function Elapsed({ since, running }: { since?: string | null; running: boolean }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  if (!since) return null;
  const seconds = Math.max(0, (now - new Date(since).getTime()) / 1000);
  return <span className="muted">Đã chạy {durationLabel(seconds)}</span>;
}

export function Run({ id }: { id: string }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const state = useData<ScanRow>("/api/scans/" + id, revision, 3000);
  const status = state.data?.status;
  const finished = TERMINAL.has(status || "");
  const info = useData<ReviewData>("/api/scans/" + id + "/review", finished ? 1 : 0);
  const stream = useScanStream(id, finished, () => setRevision((v) => v + 1));
  const [warningsOnly, setWarningsOnly] = useState(false);

  async function cancel() {
    try {
      await api("/api/scans/" + id + "/cancel", { method: "POST" });
      setConfirming(false);
      setRevision((v) => v + 1);
    } catch (e) {
      setError(explain(e));
    }
  }
  async function again() {
    if (!info.data) return;
    try {
      const made = await api("/api/programs/" + encodeURIComponent(info.data.slug) + "/rescan", { method: "POST" });
      go("/scan/" + made.scan_id + "/review");
    } catch (e) {
      setError(explain(e));
    }
  }
  const slug = info.data?.slug;
  const good = status === "done" || status === "done_partial";
  return (
    <>
      <p className="eyebrow">BƯỚC 3/3 · ĐANG QUÉT</p>
      <h1>
        Scan #{id} {slug && <small className="inline">· {slug}</small>}
      </h1>
      <ErrorBox text={error || state.error} />
      <div className="statusrow">
        <span role="status" aria-label="Scan status">
          <StatusBadge status={status} />
        </span>
        {status === "draft" && <a href={"#/scan/" + id + "/review"}>Quay lại Review →</a>}
        <Elapsed since={state.data?.started_at} running={status === "running"} />
        {!finished && status !== "draft" && (
          confirming ? (
            <>
              <button className="danger" onClick={cancel}>Xác nhận huỷ scan</button>
              <button className="secondary" onClick={() => setConfirming(false)}>Giữ lại</button>
            </>
          ) : (
            <button className="secondary" disabled={!status} onClick={() => setConfirming(true)}>Cancel scan</button>
          )
        )}
        {slug && <a href={"#" + programPath(slug)}>Mở program →</a>}
      </div>

      {status === "done_partial" && (
        <p className="warnbox">Scan hoàn tất một phần: một số bước lỗi/bị bỏ qua. Dữ liệu có được vẫn đã nạp; không suy ra host vắng là đã biến mất.</p>
      )}
      {(status === "failed" || status === "cancelled") && (
        <section className="card">
          <h2>{status === "failed" ? "Scan lỗi" : "Scan đã huỷ"}</h2>
          {state.data?.error && <p className="error">{state.data.error}</p>}
          <p>Tạo bản nháp mới với cùng scope để chỉnh và chạy lại.</p>
          <button onClick={again}>Tạo scan mới (cùng scope)</button>
        </section>
      )}
      {good && info.data && (
        <>
          <HuntCard command={info.data.hunt_command} note={info.data.hunt_note} title="Hoàn tất → bắt đầu hunt" />
          <p>
            <a className="button" href={"#" + programPath(info.data.slug, "brief")}>Xem Brief</a>{" "}
            <a className="button secondary" href={"#" + programPath(info.data.slug)}>Tổng quan program</a>
          </p>
        </>
      )}

      {status !== "draft" && (
        <>
          <section className="card">
            <h2>Tiến độ</h2>
            <Stepper events={stream.events} finished={finished} />
          </section>
          <label className="check"><input type="checkbox" checked={warningsOnly} onChange={(e) => setWarningsOnly(e.target.checked)} />Chỉ hiện cảnh báo/lỗi</label>
          <ScanLog events={stream.events} connection={stream.connection} onlyWarnings={warningsOnly} />
          {!finished && stream.connection.startsWith("Mất") && (
            <p className="muted"><Badge tone="medium">WebSocket gián đoạn</Badge> Trạng thái vẫn được cập nhật mỗi 3 giây qua REST.</p>
          )}
        </>
      )}
    </>
  );
}
