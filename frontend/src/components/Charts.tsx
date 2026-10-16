import type { ChartsData } from "../api/types";

const fmt = (n: number | null | undefined) => (n === null || n === undefined ? "—" : n.toLocaleString("vi-VN"));
const CLASS_LABEL: Record<string, string> = { "2xx": "2xx thành công", "3xx": "3xx chuyển hướng", "4xx": "4xx bị từ chối / không có", "5xx": "5xx lỗi máy chủ", none: "Chưa probe HTTP" };

/** Horizontal bars. The number is always printed, so the bar only helps compare; it is never the sole carrier of the value. */
export function Bars({ items, label }: { items: { key: string; label: string; value: number; note?: string }[]; label: string }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="bars" aria-label={label}>
      {items.map((i) => (
        <li key={i.key}>
          <span className="bar-label" title={i.label}>{i.label}</span>
          <span className="bar-track" aria-hidden="true"><span className="bar-fill" style={{ width: `${Math.max(2, (i.value / max) * 100)}%` }} /></span>
          <span className="bar-value">{fmt(i.value)}{i.note && <small> {i.note}</small>}</span>
        </li>
      ))}
    </ul>
  );
}

const W = 160, H = 44, PAD = 4;

function Spark({ title, values }: { title: string; values: (number | null)[] }) {
  const nums = values.filter((v): v is number => v !== null);
  const last = nums[nums.length - 1];
  const prev = nums[nums.length - 2];
  const lo = Math.min(...nums), hi = Math.max(...nums);
  const x = (i: number) => PAD + (values.length === 1 ? (W - 2 * PAD) / 2 : (i * (W - 2 * PAD)) / (values.length - 1));
  const y = (v: number) => (hi === lo ? H / 2 : H - PAD - ((v - lo) / (hi - lo)) * (H - 2 * PAD));
  const points = values.map((v, i) => (v === null ? null : [x(i), y(v)] as const)).filter((p): p is readonly [number, number] => p !== null);
  const delta = last !== undefined && prev !== undefined ? last - prev : null;
  return (
    <div className="spark" data-metric={title}>
      <span className="spark-title">{title}</span>
      <strong>{fmt(last)}</strong>
      {delta !== null && <small className="spark-delta">{delta > 0 ? "▲ +" : delta < 0 ? "▼ " : "= "}{delta === 0 ? "không đổi" : fmt(delta)} so với scan trước</small>}
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title} qua ${values.length} scan: ${values.map(fmt).join(", ")}`}>
        <polyline points={points.map((p) => p.join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        {points.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={i === points.length - 1 ? 3.5 : 2} fill="currentColor" />)}
      </svg>
    </div>
  );
}

/** New / changed / gone per scan as stacked columns. Three fill patterns, not three colours alone. */
function ChangeColumns({ trend }: { trend: ChartsData["trend"] }) {
  const max = Math.max(1, ...trend.map((t) => t.new + t.changed + t.gone));
  const colW = Math.max(10, Math.min(28, 520 / trend.length)), height = 70, width = colW * trend.length + 8;
  return (
    <svg className="changecols" viewBox={`0 0 ${width} ${height + 14}`} role="img"
      aria-label={"Thay đổi mỗi scan (mới/đổi/mất): " + trend.map((t) => `#${t.id}: ${t.new}/${t.changed}/${t.gone}`).join("; ")}>
      <defs>
        <pattern id="pat-changed" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="var(--warn)" opacity=".25" /><line x1="0" y1="0" x2="0" y2="5" stroke="var(--warn)" strokeWidth="2.5" /></pattern>
        <pattern id="pat-gone" width="5" height="5" patternUnits="userSpaceOnUse"><rect width="5" height="5" fill="var(--bad)" opacity=".2" /><circle cx="2.5" cy="2.5" r="1.3" fill="var(--bad)" /></pattern>
      </defs>
      {trend.map((t, i) => {
        let top = height;
        const bar = (n: number, fill: string, key: string) => {
          const h = (n / max) * height;
          top -= h;
          return n > 0 ? <rect key={key} x={4 + i * colW + 1} y={top} width={colW - 3} height={h} fill={fill} stroke="var(--border)" strokeWidth=".5" /> : null;
        };
        return <g key={t.id}>{bar(t.new, "var(--accent)", "n")}{bar(t.changed, "url(#pat-changed)", "c")}{bar(t.gone, "url(#pat-gone)", "g")}
          <text x={4 + i * colW + colW / 2} y={height + 11} fontSize="8" textAnchor="middle" fill="var(--muted)">#{t.id}</text></g>;
      })}
    </svg>
  );
}

