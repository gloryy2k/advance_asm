import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { RECIPE_FIELDS, type Config, type Depth, type Health, type PlanPhase, type Profile, type Recipe, type ReviewData, type ScopeEntry } from "../api/types";
import { ConfigEditor } from "../components/ConfigEditor";
import { PageHead, Panel } from "../components/layout";
import { PolicyPanel } from "../components/PolicyPanel";
import { PresetPicker } from "../components/PresetPicker";
import { Badge, ErrorBox, Loading } from "../components/ui";
import { useData } from "../hooks/useData";
import { explain } from "../lib/errors";
import { cidrSize, durationLabel, formatCount } from "../lib/format";
import { PRESETS, applyPreset } from "../lib/presets";
import { go, programPath } from "../lib/router";

const MANUAL = new Set(["mobile", "other"]);
const GROUPS: [string, string][] = [
  ["wildcard", "Wildcard (liệt kê subdomain)"],
  ["web", "Web / domain"],
  ["ip", "IP"],
  ["cidr", "Dải IP (CIDR)"],
  ["source_code", "Source code"],
  ["mobile", "Mobile — làm tay"],
  ["other", "Khác — làm tay"],
];

const entryLabel = (e: ScopeEntry) => {
  const size = e.category === "cidr" ? cidrSize(e.pattern) : null;
  return size ? `${e.pattern} (${formatCount(size)} địa chỉ)` : e.pattern;
};
const recipeOf = (c: Config): Recipe => Object.fromEntries(RECIPE_FIELDS.map((f) => [f, c[f]])) as Recipe;

