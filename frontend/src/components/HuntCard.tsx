import { CopyButton } from "./ui";

export function HuntCard({ command, note = "", title = "Sẵn sàng hunt" }: { command: string; note?: string; title?: string }) {
  return (
    <section className="card hunt" aria-labelledby="hunt-h">
      <h2 id="hunt-h">{title}</h2>
      <p>Mở terminal trên máy bạn và chạy lệnh dưới đây; agent sẽ đọc <code>CLAUDE.md</code> → <code>PROGRAM.md</code> → <code>AGENT_BRIEF.md</code>.</p>
      <div className="command">
        <code>{command}</code>
        <CopyButton text={command} label="Sao chép lệnh" />
      </div>
      {note && <small>{note}</small>}
    </section>
  );
}
