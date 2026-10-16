import { useState } from "react";
import { api } from "../api/client";
import type { DeletePreview } from "../api/types";
import { explain } from "../lib/errors";
import { when } from "../lib/format";
import { go } from "../lib/router";
import { ErrorBox } from "./ui";

const COUNT_LABEL: Record<string, string> = {
  scans: "lần scan", drafts: "bản nháp", asset: "asset", url: "URL", finding: "finding", diff_event: "thay đổi trong Diff",
};

/** Shown on an archived program: restore it, or delete it for good after reading exactly what goes and typing its name. */
export function ArchivedBanner({ slug, archivedAt, reload }: { slug: string; archivedAt: string; reload: () => void }) {
  const base = "/api/programs/" + encodeURIComponent(slug);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  async function restore() {
    setError("");
    try { await api(base + "/restore", { method: "POST" }); reload(); } catch (e) { setError(explain(e)); }
  }
  async function openDelete() {
    setError("");
    try { setPreview(await api<DeletePreview>(base + "/delete-preview")); setTyped(""); } catch (e) { setError(explain(e)); }
  }
  async function remove() {
    setBusy(true); setError("");
    try {
      await api(base, { method: "DELETE", body: JSON.stringify({ confirm_slug: typed }) });
      go("/");
    } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }
  const counts = preview ? Object.entries(preview.counts).filter(([, n]) => n > 0) : [];
  return (
    <section className="warnbox archived-banner" role="status" data-testid="archived-banner">
      <p>
        <strong>Program đã lưu trữ</strong> ({when(archivedAt)}). Nó bị ẩn khỏi danh sách chính, lịch giám sát đã tạm dừng và không thể đổi cấu hình hay tạo scan mới. Lịch sử, Diff, finding và file vẫn còn nguyên.
      </p>
      <div className="actions">
        <button onClick={restore}>Khôi phục</button>
        {!preview && <button className="secondary danger" onClick={openDelete}>Xóa vĩnh viễn…</button>}
      </div>
      <ErrorBox text={error} />
      {preview && (
        <div className="delete-panel" data-testid="delete-panel">
          <h3 className="subhead">Xóa vĩnh viễn “{slug}”</h3>
          <p>Việc này <strong>không hoàn tác được</strong>. Sẽ xóa:</p>
          <ul className="plain">
            {counts.map(([key, n]) => <li key={key}>{n.toLocaleString("vi-VN")} {COUNT_LABEL[key] || key}</li>)}
            <li>Thư mục <code>{preview.folder.path}</code> ({preview.folder.files.toLocaleString("vi-VN")} file, {(preview.folder.bytes / 1024).toFixed(0)} KB)</li>
            {preview.has_schedule && <li>Lịch giám sát</li>}
          </ul>
          <p className="muted">Nhật ký kiểm toán (audit) được giữ lại một bản trong <code>data/audit-archive</code>.</p>
          {preview.blockers.length > 0 && <p className="warnbox" role="alert">{preview.blockers.join(" ")}</p>}
          <label>Gõ <code>{slug}</code> để xác nhận
            <input aria-label="Gõ tên program để xác nhận xóa" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
          </label>
          <div className="actions">
            <button className="danger" disabled={busy || typed !== slug || preview.blockers.length > 0} onClick={remove}>Xóa vĩnh viễn</button>
            <button className="secondary" onClick={() => setPreview(null)}>Hủy</button>
          </div>
        </div>
      )}
    </section>
  );
}
