export function ScanLog({ events, connection, onlyWarnings }: { events: any[]; connection: string; onlyWarnings?: boolean }) {
  const shown = onlyWarnings
    ? events.filter((e) => e.level === "warning" || /\[!\]|error|fail/i.test(e.message || ""))
    : events;
  return (
    <section className="card">
      <div className="split">
        <h2>Nhật ký scan</h2>
        <span className="badge">{connection}</span>
      </div>
      <div className="logs" role="log" tabIndex={0}>
        {shown.length === 0
          ? "Đang chờ log…"
          : shown.map((e, i) => (
              <div key={i}>
                <span>{e.type}</span> {e.message || e.phase || e.status || JSON.stringify(e)}
              </div>
            ))}
      </div>
    </section>
  );
}
