import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { Health } from "../api/types";
import { ErrorBox } from "../components/ui";
import { PreviewTable } from "../components/PreviewTable";
import { useData } from "../hooks/useData";
import { usePreview } from "../hooks/usePreview";
import { explain } from "../lib/errors";
import { go } from "../lib/router";

const EXAMPLE_IN = "*.example.com\napi.example.com\n203.0.113.0/24\nrepo:https://github.com/example/webapp";
const EXAMPLE_OUT = "admin.example.com";
const lines = (text: string) => text.split("\n");

export function NewScan() {
  const [mode, setMode] = useState<"h1" | "raw">("h1");
  const [h1, setH1] = useState("");
  const [scopeIn, setScopeIn] = useState("");
  const [scopeOut, setScopeOut] = useState("");
  const [name, setName] = useState("");
  const [policy, setPolicy] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const health = useData<Health>("/api/health");

  const body = useMemo(() => {
    if (mode === "h1") return h1.trim() ? { input: h1.trim() } : null;
    return scopeIn.trim() || scopeOut.trim()
      ? { input: "raw", scope: lines(scopeIn), scope_out: lines(scopeOut) }
      : null;
  }, [mode, h1, scopeIn, scopeOut]);
  const { preview, pending, error: previewError } = usePreview(body);

  const ready = !!body && !!preview?.ok && !pending && !busy && !previewError;
  const reason = busy
    ? "Đang resolve…"
    : !body
      ? mode === "h1"
        ? "Nhập handle hoặc URL chương trình HackerOne."
        : "Nhập ít nhất một asset vào ô scope."
      : pending
        ? "Đang kiểm tra…"
        : previewError || preview?.message || "";

  async function resolve(e: React.FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError("");
    try {
      const request =
        mode === "h1"
          ? { input: h1.trim(), policy_text: policy }
          : { input: "raw", scope: lines(scopeIn), scope_out: lines(scopeOut), name: name.trim(), policy_text: policy };
      const result = await api("/api/scope/resolve", { method: "POST", body: JSON.stringify(request) });
      go("/scan/" + result.scan_id + "/review");
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(false);
    }
  }

  async function loadFile(file?: File) {
    if (!file) return;
    if (file.size > 1_000_000) return setError("File quá lớn (tối đa 1 MB).");
    const text = await file.text();
    setScopeIn((current) => (current ? current.replace(/\n?$/, "\n") : "") + text);
  }

  return (
    <>
      <p className="eyebrow">BƯỚC 1/3 · NHẬP SCOPE</p>
      <h1>Thêm program</h1>
      <p className="lead">
        Nhập nguồn scope. Chưa có gì được quét: bạn sẽ xem lại policy, scope và cấu hình ở bước kế tiếp.
      </p>
      <form className="card form wide" onSubmit={resolve}>
        <div role="tablist" aria-label="Nguồn scope" className="seg">
          {(["h1", "raw"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              className={mode === m ? "active" : "secondary"}
              onClick={() => setMode(m)}
            >
              {m === "h1" ? "HackerOne" : "Raw scope"}
            </button>
          ))}
        </div>

        {mode === "h1" ? (
          <>
            <label>
              HackerOne handle hoặc URL
              <input
                value={h1}
                onChange={(e) => setH1(e.target.value)}
                placeholder="h1:acme · acme · https://hackerone.com/acme"
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            {preview?.mode === "h1" && preview.ok && (
              <p className="okline">
                Nhận diện: program <code>{preview.handle}</code> ✓
              </p>
            )}
            <p className="muted">
              {health.data?.h1_api
                ? "Dùng API HackerOne (đã cấu hình H1_USER/H1_TOKEN): scope có phân loại và policy đầy đủ."
                : "Chưa cấu hình H1_USER/H1_TOKEN nên dùng dữ liệu công khai: có thể đã cũ và thường không có policy đầy đủ. Hãy đọc policy chính thức trên HackerOne và dán vào ô bên dưới."}
            </p>
          </>
        ) : (
          <>
            <div className="two">
              <label>
                Scope — mỗi dòng một asset (IN)
                <textarea
                  rows={9}
                  value={scopeIn}
                  onChange={(e) => setScopeIn(e.target.value)}
                  placeholder={EXAMPLE_IN}
                  spellCheck={false}
                />
              </label>
              <label>
                Loại trừ (OUT) — mỗi dòng một asset
                <textarea
                  rows={9}
                  value={scopeOut}
                  onChange={(e) => setScopeOut(e.target.value)}
                  placeholder={EXAMPLE_OUT}
                  spellCheck={false}
                />
              </label>
            </div>
            <div className="row">
              <button
                type="button"
                className="secondary small"
                onClick={() => {
                  setScopeIn(EXAMPLE_IN);
                  setScopeOut(EXAMPLE_OUT);
                }}
              >
                Điền ví dụ
              </button>
              <label className="filebtn secondary small">
                Tải file .txt vào ô IN
                <input type="file" accept=".txt,.csv,text/plain" onChange={(e) => loadFile(e.target.files?.[0])} />
              </label>
            </div>
            <p className="muted">
              Chấp nhận domain, <code>*.domain</code>, IP, CIDR, dải IP (<code>10.0.0.1-10.0.0.20</code>),{" "}
              <code>repo:https://github.com/org/repo</code> và <code>app:com.id</code>. Phân tách bằng xuống dòng,
              dấu phẩy hoặc khoảng trắng. Dòng bắt đầu bằng <code>#</code> là ghi chú.
            </p>
            <label>
              Tên program (tuỳ chọn)
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="vd: acme-internal" />
            </label>
            {preview?.mode === "raw" && (
              <p className="okline" aria-live="polite">
                {preview.summary.in} IN · {preview.summary.out} OUT
                {preview.summary.errors ? ` · ${preview.summary.errors} lỗi` : ""}
                {preview.summary.warnings ? ` · ${preview.summary.warnings} cần lưu ý` : ""}
              </p>
            )}
            <PreviewTable lines={(preview?.lines || []).filter((l) => l.status !== "skip" || l.note !== "Ghi chú, bỏ qua")} />
          </>
        )}

        <details>
          <summary>Policy / hướng dẫn của program (tuỳ chọn)</summary>
          <label>
            Dán nội dung policy hoặc quy định riêng — sẽ được ghi vào PROGRAM.md cho agent
            <textarea rows={6} value={policy} onChange={(e) => setPolicy(e.target.value)} />
          </label>
        </details>

        <ErrorBox text={error} />
        <div className="actions">
          <button disabled={!ready}>{busy ? "Đang resolve…" : "Resolve & review"}</button>
          {!ready && reason && <span className="muted" role="status">{reason}</span>}
        </div>
      </form>
    </>
  );
}
