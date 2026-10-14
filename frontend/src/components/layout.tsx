import type { ReactNode } from "react";
import type { Trust } from "../api/types";

export function PageHead({
  eyebrow,
  title,
  sub,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="pagehead">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      {actions && <div className="head-actions">{actions}</div>}
    </header>
  );
}

/** A titled block that says what it is for and where its output lives. */
export function Panel({
  id,
  title,
  hint,
  output,
  children,
  actions,
  tone,
}: {
  id?: string;
  title: ReactNode;
  hint?: ReactNode;
  output?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  tone?: "accent" | "warn";
}) {
  return (
    <section className={"panel" + (tone ? " " + tone : "")} aria-labelledby={id}>
      <div className="panel-head">
        <div>
          <h2 id={id}>{title}</h2>
          {hint && <p className="hint">{hint}</p>}
        </div>
        {actions && <div className="panel-actions">{actions}</div>}
      </div>
      {children}
      {output && <p className="output-note">📍 {output}</p>}
    </section>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          className={value === o.value ? "on" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Chip({ tone, children, title }: { tone?: string; children: ReactNode; title?: string }) {
  return (
    <span className={"chip " + (tone || "")} title={title}>
      {children}
    </span>
  );
}

export function TrustBadge({ trust, full = false }: { trust?: Trust; full?: boolean }) {
  if (!trust) return null;
  const unverifiedPublic = trust.level === "public" || trust.level === "public_page";
  const tone = unverifiedPublic ? "warn" : trust.verified ? "good" : "plain";
  return (
    <div className={"trust " + tone}>
      <strong>{trust.verified ? "✓ " : unverifiedPublic ? "⚠ " : "ℹ "}{trust.label}</strong>
      {full && (
        <>
          <p>{trust.detail}</p>
          {trust.missing.length > 0 && <p>Còn thiếu: {trust.missing.join(", ")}.</p>}
          {trust.checklist.length > 0 && (
            <ol>
              {trust.checklist.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ol>
          )}
          {trust.official_url && !trust.verified && (
            <p>
              <a href={trust.official_url} target="_blank" rel="noreferrer noopener">
                Mở trang chính thức ↗
              </a>
            </p>
          )}
        </>
      )}
    </div>
  );
}
