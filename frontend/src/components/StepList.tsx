import type { ReactNode } from "react";
import { Chip } from "./layout";

export type StepRow = {
  key: string;
  title: string;
  what: string;
  touches: boolean;
  status: string;           // plan: on|off|missing_tool · report: ran|empty|skipped|missing_tool|no_output|pending
  statusLabel: string;
  reason?: string | null;
  count?: number;
  countLabel?: string;
  outputLabel?: string;
};

const TONE: Record<string, string> = {
  on: "good", ran: "good", off: "muted", skipped: "muted", empty: "warn", missing_tool: "bad", no_output: "muted", timeout: "warn", pending: "muted",
};

/** One row per function: what it does, whether it runs/ran, how much it found, where to read it. */
export function StepList({
  rows,
  toggle,
  action,
}: {
  rows: StepRow[];
  toggle?: (row: StepRow) => ReactNode;
  action?: (row: StepRow) => ReactNode;
}) {
  return (
    <ul className="steps">
      {rows.map((r) => (
        <li key={r.key} className={"step " + r.status} data-step={r.key}>
          <div className="step-main">
            {toggle && <div className="step-toggle">{toggle(r)}</div>}
            <div>
              <div className="step-title">
                <strong>{r.title}</strong>
                <Chip tone={r.touches ? "touch" : "quiet"} title={r.touches ? "Gửi request tới target" : "Không gửi request tới target"}>
                  {r.touches ? "chạm target" : "không chạm target"}
                </Chip>
              </div>
              <p className="step-what">{r.what}</p>
              {r.reason && <p className={"step-reason " + (TONE[r.status] || "")}>{r.reason}</p>}
              {r.outputLabel && <p className="output-note">📍 Kết quả: {r.outputLabel}</p>}
            </div>
          </div>
          <div className="step-side">
            <Chip tone={TONE[r.status]}>{r.statusLabel}</Chip>
            {r.count !== undefined && r.count > 0 && (
              <span className="step-count">
                <strong>{r.count.toLocaleString("vi-VN")}</strong> {r.countLabel}
              </span>
            )}
            {action?.(r)}
          </div>
        </li>
      ))}
    </ul>
  );
}
