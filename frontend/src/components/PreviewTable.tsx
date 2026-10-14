import type { PreviewLine } from "../api/types";

const ICON = { ok: "✓", warn: "⚠", error: "✗", skip: "·" } as const;
const LABEL = { ok: "hợp lệ", warn: "cần lưu ý", error: "lỗi", skip: "bỏ qua" } as const;

export function PreviewTable({ lines }: { lines: PreviewLine[] }) {
  if (!lines.length) return null;
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Bảng dữ liệu, cuộn được">
      <table className="preview">
        <caption className="sr-only">Cách hệ thống hiểu từng dòng scope</caption>
        <thead>
          <tr>
            <th>Ô · dòng</th>
            <th>Trạng thái</th>
            <th>Hiểu là</th>
            <th>Ghi chú</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i} className={"line-" + l.status}>
              <td>
                {l.box.toUpperCase()} · {l.line}
              </td>
              <td>
                <span className={"mk mk-" + l.status} title={LABEL[l.status]}>
                  {ICON[l.status]}
                </span>
                <span className="sr-only">{LABEL[l.status]}</span>
              </td>
              <td>
                {l.status === "error" || l.status === "skip" ? (
                  <code>{l.raw.trim().slice(0, 80)}</code>
                ) : (
                  <>
                    <span className={"badge " + l.kind}>{l.kind.toUpperCase()}</span>
                    <span className="badge">{l.category}</span>{" "}
                    {l.shadowed_by ? <s title={"Bị OUT loại: " + l.shadowed_by}><code>{l.normalized}</code></s> : <code>{l.normalized}</code>}
                    {l.shadowed_by && <span className="badge out">bị OUT loại</span>}
                  </>
                )}
              </td>
              <td>{l.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
