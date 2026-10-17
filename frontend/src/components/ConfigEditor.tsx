import { useState } from "react";
import { api, ApiError } from "../api/client";
import { RECIPE_FIELDS, type Config, type PlanPhase, type Recipe } from "../api/types";
import { SEVERITY_LEVELS } from "../lib/presets";
import { Panel } from "./layout";
import { StepList, type StepRow } from "./StepList";

type LookupTemplate = { path: string; name: string | null; severity: string | null };
type LookupResult = { tag: string; total: number; templates: LookupTemplate[]; truncated: boolean };

/** Preview of the pool `-as`/`-tags` draw from (backend.templates.py::lookup_by_tag — pure local listing, no
 * target touched). Which template actually fires on a host is decided by nuclei at scan time from that host's
 * own fingerprint; this never claims otherwise. Shared by Review and Profiles (no scan context needed). */
function TemplateLookup() {
  const [tag, setTag] = useState("");
  const [result, setResult] = useState<LookupResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const search = async () => {
    const value = tag.trim().toLowerCase();
    if (!value) return;
    setLoading(true);
    setError("");
    try {
      setResult(await api<LookupResult>("/api/tools/templates/lookup?" + new URLSearchParams({ tag: value })));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không tra được");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };
  return (
    <details className="adv">
      <summary>Tra cứu template theo công nghệ/tag</summary>
      <p className="muted">
        Xem trước <strong>bộ template nuclei đã cài</strong> có gắn một tag (vd <code>wordpress</code>, <code>nginx</code>, <code>mysql</code>, <code>cve</code>…).
        Đây là toàn bộ template <em>có thể</em> được <code>-as</code> chọn tới nếu nuclei dò ra công nghệ đó trên một host — không phải danh sách
        "sẽ chạy cho scan này", vì điều đó chỉ biết được sau khi nuclei hỏi host thật.
      </p>
      <div className="filters">
        <input aria-label="Tag cần tra" placeholder="vd: wordpress" value={tag} onChange={(e) => setTag(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()} />
        <button type="button" className="secondary small" disabled={loading || !tag.trim()} onClick={search}>{loading ? "Đang tra…" : "Tra cứu"}</button>
      </div>
      {error && <p className="muted" role="alert">{error}</p>}
      {result && (
        result.total === 0 ? <p className="muted">Không có template nào gắn tag "{result.tag}" trong bộ đã cài.</p> : (
          <>
            <p className="muted" data-testid="lookup-total">
              {result.total} template gắn tag "{result.tag}"{result.truncated && <> (chỉ hiện {result.templates.length} đầu tiên)</>}.
            </p>
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Bảng dữ liệu, cuộn được">
              <table>
                <thead><tr><th>Tên</th><th>Mức</th><th>Đường dẫn</th></tr></thead>
                <tbody>
                  {result.templates.map((t) => (
                    <tr key={t.path}><td>{t.name || "—"}</td><td>{t.severity || "—"}</td><td><code>{t.path}</code></td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )
      )}
    </details>
  );
}

/** Which user switch controls a step. `inverted` = the config stores "skip". */
const CONTROL: Record<string, keyof Config> = {
  port_scan: "skip_nmap",
  nuclei: "skip_nuclei",
  url_crawl: "skip_active_crawl",
  dir_fuzz: "skip_ffuf",
  url_history: "skip_historical",
  takeover: "skip_takeover",
  secrets: "skip_secrets",
};
const STATUS_LABEL = { on: "Sẽ chạy", off: "Tắt", missing_tool: "Thiếu công cụ" } as const;
const FIELD_LABEL: Record<string, string> = {
  depth: "mức quét", threads: "số luồng", rate_limit: "request/giây", scan_timeout: "thời gian tối đa", nuclei_severity: "mức nuclei",
  skip_nmap: "quét cổng", skip_nuclei: "nuclei", skip_active_crawl: "crawl chủ động", skip_ffuf: "dò thư mục", nmap_timeout: "giới hạn nmap", ffuf_maxtime: "giới hạn ffuf", deep_hosts: "số host quét sâu", nuclei_allow_intrusive: "template nguy hiểm", nuclei_auto_select: "tự chọn theo công nghệ", skip_historical: "URL lịch sử",
  skip_takeover: "takeover", skip_secrets: "bí mật trong JS", max_js_files: "số file JS", url_exclude_patterns: "đường dẫn loại trừ",
  brief_budget_kb: "dung lượng brief", brief_top_assets: "số asset trong brief", brief_top_urls: "số URL trong brief",
};

export function changedFields(config: Config, base: Recipe | undefined): string[] {
  if (!base) return [];
  return RECIPE_FIELDS.filter((f) => base[f] !== undefined && JSON.stringify(config[f]) !== JSON.stringify(base[f]));
}

/** Everything a user can tune, grouped by what it affects. Shared by Review and the Profiles page. */
export function ConfigEditor({
  config,
  base,
  baseName,
  plan,
  onChange,
  onReset,
  scopeFields,
  advancedOpen = false,
}: {
  config: Config;
  base?: Recipe;
  baseName?: string;
  plan: PlanPhase[] | null;
  onChange: (patch: Partial<Config>) => void;
  onReset?: () => void;
  scopeFields?: React.ReactNode;
  advancedOpen?: boolean;
}) {
  const diff = changedFields(config, base);
  const severities = new Set(config.nuclei_severity.split(",").filter(Boolean));
  const [patterns, setPatterns] = useState(config.url_exclude_patterns.join("\n"));
  const forcedOff = new Set((plan || []).filter((p) => p.forced).map((p) => p.key));
  const rows: StepRow[] = (plan || []).map((p) => ({
    key: p.key, title: p.title, what: p.what, touches: p.touches, status: p.status,
    statusLabel: STATUS_LABEL[p.status], reason: p.reason, outputLabel: p.view.label,
  }));
  return (
    <div className="editor">
      {base && (
        <p className={"diffline " + (diff.length ? "changed" : "")} role="status">
          {diff.length
            ? <>Khác preset {baseName}: <strong>{diff.length} mục</strong> — {diff.map((f) => FIELD_LABEL[f] || f).join(", ")}. </>
            : <>Đang đúng theo preset {baseName}. </>}
          {diff.length > 0 && onReset && <button type="button" className="linklike" onClick={onReset}>↺ Đặt lại</button>}
        </p>
      )}

      <Panel id="ed-steps" title="Các bước & kết quả" hint="Bật/tắt từng bước. Mỗi bước ghi rõ nó làm gì, có chạm target không, và kết quả xem ở đâu.">
        {plan === null ? <p className="muted">Đang tính…</p> : (
          <StepList
            rows={rows}
            toggle={(r) => {
              const field = CONTROL[r.key];
              if (!field) return <span className="step-fixed" aria-hidden="true">●</span>;
              const forced = forcedOff.has(r.key);  // off because of the depth itself, not the user's switch
              return (
                <input
                  type="checkbox"
                  aria-label={`Chạy: ${r.title}`}
                  checked={!config[field] && !forced}
                  disabled={forced}
                  onChange={(e) => onChange({ [field]: !e.target.checked } as Partial<Config>)}
                />
              );
            }}
          />
        )}
      </Panel>

      <details className="adv" open={advancedOpen}>
      <summary>Tuỳ chỉnh chi tiết: tốc độ, nuclei, dữ liệu &amp; brief</summary>
      <Panel id="ed-speed" title="Tốc độ" hint="Càng cao càng nhanh nhưng càng dễ chạm giới hạn của target. Một số công cụ có giới hạn riêng nên có thể không theo hết các giá trị này.">
        <div className="three">
          <label>Số luồng
            <input type="number" min={1} max={200} value={config.threads} onChange={(e) => onChange({ threads: Number(e.target.value) })} />
            <small>1–200</small>
          </label>
          <label>Request/giây
            <input type="number" min={1} max={500} value={config.rate_limit} onChange={(e) => onChange({ rate_limit: Number(e.target.value) })} />
            <small>1–500</small>
          </label>
          <label>Thời gian tối đa (giây)
            <input type="number" min={1} value={config.scan_timeout} onChange={(e) => onChange({ scan_timeout: Number(e.target.value) })} />
            <small>Hết giờ thì dừng và lấy phần đã có</small>
          </label>
        </div>
      </Panel>

      <Panel id="ed-budget" title="Ngân sách công cụ" hint="Chương trình lớn cần nhiều thời gian hơn chương trình nhỏ. Để trống để dùng mặc định của máy chủ; 0 = không giới hạn từng lệnh (vẫn nằm trong thời gian tối đa của scan). Hết giới hạn thì công cụ dừng và giữ kết quả đã có.">
        <div className="three">
          <label>nmap tối đa mỗi lần chạy (giây)
            <input type="number" min={0} max={7200} aria-label="nmap tối đa (giây)" placeholder="mặc định" value={config.nmap_timeout ?? ""}
              onChange={(e) => onChange({ nmap_timeout: e.target.value === "" ? null : Number(e.target.value) })} />
            <small>Chỉ chạy ở bước quét sâu (Strong)</small>
          </label>
          <label>ffuf tối đa mỗi lần chạy (giây)
            <input type="number" min={0} max={7200} aria-label="ffuf tối đa (giây)" placeholder="mặc định" value={config.ffuf_maxtime ?? ""}
              onChange={(e) => onChange({ ffuf_maxtime: e.target.value === "" ? null : Number(e.target.value) })} />
          </label>
          <label>Số host được quét sâu
            <input type="number" min={1} max={200} aria-label="Số host quét sâu" placeholder="mặc định" value={config.deep_hosts ?? ""}
              onChange={(e) => onChange({ deep_hosts: e.target.value === "" ? null : Number(e.target.value) })} />
            <small>Host đang sống được chọn từ kết quả probe</small>
          </label>
        </div>
      </Panel>

      <Panel id="ed-nuclei" title="Nuclei" hint="Chọn mức nghiêm trọng của mẫu kiểm tra. Mức cao ít nhiễu hơn; mức thấp tìm nhiều hơn nhưng lâu hơn.">
        <div className="chips-row">
          {SEVERITY_LEVELS.map((s) => (
            <label className="check inline" key={s}>
              <input
                type="checkbox"
                checked={severities.has(s)}
                disabled={config.skip_nuclei}
                onChange={(e) => {
                  const next = new Set(severities);
                  e.target.checked ? next.add(s) : next.delete(s);
                  onChange({ nuclei_severity: SEVERITY_LEVELS.filter((l) => next.has(l)).join(",") });
                }}
              />
              {s}
            </label>
          ))}
        </div>
        <label className="check">
          <input type="checkbox" checked={!!config.nuclei_allow_intrusive} disabled={config.skip_nuclei}
            onChange={(e) => onChange({ nuclei_allow_intrusive: e.target.checked })} />
          Cho phép template có thẻ nguy hiểm (<code>dos</code>, <code>fuzz</code>, <code>intrusive</code>, <code>brute-force</code>). Mặc định tắt: chúng có thể làm sập dịch vụ hoặc đoán thông tin đăng nhập.
        </label>
        <label className="check">
          <input type="checkbox" checked={!!config.nuclei_auto_select} disabled={config.skip_nuclei}
            onChange={(e) => onChange({ nuclei_auto_select: e.target.checked })} />
          Tự chọn thêm template theo công nghệ phát hiện được (<code>-as</code>). nuclei tự dò công nghệ trên từng host rồi chạy thêm
          template khớp, ngoài severity/tag đã lọc ở trên. Sau khi scan xong, Run có file "template nuclei đã nạp" cho đúng lượt đó.
        </label>
        <TemplateLookup />
      </Panel>

      <Panel id="ed-data" title="Dữ liệu & brief" hint="Giới hạn lượng dữ liệu và chọn thứ gì được đưa vào AGENT_BRIEF.md.">
        <div className="three">
          <label>Số file JS tải tối đa
            <input type="number" min={0} max={100} value={config.max_js_files} disabled={config.skip_secrets} onChange={(e) => onChange({ max_js_files: Number(e.target.value) })} />
            <small>0–100 (bước "Bí mật trong JS")</small>
          </label>
          <label>Dung lượng brief
            <select value={config.brief_budget_kb} onChange={(e) => onChange({ brief_budget_kb: Number(e.target.value) })}>
              {[4, 8, 12].map((k) => <option key={k} value={k}>{k} KB{k === 12 ? " (tối đa)" : ""}</option>)}
            </select>
            <small>Nhỏ hơn = agent đọc nhanh hơn</small>
          </label>
          <label>Asset / URL trong brief
            <span className="inline-pair">
              <input type="number" aria-label="Số asset trong brief" min={5} max={50} value={config.brief_top_assets} onChange={(e) => onChange({ brief_top_assets: Number(e.target.value) })} />
              <input type="number" aria-label="Số URL trong brief" min={0} max={30} value={config.brief_top_urls} onChange={(e) => onChange({ brief_top_urls: Number(e.target.value) })} />
            </span>
            <small>5–50 asset · 0–30 URL</small>
          </label>
        </div>
        <label>Đường dẫn KHÔNG đưa vào kết quả (mỗi dòng một mẫu, vd <code>/internal/*</code>)
          <textarea
            rows={3}
            value={patterns}
            placeholder={"/internal/*\n/admin/*"}
            onChange={(e) => {
              setPatterns(e.target.value);
              onChange({ url_exclude_patterns: e.target.value.split("\n").map((l) => l.trim()).filter(Boolean) });
            }}
          />
          <small>Dùng cho các đường dẫn program yêu cầu không kiểm thử. Chỉ lọc kết quả hiển thị/brief; không ngăn công cụ truy cập.</small>
        </label>
      </Panel>

      </details>
      {scopeFields}
    </div>
  );
}
