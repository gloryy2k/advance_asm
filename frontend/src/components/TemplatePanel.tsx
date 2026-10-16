import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { TemplateInfo } from "../api/types";
import { explain } from "../lib/errors";
import { when } from "../lib/format";
import { Panel } from "./layout";
import { Badge, ErrorBox } from "./ui";

/** Nuclei templates: what is installed, the update job, and the user's own templates. */
export function TemplatePanel({ info, nucleiReady, onChanged }: { info?: TemplateInfo; nucleiReady: boolean; onChanged: () => void }) {
  const [live, setLive] = useState<TemplateInfo | null>(null);
  const [error, setError] = useState("");
  const [yaml, setYaml] = useState("");
  const [busy, setBusy] = useState(false);
  const shown = live || info;
  const running = shown?.job?.state === "running";

  // While an update runs, ask again every 2 s; stop as soon as it is over.
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => api<TemplateInfo>("/api/tools/templates").then((r) => { setLive(r); if (r.job?.state !== "running") onChanged(); }).catch(() => undefined), 2000);
    return () => clearInterval(timer);
  }, [running, onChanged]);

  async function update() {
    setError(""); setBusy(true);
    try {
      await api("/api/tools/templates/update", { method: "POST" });
      setLive(await api<TemplateInfo>("/api/tools/templates"));
    } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }
  async function add() {
    setError(""); setBusy(true);
    try {
      await api("/api/tools/templates/custom", { method: "POST", body: JSON.stringify({ content: yaml }) });
      setYaml(""); setLive(await api<TemplateInfo>("/api/tools/templates")); onChanged();
    } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }
  async function remove(id: string) {
    if (!confirm(`Xoá template riêng "${id}"? Bộ template chính thức không bị ảnh hưởng.`)) return;
    try { await api("/api/tools/templates/custom/" + encodeURIComponent(id), { method: "DELETE" }); setLive(await api<TemplateInfo>("/api/tools/templates")); onChanged(); } catch (e) { setError(explain(e)); }
  }
  async function pick(file: File | undefined) {
    if (!file) return;
    if (file.size > 256 * 1024) { setError("Template quá lớn (tối đa 256 KB)."); return; }
    setYaml(await file.text());
  }
  const job = shown?.job;
  return (
    <Panel id="templates-h" title="Nuclei templates"
      hint="Bộ mẫu kiểm tra của nuclei. Scan không bao giờ tự tải; bạn cài/cập nhật ở đây. Tải vào thư mục tạm, chỉ thay bộ đang dùng khi tải đủ; lỗi thì giữ bộ cũ."
      actions={<button onClick={update} disabled={running || busy || !nucleiReady} title={nucleiReady ? "" : "Cần nuclei trước"}>
        {running ? "Đang tải…" : shown?.installed ? "Cập nhật templates" : "Cài templates"}</button>}>
      <ErrorBox text={error} />
      <p data-testid="template-status">
        {shown?.installed
          ? <><Badge tone="done">Đã cài</Badge> {shown.count ? <strong>{shown.count.toLocaleString("vi-VN")} template</strong> : "bộ có sẵn trên máy"}
              {shown.version && <> · phiên bản {shown.version}</>}{shown.updated_at && <> · cập nhật {when(shown.updated_at)}</>}{shown.source && <> · nguồn {shown.source}</>}</>
          : <><Badge tone="failed">Chưa cài</Badge> Light/Strong sẽ bỏ qua bước Nuclei cho tới khi có bộ template.</>}
      </p>
      {job && (
        <p className={job.state === "failed" ? "warnbox" : "muted"} role="status" data-testid="template-job">
          {job.state === "running" ? "Đang cập nhật…" : job.state === "ok" ? "Lần cập nhật gần nhất thành công: " : "Lần cập nhật gần nhất thất bại: "}{job.message}
          {job.finished_at && <> ({when(job.finished_at)})</>}
        </p>
      )}
      <details className="adv">
        <summary>Template riêng ({shown?.custom?.length ?? 0})</summary>
        <p className="muted">Mỗi template là một file YAML của bạn (http/dns/ssl/tcp). BBASM từ chối template có <code>code</code>, <code>javascript</code>, <code>headless</code>, <code>file</code> hoặc
          URL cố định ngoài <code>{"{{BaseURL}}"}</code>, rồi kiểm bằng <code>nuclei -validate</code>. Template riêng <strong>chạy thêm</strong> bộ chính thức và chỉ khi bạn chọn nó ở Review cho từng scan.</p>
        {shown?.custom?.length ? (
          <ul className="profiles">
            {shown.custom.map((t) => (
              <li key={t.id}><div><strong>{t.name}</strong> <code>{t.id}</code><small>{t.bytes} byte · thêm {when(t.added_at)}</small></div>
                <button className="secondary small" onClick={() => remove(t.id)}>Xoá</button></li>
            ))}
          </ul>
        ) : null}
        <label>Dán YAML hoặc chọn file
          <textarea rows={6} aria-label="YAML template" value={yaml} spellCheck={false} onChange={(e) => setYaml(e.target.value)} placeholder={"id: my-check\ninfo: {name: ..., author: ..., severity: low}\nhttp:\n  - method: GET\n    path: [\"{{BaseURL}}/status\"]"} />
        </label>
        <div className="actions">
          <input type="file" accept=".yaml,.yml" aria-label="Chọn file template" onChange={(e) => pick(e.target.files?.[0])} />
          <button onClick={add} disabled={busy || yaml.trim().length < 10}>Thêm template</button>
        </div>
      </details>
    </Panel>
  );
}
