const TAG: Record<string, [string, string]> = {
  skipped_config: ["bỏ qua theo mức quét", "muted"], missing_tool: ["thiếu công cụ", "bad"], timeout: ["quá thời gian", "warn"],
  no_input: ["không có dữ liệu đầu vào", "muted"], not_needed: ["không dùng ở cấu hình này", "muted"],
};

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
              <div key={i} className={e.type === "stage" ? "log-stage" : undefined}>
                <span>{e.type}</span> {e.tag && TAG[e.tag] && <span className={"chip " + TAG[e.tag][1]}>{TAG[e.tag][0]}</span>}{" "}
                {e.message || e.phase || e.status || JSON.stringify(e)}
              </div>
            ))}
      </div>
    </section>
  );
}
