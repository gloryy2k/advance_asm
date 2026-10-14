import { phaseState } from "../lib/phases";

export function Stepper({ events, finished }: { events: any[]; finished: boolean }) {
  const phases = phaseState(events, finished);
  return (
    <ol className="stepper" aria-label="Tiến độ recon">
      {phases.map((p) => (
        <li key={p.key} className={p.state} aria-current={p.state === "current" ? "step" : undefined}>
          <span className="dot" aria-hidden="true">
            {p.state === "done" ? "✓" : p.state === "current" ? "●" : "○"}
          </span>
          {p.label}
        </li>
      ))}
    </ol>
  );
}