export function TrendChart({ trend, truncated }: { trend: ChartsData["trend"]; truncated: boolean }) {
  if (trend.length < 2) {
    return <p className="muted" data-testid="trend-empty">Xu hướng cần ít nhất hai scan hoàn tất. Hiện có {trend.length}.</p>;
  }
  return (
    <div data-testid="trend">
      <div className="sparks">
        <Spark title="Host (live)" values={trend.map((t) => t.live)} />
        <Spark title="URL" values={trend.map((t) => t.urls)} />
        <Spark title="Finding" values={trend.map((t) => t.findings)} />
      </div>
      <h3 className="subhead">Thay đổi sau mỗi scan</h3>
      <ChangeColumns trend={trend} />
      <p className="legend" aria-hidden="true"><span className="sw sw-new" /> mới <span className="sw sw-changed" /> đổi <span className="sw sw-gone" /> mất</p>
      {truncated && <p className="muted">Chỉ hiện 30 scan hoàn tất gần nhất.</p>}
      <details>
        <summary>Xem dạng bảng</summary>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Xu hướng theo scan, cuộn được">
          <table>
            <thead><tr><th>Scan</th><th>Mức</th><th>Host live</th><th>URL</th><th>Finding</th><th>Mới</th><th>Đổi</th><th>Mất</th></tr></thead>
            <tbody>{[...trend].reverse().map((t) => (
              <tr key={t.id}><td><a href={"#/scan/" + t.id}>#{t.id}</a>{t.status === "done_partial" ? " (một phần)" : ""}</td><td>{t.depth}</td><td>{fmt(t.live)}</td><td>{fmt(t.urls)}</td><td>{fmt(t.findings)}</td><td>{t.new}</td><td>{t.changed}</td><td>{t.gone}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

export function Distributions({ data }: { data: ChartsData }) {
  const classes = Object.entries(data.status.classes).sort((a, b) => b[1] - a[1]);
  return (
    <div className="dists" data-testid="distributions">
      <section>
        <h3 className="subhead">Mã trạng thái ({fmt(data.status.total)} host)</h3>
        {classes.length === 0 ? <p className="muted">Chưa có host.</p> : <Bars label="Phân bố mã trạng thái" items={classes.map(([k, v]) => ({ key: k, label: CLASS_LABEL[k] || k, value: v }))} />}
        {data.status.codes.length > 0 && <p className="muted">Phổ biến: {data.status.codes.map((c) => `${c.code} (${fmt(c.count)})`).join(", ")}</p>}
      </section>
      <section>
        <h3 className="subhead">Công nghệ</h3>
        {data.tech.length === 0 ? <p className="muted">Chưa nhận diện được công nghệ nào.</p> : <Bars label="Công nghệ phổ biến" items={data.tech.map((t) => ({ key: t.name, label: t.name, value: t.count }))} />}
      </section>
      <section>
        <h3 className="subhead">Host có nhiều URL nhất</h3>
        {data.hosts_by_urls.length === 0 ? <p className="muted">Chưa có URL gắn với host.</p>
          : <Bars label="Host theo số URL" items={data.hosts_by_urls.map((h) => ({ key: h.host, label: h.host, value: h.urls, note: `· điểm cao nhất ${h.top_score}` }))} />}
      </section>
    </div>
  );
}

/** Severity x host as a table: every cell prints its number, shading only echoes it. */
export function SeverityMatrix({ matrix }: { matrix: ChartsData["severity_matrix"] }) {
  if (matrix.hosts.length === 0) return <p className="muted">Chưa có finding để lập ma trận.</p>;
  const max = Math.max(1, ...matrix.hosts.flatMap((h) => matrix.severities.map((s) => Number(h[s]) || 0)));
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Ma trận mức nghiêm trọng theo host, cuộn được">
      <table className="matrix" data-testid="severity-matrix">
        <thead><tr><th>Host</th>{matrix.severities.map((s) => <th key={s}>{s}</th>)}</tr></thead>
        <tbody>{matrix.hosts.map((h) => (
          <tr key={h.host}><td>{h.host}</td>{matrix.severities.map((s) => {
            const n = Number(h[s]) || 0;
            return <td key={s} className={n ? "has" : "zero"} style={n ? { background: `color-mix(in srgb, var(--warn) ${Math.round(12 + (n / max) * 40)}%, transparent)` } : undefined}>{n || "·"}</td>;
          })}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}
