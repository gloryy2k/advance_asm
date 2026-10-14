import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { PhaseFile } from "../api/types";
import { explain } from "../lib/errors";
import { Pager, ErrorBox } from "./ui";

type Page = { total: number; lines: string[]; redacted: boolean };

/** Read-only window onto a recon output file: paged, searchable, secrets hidden unless asked. */
export function ArtifactViewer({
  scanId,
  title,
  files,
  onClose,
}: {
  scanId: number | string;
  title: string;
  files: PhaseFile[];
  onClose: () => void;
}) {
  const [path, setPath] = useState(files[0]?.path || "");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [offset, setOffset] = useState(0);
  const [reveal, setReveal] = useState(false);
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);
  const limit = 100;

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  useEffect(() => {
    const t = setTimeout(() => {
      setTerm(q);
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    if (!path) return;
    let live = true;
    setError("");
    const query = new URLSearchParams({ path, offset: String(offset), limit: String(limit), q: term, reveal: String(reveal) });
    api<Page>(`/api/scans/${scanId}/artifact?${query}`)
      .then((r) => live && setPage(r))
      .catch((e) => live && setError(explain(e)));
    return () => {
      live = false;
    };
  }, [scanId, path, offset, term, reveal]);

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={"Kết quả: " + title}>
        <div className="dialog-head">
          <h2>{title}</h2>
          <button ref={closeRef} className="secondary small" onClick={onClose} aria-label="Đóng">
            ✕ Đóng
          </button>
        </div>
        {files.length > 1 && (
          <div className="filebar" role="tablist" aria-label="File kết quả">
            {files.map((f) => (
              <button
                key={f.path}
                role="tab"
                aria-selected={f.path === path}
                className={f.path === path ? "on" : ""}
                onClick={() => {
                  setPath(f.path);
                  setOffset(0);
                  setPage(null);
                }}
              >
                {f.label} <small className="inline">{f.lines ?? "?"} dòng</small>
              </button>
            ))}
          </div>
        )}
        <div className="filters">
          <input aria-label="Tìm trong file" placeholder="Tìm trong file…" value={q} onChange={(e) => setQ(e.target.value)} />
          <a className="button secondary small" href={`/api/scans/${scanId}/artifact/download?path=${encodeURIComponent(path)}${reveal ? "&reveal=true" : ""}`}>
            Tải file ↓
          </a>
        </div>
        {page?.redacted && (
          <p className="warnbox">
            Giá trị bí mật đang bị ẩn.{" "}
            <label className="check inline">
              <input type="checkbox" checked={reveal} onChange={(e) => setReveal(e.target.checked)} />
              Hiện giá trị (chỉ khi bạn cần xác minh)
            </label>
          </p>
        )}
        <ErrorBox text={error} />
        {page === null && !error ? (
          <p className="muted">Đang tải…</p>
        ) : page && page.lines.length === 0 ? (
          <p className="empty">{term ? "Không dòng nào khớp." : "File rỗng."}</p>
        ) : (
          <ol className="lines" start={offset + 1}>
            {page?.lines.map((l, i) => (
              <li key={offset + i}>
                <code>{l || " "}</code>
              </li>
            ))}
          </ol>
        )}
        {page && <Pager total={page.total} limit={limit} offset={offset} onChange={setOffset} />}
      </div>
    </div>
  );
}
