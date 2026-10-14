import type { Depth } from "../api/types";
import { PRESETS } from "../lib/presets";

export function PresetPicker({
  value,
  onChange,
  missing,
}: {
  value: Depth;
  onChange: (depth: Depth) => void;
  missing: Record<string, string[]>;
}) {
  return (
    <div className="presets" role="radiogroup" aria-label="Depth">
      {PRESETS.map((p) => (
        <button
          key={p.depth}
          type="button"
          role="radio"
          aria-checked={value === p.depth}
          className={"preset " + (value === p.depth ? "selected" : "") + (p.depth === "strong" ? " strong" : "")}
          onClick={() => onChange(p.depth)}
        >
          <strong>{p.title}</strong>
          <span className="tagline">{p.tagline}</span>
          <span className="detail">{p.detail}</span>
          <span className="meta">
            {p.touches ? "Chạm target" : "Không chạm target"} · {p.eta}
            {missing[p.depth]?.length ? ` · thiếu ${missing[p.depth].length} tool` : ""}
          </span>
        </button>
      ))}
    </div>
  );
}
