export const PHASES: [string, string][] = [
  ["subdomain_enum", "Tìm subdomain"],
  ["live_probe", "Probe HTTP"],
  ["port_scan", "Quét cổng"],
  ["url_collect", "Thu thập URL"],
  ["js_analysis", "Phân tích JS"],
  ["dir_fuzz", "Fuzz thư mục"],
  ["config_expose", "File cấu hình lộ"],
  ["param_discover", "Tham số ẩn"],
  ["cicd_scan", "CI/CD"],
  ["nuclei", "Nuclei"],
  ["takeover", "Takeover"],
];

export function phaseState(events: any[], finished: boolean) {
  const seen = new Set<string>();
  let current = "";
  for (const event of events) {
    if (event.type === "phase" && event.phase) {
      seen.add(event.phase);
      current = event.phase;
    }
  }
  const index = PHASES.findIndex(([key]) => key === current);
  return PHASES.map(([key, label], i) => ({
    key,
    label,
    state: !seen.has(key) ? "pending" : finished || i < index ? "done" : "current",
  }));
}