export function Review({ id }: { id: string }) {
  const info = useData<ReviewData>("/api/scans/" + id + "/review");
  const health = useData<Health>("/api/health");
  const [config, setConfig] = useState<Config | null>(null);
  const [profiles, setProfiles] = useState<{ builtin: Profile[]; custom: Profile[] } | null>(null);
  const [baseId, setBaseId] = useState("");
  const [plan, setPlan] = useState<PlanPhase[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [ack, setAck] = useState(false);
  const [ackStrong, setAckStrong] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newName, setNewName] = useState("");
  const [asDefault, setAsDefault] = useState(false);
  const confirmRef = useRef<HTMLElement>(null);
  const autoPassive = useRef(false);

  useEffect(() => {
    let live = true;
    api<Config>("/api/scans/" + id + "/config").then((c) => live && setConfig(c)).catch((e) => live && setError(explain(e)));
    api<{ builtin?: Profile[]; custom?: Profile[] }>("/api/profiles").then((p) => live && setProfiles({ builtin: p.builtin || [], custom: p.custom || [] })).catch(() => undefined);
    return () => { live = false; };
  }, [id]);
  useEffect(() => {
    if (config && !baseId) setBaseId("builtin:" + config.depth);
  }, [config, baseId]);

  // Which steps will run for the config as it is *right now* (server decides, so Review never lies).
  const planKey = config ? JSON.stringify(config) : "";
  useEffect(() => {
    if (!config) return;
    let live = true;
    const t = setTimeout(() => {
      api<{ phases: PlanPhase[] }>("/api/meta/plan", { method: "POST", body: planKey })
        .then((r) => live && setPlan(r.phases || null))
        .catch(() => undefined);
    }, 200);
    return () => { live = false; clearTimeout(t); };
  }, [planKey, config === null]);

  const entries = info.data?.scope || [];
  const ins = entries.filter((e) => e.kind === "in");
  const outs = entries.filter((e) => e.kind === "out");
  const all = useMemo(() => [...(profiles?.builtin || []), ...(profiles?.custom || [])], [profiles]);
  const base = all.find((p) => String(p.id) === baseId);
  const edit = (patch: Partial<Config>) => setConfig((c) => (c ? { ...c, ...patch } : c));

  const included = useMemo(
    () => (config ? ins.filter((e) => !MANUAL.has(e.category) && config.categories_enabled.includes(e.category) && !config.excluded_hosts.includes(e.pattern)) : []),
    [config, ins],
  );

  // A draft saved at Light/Strong but resolved from data that only supports Passive starts on Passive, once.
  const allowed = info.data?.launch_gate?.allowed_depths;
  useEffect(() => {
    if (autoPassive.current || !config || !allowed || allowed.includes(config.depth) || config.depth === "passive") return;
    autoPassive.current = true;
    const found = profiles?.builtin.find((p) => p.id === "builtin:passive");
    setConfig(found ? { ...config, ...found.config } : applyPreset(config, "passive"));
    setBaseId("builtin:passive");
  }, [allowed, config, profiles]);

  if (info.error && !info.data) return <ErrorBox text={info.error} />;
  if (!info.data || !config) return <><ErrorBox text={error} /><Loading label="Đang tải cấu hình…" /></>;
  const review = info.data;
  const missing = health.data?.missing_by_depth || {};
  const preset = PRESETS.find((p) => p.depth === config.depth)!;
  const isDraft = review.scan.status === "draft";
  const needAck = config.depth !== "passive";
  // Light/Strong need verified-enough scope + policy; the server enforces it too (scope_incomplete).
  const gate = review.launch_gate;
  const gateReason = gate && gate.allowed_depths.length < 3 ? "Thiếu dữ liệu: " + (gate.missing.join(", ") || "scope/policy") : "";
  const blockedDepths: Record<string, string> = gateReason ? Object.fromEntries((["light", "strong"] as Depth[]).filter((d) => !gate!.allowed_depths.includes(d)).map((d) => [d, gateReason])) : {};
  const depthBlocked = !!blockedDepths[config.depth];
  const unsupported = health.data?.runtime && !health.data.runtime.recon_supported;
  const blocker = !isDraft ? "Scan này đã được launch."
    : depthBlocked ? gateReason + ". Chỉ chạy được Passive cho tới khi đủ dữ liệu."
    : unsupported ? health.data!.runtime!.reason
    : included.length === 0 ? "Chưa có mục IN nào được chọn để kiểm tra."
    : needAck && !ack ? "Cần xác nhận program cho phép scan tự động."
    : config.depth === "strong" && !ackStrong ? "Cần xác nhận hiểu rủi ro của Strong." : "";

  const chooseBase = (profile: Profile) => {
    setConfig(applyRecipeTo(config, profile.config));
    setBaseId(String(profile.id));
    setAck(false);
    setAckStrong(false);
  };
  const applyRecipeTo = (c: Config, recipe: Recipe): Config => ({ ...c, ...recipe });
  const choosePreset = (d: Depth) => {
    const found = profiles?.builtin.find((p) => p.id === "builtin:" + d);
    if (found) chooseBase(found);
    else { setConfig(applyPreset(config, d)); setBaseId("builtin:" + d); setAck(false); setAckStrong(false); }
  };
  async function saveProfile() {
    if (!newName.trim()) return;
    try {
      const made = await api<Profile>("/api/profiles", { method: "POST", body: JSON.stringify({ name: newName.trim(), based_on: config!.depth, config: recipeOf(config!) }) });
      if (asDefault) await api("/api/programs/" + encodeURIComponent(review.slug) + "/default-profile", { method: "PUT", body: JSON.stringify({ profile_id: made.id }) });
      { const p = await api<{ builtin?: Profile[]; custom?: Profile[] }>("/api/profiles"); setProfiles({ builtin: p.builtin || [], custom: p.custom || [] }); }
      setBaseId(String(made.id));
      setSaving(false);
      setNewName("");
    } catch (e) { setError(explain(e)); }
  }
  async function launch() {
    if (blocker) return;
    setBusy(true);
    setError("");
    try {
      await api("/api/scans/" + id + "/launch", { method: "POST", body: JSON.stringify({ config, automation_ack: needAck && ack }) });
      go("/scan/" + id);
    } catch (e) { setError(explain(e)); setBusy(false); }
  }
  async function discard() {
    if (!confirm("Xoá bản nháp này? Chưa có gì được quét.")) return;
    try { await api("/api/scans/" + id, { method: "DELETE" }); go("/"); } catch (e) { setError(explain(e)); }
  }
  const toggleCategory = (category: string, on: boolean) =>
    edit({ categories_enabled: on ? [...new Set([...config.categories_enabled, category])] : config.categories_enabled.filter((c) => c !== category) });
  const toggleEntry = (pattern: string, on: boolean) =>
    edit({ excluded_hosts: on ? config.excluded_hosts.filter((h) => h !== pattern) : [...config.excluded_hosts, pattern] });
  const toolsOff = (missing[config.depth] || []);

  return (
    <>
      <PageHead
        eyebrow="BƯỚC 2/3 · XEM LẠI TRƯỚC KHI CHẠY"
        title={<>Xem lại · {review.slug} <small className="inline">scan #{id}</small></>}
        sub="Chưa có gì được quét. Kiểm tra độ tin cậy của scope và policy, chọn mức quét, rồi mới bắt đầu."
      />
      <ErrorBox text={error} />
      {review.warnings.map((w) => <p className="warnbox" key={w}>⚠ {w}</p>)}

      <PolicyPanel review={review} />

      <Panel id="scope-h" title="Scope" hint="Bỏ chọn để loại một mục khỏi lần quét này. Mục OUT luôn bị chặn bởi scope gate.">
        {GROUPS.map(([category, label]) => {
          const group = ins.filter((e) => e.category === category);
          if (!group.length) return null;
          const manual = MANUAL.has(category);
          return (
            <fieldset className="scope-group" key={category}>
              <legend>
                <label className="check">
                  <input type="checkbox" disabled={manual} aria-label={"Nhóm " + label} checked={!manual && config.categories_enabled.includes(category)} onChange={(e) => toggleCategory(category, e.target.checked)} />
                  <strong>{label}</strong> <span className="muted">({group.length})</span>
                </label>
              </legend>
              {manual && <p className="muted">Không tự động recon; được ghi vào PROGRAM.md và brief để làm tay.</p>}
              {group.map((entry) => (
                <label className="check entry" key={entry.pattern}>
                  {!manual && (
                    <input type="checkbox" aria-label={"Include " + entry.pattern} disabled={!config.categories_enabled.includes(category)}
                      checked={!config.excluded_hosts.includes(entry.pattern)} onChange={(e) => toggleEntry(entry.pattern, e.target.checked)} />
                  )}
                  <code>{entryLabel(entry)}</code>
                  {entry.instruction && <small>{entry.instruction}</small>}
                </label>
              ))}
            </fieldset>
          );
        })}
        {outs.length > 0 && (
          <fieldset className="scope-group out">
            <legend><strong>Loại trừ (OUT)</strong> <span className="muted">({outs.length}) — luôn bị chặn</span></legend>
            {outs.map((entry) => (
              <p className="entry" key={entry.pattern}><Badge tone="out">OUT</Badge> <code>{entryLabel(entry)}</code>{entry.instruction && <small>{entry.instruction}</small>}</p>
            ))}
          </fieldset>
        )}
        <details className="adv">
          <summary>Loại trừ thêm host/pattern (tuỳ chọn)</summary>
          <label>Mỗi dòng một host hoặc pattern
            <textarea rows={3} value={config.excluded_hosts.join("\n")} onChange={(e) => edit({ excluded_hosts: e.target.value.split("\n").map((l) => l.trim()).filter(Boolean) })} />
          </label>
        </details>
      </Panel>

      <Panel id="preset-h" title="Mức quét" hint="Chọn một preset, một profile của bạn, hoặc chỉnh từng phần ở dưới. Preset chỉ là điểm xuất phát — mọi giá trị đều sửa được.">
        <PresetPicker value={config.depth} missing={missing} blocked={blockedDepths} onChange={choosePreset} />
        {review.source === "h1" && !gateReason && (
          <p className="muted" data-testid="gate-note">
            Light/Strong mở khoá nghĩa là <strong>đủ dữ liệu để cấu hình</strong>, không phải policy đã cho phép quét tự động.
            Việc đó do bạn quyết định sau khi đọc policy và tick xác nhận ở dưới.
          </p>
        )}
        <div className="profilebar">
          <label>Profile của tôi
            <select value={profiles?.custom.some((p) => String(p.id) === baseId) ? baseId : ""} onChange={(e) => { const p = profiles?.custom.find((x) => String(x.id) === e.target.value); if (p) chooseBase(p); }}>
              <option value="">— chọn profile đã lưu —</option>
              {profiles?.custom.map((p) => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
            </select>
          </label>
          {!saving ? (
            <button type="button" className="secondary small" onClick={() => setSaving(true)}>💾 Lưu cấu hình này thành profile…</button>
          ) : (
            <span className="saveform">
              <input aria-label="Tên profile" placeholder="Tên profile" value={newName} onChange={(e) => setNewName(e.target.value)} />
              <label className="check inline"><input type="checkbox" checked={asDefault} onChange={(e) => setAsDefault(e.target.checked)} />Mặc định cho program này</label>
              <button type="button" className="small" onClick={saveProfile} disabled={!newName.trim()}>Lưu</button>
              <button type="button" className="secondary small" onClick={() => setSaving(false)}>Huỷ</button>
            </span>
          )}
        </div>
        <ConfigEditor config={config} base={base?.config} baseName={base?.name} plan={plan} onChange={edit}
          onReset={() => base && chooseBase(base)} />
      </Panel>

      <section className="panel" aria-labelledby="go-h" ref={confirmRef} id="confirm">
        <h2 id="go-h">Xác nhận</h2>
        {needAck && (
          <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />Tôi đã đọc policy và program cho phép scan tự động ở mức này.</label>
        )}
        {config.depth === "strong" && (
          <label className="check"><input type="checkbox" checked={ackStrong} onChange={(e) => setAckStrong(e.target.checked)} />Tôi hiểu Strong gửi nhiều request (nmap/ffuf/nuclei) và chỉ dùng khi policy cho phép active scan.</label>
        )}
        {!needAck && <p className="muted">Passive không gửi request tới target nên không cần xác nhận thêm.</p>}
        <small>Sau khi chạy, scope đã chọn trở thành scope hiện hành của program <a href={"#" + programPath(review.slug)}>{review.slug}</a>.</small>
      </section>

      <div className="actionbar" role="region" aria-label="Bắt đầu quét">
        <div className="actionbar-info">
          <strong>{preset.title}</strong> · {included.length} mục IN{outs.length ? ` · ${outs.length} OUT` : ""} · ~{preset.eta.replace("~", "")} · tối đa {durationLabel(config.scan_timeout)}
          {toolsOff.length > 0 && <small>Thiếu công cụ: {toolsOff.join(", ")} — các bước đó sẽ bị bỏ qua.</small>}
          {isDraft && blocker && <small role="status" className="blocked">⚠ {blocker}</small>}
        </div>
        <div className="actionbar-buttons">
          {isDraft && blocker && (needAck && !ack || (config.depth === "strong" && !ackStrong)) &&
            <button type="button" className="secondary" onClick={() => confirmRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })}>↓ Tới ô xác nhận</button>}
          <button type="button" className="secondary" disabled={!isDraft} onClick={discard}>Huỷ bản nháp</button>
          <button disabled={busy || !!blocker} onClick={launch}>{busy ? "Đang launch…" : "Launch scan"}</button>
          {!isDraft && <a href={"#/scan/" + id}>Xem scan →</a>}
        </div>
      </div>
    </>
  );
}
