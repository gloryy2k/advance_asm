import { useState, type ReactNode } from "react";
import { STATUS_LABEL } from "../lib/format";

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  return <span className={"badge " + (tone || String(children).toLowerCase())}>{children}</span>;
}

export function StatusBadge({ status }: { status?: string | null }) {
  return <Badge tone={status || "none"}>{status ? STATUS_LABEL[status] || status : "chưa chạy"}</Badge>;
}

export function ErrorBox({ text, action }: { text: string; action?: ReactNode }) {
  return text ? (
    <div role="alert" className="error">
      {text} {action}
    </div>
  ) : null;
}

export function Loading({ label = "Đang tải…" }: { label?: string }) {
  return (
    <p role="status" className="muted">
      {label}
    </p>
  );
}

/** Loading / error / content in one place so every list has all three states. */
export function State({
  data,
  error,
  children,
  retry,
}: {
  data: unknown;
  error: string;
  children: ReactNode;
  retry?: () => void;
}) {
  if (error)
    return (
      <ErrorBox
        text={error}
        action={retry && <button className="secondary small" onClick={retry}>Thử lại</button>}
      />
    );
  if (data === null) return <Loading />;
  return <>{children}</>;
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function CopyButton({ text, label = "Sao chép" }: { text: string; label?: string }) {
  const [state, setState] = useState<"idle" | "ok" | "fail">("idle");
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("ok");
    } catch {
      setState("fail");
    }
    setTimeout(() => setState("idle"), 2000);
  }
  return (
    <button type="button" className="secondary small" onClick={copy}>
      {state === "ok" ? "Đã chép ✓" : state === "fail" ? "Không chép được — chọn rồi Ctrl+C" : label}
    </button>
  );
}

export function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <nav className="pager" aria-label="Phân trang">
      <button className="secondary small" disabled={offset <= 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        ← Trước
      </button>
      <span>
        Trang {page}/{pages} · {total.toLocaleString("vi-VN")} mục
      </span>
      <button className="secondary small" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
        Sau →
      </button>
    </nav>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge tone={severity}>{severity}</Badge>;
}
