import { useEffect, useState } from "react";
import { api } from "../api/client";
import { RECIPE_FIELDS, type Config, type Depth, type PlanPhase, type Profile, type Recipe } from "../api/types";
import { ConfigEditor } from "../components/ConfigEditor";
import { PageHead, Panel } from "../components/layout";
import { Badge, EmptyState, ErrorBox } from "../components/ui";
import { explain } from "../lib/errors";

type Editing = { id?: number; name: string; description: string; based: Depth; config: Config; base: Recipe };
const toConfig = (r: Recipe): Config => ({ categories_enabled: ["web"], excluded_hosts: [], ...(r as any) });
const recipeOf = (c: Config): Recipe => Object.fromEntries(RECIPE_FIELDS.map((f) => [f, c[f]])) as Recipe;

export function Profiles() {
  const [data, setData] = useState<{ builtin: Profile[]; custom: Profile[] } | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Editing | null>(null);
  const [plan, setPlan] = useState<PlanPhase[] | null>(null);
  const load = () => api<{ builtin: Profile[]; custom: Profile[] }>("/api/profiles").then(setData).catch((e) => setError(explain(e)));
  useEffect(() => { void load(); }, []);
  const key = editing ? JSON.stringify(editing.config) : "";
  useEffect(() => {
    if (!editing) return;
    let live = true;
    const t = setTimeout(() => api<{ phases: PlanPhase[] }>("/api/meta/plan", { method: "POST", body: key }).then((r) => live && setPlan(r.phases)).catch(() => undefined), 200);
    return () => { live = false; clearTimeout(t); };
  }, [key, editing === null]);

  const start = (p?: Profile) => {
    const from = p || data?.builtin.find((b) => b.id === "builtin:light")!;
    setEditing({ id: p && !p.builtin ? (p.id as number) : undefined, name: p && !p.builtin ? p.name : "", description: p && !p.builtin ? p.description : "",
      based: (p?.based_on || (p?.builtin ? String(p.id).split(":")[1] : "light") || "light") as Depth, config: toConfig(from.config), base: from.config });
    setError("");
  };
  async function save() {
    if (!editing) return;
    try {
      const body = JSON.stringify({ name: editing.name, description: editing.description, based_on: editing.based, config: recipeOf(editing.config) });
      await api(editing.id ? `/api/profiles/${editing.id}` : "/api/profiles", { method: editing.id ? "PUT" : "POST", body });
      setEditing(null);
      await load();
    } catch (e) { setError(explain(e)); }
  }
  async function act(url: string, method: string) {
    try { await api(url, { method }); await load(); } catch (e) { setError(explain(e)); }
  }
  const summaryOf = (c: Recipe) => `${c.depth} · ${c.threads} luồng · ${c.rate_limit} req/s · nuclei ${c.skip_nuclei ? "tắt" : c.nuclei_severity || "—"}${c.skip_historical ? " · không URL lịch sử" : ""}`;

  return (
    <>
      <PageHead eyebrow="CẤU HÌNH" title="Profile quét" sub="Lưu cách quét của bạn để dùng lại. Profile chỉ chứa cách quét (tốc độ, bước bật/tắt, giới hạn dữ liệu), không chứa scope."
        actions={!editing && <button onClick={() => start()}>+ Tạo profile</button>} />
      <ErrorBox text={error} />
      {editing && (
        <Panel id="edit-h" title={editing.id ? "Sửa profile" : "Profile mới"} tone="accent">
          <div className="form">
            <label>Tên<input aria-label="Tên profile" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="vd: Nhanh, bỏ nuclei" /></label>
            <label>Mô tả (tuỳ chọn)<input value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></label>
            <label>Bắt đầu từ preset
              <select value={editing.based} onChange={(e) => {
                const b = data?.builtin.find((x) => x.id === "builtin:" + e.target.value);
                if (b) setEditing({ ...editing, based: e.target.value as Depth, config: toConfig(b.config), base: b.config });
              }}>
                <option value="passive">Passive</option><option value="light">Light</option><option value="strong">Strong</option>
              </select>
            </label>
          </div>
          <ConfigEditor config={editing.config} base={editing.base} baseName={editing.based} plan={plan} advancedOpen
            onChange={(patch) => setEditing({ ...editing, config: { ...editing.config, ...patch } })}
            onReset={() => setEditing({ ...editing, config: toConfig(editing.base) })} />
          <div className="actions">
            <button onClick={save} disabled={!editing.name.trim()}>Lưu profile</button>
            <button className="secondary" onClick={() => setEditing(null)}>Huỷ</button>
          </div>
        </Panel>
      )}
      <Panel id="custom-h" title="Profile của tôi">
        {data && data.custom.length === 0 ? <EmptyState title="Chưa có profile nào" action={!editing && <button onClick={() => start()}>Tạo profile đầu tiên</button>}>Hoặc chỉnh cấu hình ở màn Xem lại rồi bấm “Lưu cấu hình này thành profile”.</EmptyState> : (
          <ul className="profiles">
            {data?.custom.map((p) => (
              <li key={p.id}>
                <div><strong>{p.name}</strong> {p.based_on && <Badge>{p.based_on}</Badge>}{p.description && <small>{p.description}</small>}<small>{summaryOf(p.config)}</small></div>
                <span className="actions">
                  <button className="secondary small" onClick={() => start(p)}>Sửa</button>
                  <button className="secondary small" onClick={() => act(`/api/profiles/${p.id}/duplicate`, "POST")}>Nhân bản</button>
                  <button className="secondary small" onClick={() => confirm(`Xoá profile “${p.name}”?`) && act(`/api/profiles/${p.id}`, "DELETE")}>Xoá</button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel id="builtin-h" title="Preset có sẵn" hint="Chỉ đọc. Để chỉnh, tạo profile từ preset.">
        <ul className="profiles">
          {data?.builtin.map((p) => (
            <li key={p.id}><div><strong>{p.name}</strong><small>{p.description}</small><small>{summaryOf(p.config)}</small></div>
              <button className="secondary small" onClick={() => start(p)}>Tạo profile từ preset này</button></li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
