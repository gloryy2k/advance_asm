import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Config, Depth, Health, ReviewData, ScopeEntry } from "../api/types";
import { Badge, ErrorBox, Loading } from "../components/ui";
import { PolicyPanel } from "../components/PolicyPanel";
import { PresetPicker } from "../components/PresetPicker";
import { useData } from "../hooks/useData";
import { explain } from "../lib/errors";
import { cidrSize, durationLabel, formatCount } from "../lib/format";
import { PRESETS, SEVERITY_LEVELS, applyPreset } from "../lib/presets";
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

function entryLabel(entry: ScopeEntry) {
  const size = entry.category === "cidr" ? cidrSize(entry.pattern) : null;
  return size ? `${entry.pattern} (${formatCount(size)} địa chỉ)` : entry.pattern;
}

export function Review({ id }: { id: string }) {
  const info = useData<ReviewData>("/api/scans/" + id + "/review");
  const health = useData<Health>("/api/health");
  const [config, setConfig] = useState<Config | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [ack, setAck] = useState(false);
  const [ackStrong, setAckStrong] = useState(false);
  const [advanced, setAdvanced] = useState(false);

  useEffect(() => {
    let live = true;
    api<Config>("/api/scans/" + id + "/config")
      .then((c) => live && setConfig(c))
      .catch((e) => live && setError(explain(e)));
    return () => {
      live = false;
    };
  }, [id]);

  const entries = info.data?.scope || [];
  const ins = entries.filter((e) => e.kind === "in");
  const outs = entries.filter((e) => e.kind === "out");
  const edit = (patch: Partial<Config>) => setConfig((c) => (c ? { ...c, ...patch } : c));

  const included = useMemo(
    () =>
      config
        ? ins.filter(
            (e) =>
              !MANUAL.has(e.category) &&
              config.categories_enabled.includes(e.category) &&
              !config.excluded_hosts.includes(e.pattern),
          )
        : [],
    [config, ins],
  );

  if (info.error && !info.data) return <ErrorBox text={info.error} />;
  if (!info.data || !config) return <><ErrorBox text={error} /><Loading label="Đang tải cấu hình…" /></>;
  const review = info.data;
  const missing = health.data?.missing_by_depth || {};
  const preset = PRESETS.find((p) => p.depth === config.depth)!;
  const missingNow = missing[config.depth] || [];
  const isDraft = review.scan.status === "draft";
  const needAck = config.depth !== "passive";

  const blocker = !isDraft
    ? "Scan này đã được launch."
    : included.length === 0
      ? "Chưa có mục IN nào được chọn để kiểm tra."
      : needAck && !ack
        ? "Cần xác nhận program cho phép scan tự động."
        : config.depth === "strong" && !ackStrong
          ? "Cần xác nhận hiểu rủi ro của Strong."
          : "";

  async function launch() {
    if (!config || blocker) return;
    setBusy(true);
    setError("");
    try {
      await api("/api/scans/" + id + "/launch", {
        method: "POST",
        body: JSON.stringify({ config, automation_ack: needAck && ack }),
      });
      go("/scan/" + id);
    } catch (e) {
      setError(explain(e));
      setBusy(false);
    }
  }

  async function discard() {
    if (!confirm("Xoá bản nháp này? Chưa có gì được quét.")) return;
    try {
      await api("/api/scans/" + id, { method: "DELETE" });
      go("/");
    } catch (e) {
      setError(explain(e));
    }
  }

  const toggleCategory = (category: string, on: boolean) =>
    edit({
      categories_enabled: on
        ? [...new Set([...config.categories_enabled, category])]
        : config.categories_enabled.filter((c) => c !== category),
    });
  const toggleEntry = (pattern: string, on: boolean) =>
    edit({
      excluded_hosts: on
        ? config.excluded_hosts.filter((h) => h !== pattern)
        : [...config.excluded_hosts, pattern],
    });
  const severities = new Set(config.nuclei_severity.split(",").filter(Boolean));

  return (
    <>
      <p className="eyebrow">BƯỚC 2/3 · XEM LẠI TRƯỚC KHI CHẠY</p>
      <h1>
        Review · {review.slug} <small className="inline">scan #{id}</small>
      </h1>
      <ErrorBox text={error} />
      {review.warnings.map((w) => (
        <p className="warnbox" key={w}>⚠ {w}</p>
      ))}

      <section className="card summary" aria-labelledby="sum-h">
        <h2 id="sum-h">Sẽ làm gì</h2>
        <ul className="plain">
          <li>
            <strong>{preset.title}</strong> — {preset.touches ? "có gửi request tới target" : "không chạm target"}; ước tính{" "}
            {preset.eta}, giới hạn cứng {durationLabel(config.scan_timeout)}.
          </li>
          <li>
            Kiểm tra <strong>{included.length}</strong> mục IN
            {outs.length ? <>, luôn chặn <strong>{outs.length}</strong> mục OUT</> : null}
            {ins.some((e) => MANUAL.has(e.category)) && ", mobile/khác làm tay (ghi vào PROGRAM.md)"}.
          </li>
          <li>
            Công cụ:{" "}
            {preset.tools.map((t) => (
              <Badge key={t} tone={missing[config.depth]?.includes(t) ? "failed" : "done"}>
                {t}
                {missing[config.depth]?.includes(t) ? " ✗" : ""}
              </Badge>
            ))}
          </li>
        </ul>
        {missingNow.length > 0 && (
          <p className="warnbox">
            Thiếu công cụ cho {preset.title}: {missingNow.join(", ")}. Các bước tương ứng sẽ bị bỏ qua (không lỗi),
            brief sẽ ít dữ liệu hơn.
          </p>
        )}
      </section>

      <section className="card" aria-labelledby="preset-h">
        <h2 id="preset-h">Mức quét</h2>
        <PresetPicker value={config.depth} missing={missing} onChange={(d: Depth) => { setConfig(applyPreset(config, d)); setAck(false); setAckStrong(false); }} />
      </section>

      <PolicyPanel review={review} />

      <section className="card" aria-labelledby="scope-h">
        <h2 id="scope-h">Scope</h2>
        <p className="muted">Bỏ chọn để loại một mục khỏi lần quét này. Mục OUT luôn bị chặn bởi scope gate.</p>
        {GROUPS.map(([category, label]) => {
          const group = ins.filter((e) => e.category === category);
          if (!group.length) return null;
          const manual = MANUAL.has(category);
          return (
            <fieldset className="scope-group" key={category}>
              <legend>
                <label className="check">
                  <input
                    type="checkbox"
                    disabled={manual}
                    aria-label={"Nhóm " + label}
                    checked={!manual && config.categories_enabled.includes(category)}
                    onChange={(e) => toggleCategory(category, e.target.checked)}
                  />
                  <strong>{label}</strong> <span className="muted">({group.length})</span>
                </label>
              </legend>
              {manual && <p className="muted">Không tự động recon; được ghi vào PROGRAM.md và brief để làm tay.</p>}
              {group.map((entry) => (
                <label className="check entry" key={entry.pattern}>
                  {!manual && (
                    <input
                      type="checkbox"
                      aria-label={"Include " + entry.pattern}
                      disabled={!config.categories_enabled.includes(category)}
                      checked={!config.excluded_hosts.includes(entry.pattern)}
                      onChange={(e) => toggleEntry(entry.pattern, e.target.checked)}
                    />
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
            <legend>
              <strong>Loại trừ (OUT)</strong> <span className="muted">({outs.length}) — luôn bị chặn</span>
            </legend>
            {outs.map((entry) => (
              <p className="entry" key={entry.pattern}>
                <Badge tone="out">OUT</Badge> <code>{entryLabel(entry)}</code>
                {entry.instruction && <small>{entry.instruction}</small>}
              </p>
            ))}
          </fieldset>
        )}
      </section>

      <section className="card" aria-labelledby="adv-h">
        <h2 id="adv-h">
          <button type="button" className="linklike" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
            Nâng cao {advanced ? "▾" : "▸"}
          </button>
        </h2>
        {advanced && (
          <div className="form">
            <div className="three">
              <label>
                Số luồng (threads)
                <input type="number" min={1} max={200} value={config.threads} onChange={(e) => edit({ threads: Number(e.target.value) })} />
                <small>Tối đa 200</small>
              </label>
              <label>
                Giới hạn request/giây
                <input type="number" min={1} max={500} value={config.rate_limit} onChange={(e) => edit({ rate_limit: Number(e.target.value) })} />
                <small>Theo policy của program; tối đa 500</small>
              </label>
              <label>
                Timeout cứng (giây)
                <input type="number" min={1} value={config.scan_timeout} onChange={(e) => edit({ scan_timeout: Number(e.target.value) })} />
                <small>Tối đa theo mức quét</small>
              </label>
            </div>
            <fieldset className="plainfs">
              <legend>Mức nghiêm trọng của nuclei</legend>
              {SEVERITY_LEVELS.map((s) => (
                <label className="check inline" key={s}>
                  <input
                    type="checkbox"
                    checked={severities.has(s)}
                    disabled={config.skip_nuclei}
                    onChange={(e) => {
                      const next = new Set(severities);
                      e.target.checked ? next.add(s) : next.delete(s);
                      edit({ nuclei_severity: SEVERITY_LEVELS.filter((l) => next.has(l)).join(",") });
                    }}
                  />
                  {s}
                </label>
              ))}
            </fieldset>
            <label className="check"><input type="checkbox" checked={config.skip_nmap} onChange={(e) => edit({ skip_nmap: e.target.checked })} />Bỏ qua quét cổng (nmap)</label>
            <label className="check"><input type="checkbox" checked={config.skip_nuclei} onChange={(e) => edit({ skip_nuclei: e.target.checked })} />Bỏ qua nuclei</label>
            <label className="check"><input type="checkbox" checked={config.skip_active_crawl} onChange={(e) => edit({ skip_active_crawl: e.target.checked })} />Bỏ qua crawl chủ động</label>
            <label>
              Loại trừ thêm (mỗi dòng một host/pattern)
              <textarea
                rows={3}
                value={config.excluded_hosts.join("\n")}
                onChange={(e) => edit({ excluded_hosts: e.target.value.split("\n").map((l) => l.trim()).filter(Boolean) })}
              />
            </label>
            <button type="button" className="secondary small" onClick={() => setConfig(applyPreset(config, config.depth))}>
              Đặt lại theo mức quét
            </button>
          </div>
        )}
      </section>

      <section className="card launchbar" aria-labelledby="go-h">
        <h2 id="go-h">Xác nhận &amp; chạy</h2>
        {needAck && (
          <label className="check">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            Tôi đã đọc policy và program cho phép scan tự động ở mức này.
          </label>
        )}
        {config.depth === "strong" && (
          <label className="check">
            <input type="checkbox" checked={ackStrong} onChange={(e) => setAckStrong(e.target.checked)} />
            Tôi hiểu Strong gửi nhiều request (nmap/ffuf/nuclei) và chỉ dùng khi policy cho phép active scan.
          </label>
        )}
        <div className="actions">
          <button disabled={busy || !!blocker} onClick={launch}>
            {busy ? "Đang launch…" : "Launch scan"}
          </button>
          <button type="button" className="secondary" disabled={!isDraft} onClick={discard}>Huỷ bản nháp</button>
          {!isDraft && <a href={"#/scan/" + id}>Xem scan →</a>}
          {isDraft && blocker && <span className="muted" role="status">{blocker}</span>}
        </div>
        <small>Sau khi chạy, scope đã chọn trở thành scope hiện hành của program <a href={"#" + programPath(review.slug)}>{review.slug}</a>.</small>
      </section>
    </>
  );
}
