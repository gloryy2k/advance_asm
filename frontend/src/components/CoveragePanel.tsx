import type { AssetCoverage, Config } from "../api/types";
import { Chip, Panel } from "./layout";

export type ApexInfo = { apex: string; wildcard: string; status: "not_in_scope" | "in_scope_explicit" | "added_by_you" | "blocked_by_out"; dropped_urls: number; selected: boolean; confirmed: boolean };
export type CoverageData = {
  assets: AssetCoverage[];
  summary: Record<string, number>;
  apex: ApexInfo[];
  stage_shares: { key: string; until: number; seconds: number }[];
  path_rules: { hosts: Record<string, string[]>; enforcement: { tool: string; how: string; stops_request: boolean }[]; active_allowed: boolean };
};

const MODE_TONE: Record<string, string> = { recon: "good", recon_host: "warn", secrets_only: "touch", passive_only: "quiet", manual: "muted", manual_confirm: "bad", off: "muted" };
const STAGE_NAME: Record<string, string> = { discovery: "Khám phá", main: "Host nêu trong scope", probe: "Probe host khám phá", deep: "Quét sâu" };

/** What BBASM will do with each asset of the scope, said before anything runs: Strong never means "everything was scanned". */
export function CoveragePanel({ data, config, edit }: { data: CoverageData | null; config: Config; edit: (patch: Partial<Config>) => void }) {
  if (!data) return null;
  const counts = data.summary;
  const auto = (counts.recon || 0) + (counts.recon_host || 0);
  const apexSelected = (config.include_apex || []).length > 0;
  const toggleApex = (apex: string, on: boolean) => {
    const next = on ? [...new Set([...(config.include_apex || []), apex])] : (config.include_apex || []).filter((a) => a !== apex);
    edit({ include_apex: next, apex_confirmed: next.length ? config.apex_confirmed : false });
  };
  const toggleRepo = (pattern: string, on: boolean) => {
    const list = config.source_full_repo_ok || [];
    edit({ source_full_repo_ok: on ? [...new Set([...list, pattern])] : list.filter((p) => p !== pattern) });
  };
  const hosts = Object.entries(data.path_rules.hosts);
  return (
    <Panel id="coverage-h" title="Độ phủ theo loại asset" hint="Mỗi mục trong scope được xử lý khác nhau. Đọc kỹ trước khi launch: chọn mức Strong không có nghĩa mọi asset đều được quét.">
      <p data-testid="coverage-summary">
        <strong>{auto}</strong> asset recon tự động
        {!!counts.secrets_only && <> · <strong>{counts.secrets_only}</strong> repo chỉ quét bí mật</>}
        {!!counts.passive_only && <> · <strong>{counts.passive_only}</strong> chỉ nguồn công khai</>}
        {!!(counts.manual || 0) && <> · <strong>{counts.manual}</strong> chỉ lưu để làm tay</>}
        {!!counts.manual_confirm && <> · <strong>{counts.manual_confirm}</strong> bị khóa chờ bạn xác nhận</>}
        {!!counts.off && <> · {counts.off} đã tắt</>}.
      </p>
      <ul className="coverage-list" aria-label="Độ phủ từng asset">
        {data.assets.map((a) => (
          <li key={a.pattern} data-mode={a.mode}>
            <div className="coverage-head"><code>{a.pattern}</code> <Chip tone={MODE_TONE[a.mode]}>{a.label}</Chip></div>
            <p className="muted">{a.detail}</p>
            {a.instruction && a.mode !== "manual" && <p className="step-detail"><strong>Hướng dẫn của program:</strong> {a.instruction}</p>}
            {a.mode === "manual_confirm" && (
              <label className="check">
                <input type="checkbox" aria-label={"Cho phép quét cả repo " + a.pattern} checked={(config.source_full_repo_ok || []).includes(a.pattern)} onChange={(e) => toggleRepo(a.pattern, e.target.checked)} />
                Tôi đã đọc hướng dẫn của program và cho phép quét toàn bộ repo này (cả lịch sử git).
              </label>
            )}
            {a.mode === "secrets_only" && (config.source_full_repo_ok || []).includes(a.pattern) && (
              <label className="check">
                <input type="checkbox" checked onChange={(e) => toggleRepo(a.pattern, e.target.checked)} aria-label={"Cho phép quét cả repo " + a.pattern} />
                Đã xác nhận quét cả repo (bỏ chọn để trả về làm tay).
              </label>
            )}
          </li>
        ))}
      </ul>

      {data.apex.length > 0 && (
        <div className="apex" data-testid="apex">
          <h3 className="subhead">Wildcard và domain gốc</h3>
          {data.apex.map((x) => (
            <div key={x.apex} className="apex-row">
              <p>
                <code>{x.wildcard}</code> chỉ gồm <strong>subdomain</strong>; domain gốc <code>{x.apex}</code>{" "}
                {x.status === "not_in_scope" && <>đang <strong>ngoài scope</strong>{x.dropped_urls > 0 && <> ({x.dropped_urls.toLocaleString("vi-VN")} URL của nó ở scan trước đã bị loại)</>}.</>}
                {x.status === "in_scope_explicit" && <>đã nằm trong scope như một asset riêng.</>}
                {x.status === "added_by_you" && <>được <strong>thêm theo lựa chọn của bạn</strong> ở scan này.</>}
                {x.status === "blocked_by_out" && <>bị một mục OUT chặn; không thể thêm.</>}
              </p>
              {x.status !== "in_scope_explicit" && x.status !== "blocked_by_out" && (
                <>
                  <label className="check">
                    <input type="checkbox" aria-label={"Thêm domain gốc " + x.apex} checked={config.include_apex?.includes(x.apex) || false} onChange={(e) => toggleApex(x.apex, e.target.checked)} />
                    Thêm <code>{x.apex}</code> vào scope của lần quét này (HackerOne không nói rõ <code>*.domain</code> có gồm domain gốc; BBASM không tự mở rộng).
                  </label>
                  {config.include_apex?.includes(x.apex) && (
                    <p className="muted">Sẽ thêm vào IN: <code>{x.apex}</code> (web). Các mục OUT vẫn thắng. BBASM sẽ gửi request tới <code>{x.apex}</code> như một host nêu trong scope.</p>
                  )}
                </>
              )}
            </div>
          ))}
          {apexSelected && (
            <label className="check"><input type="checkbox" aria-label="Xác nhận policy cho phép domain gốc" checked={!!config.apex_confirmed} onChange={(e) => edit({ apex_confirmed: e.target.checked })} />
              Tôi đã đối chiếu policy chính thức của program và domain gốc được phép kiểm thử.</label>
          )}
        </div>
      )}

      {hosts.length > 0 && (
        <details className="adv" data-testid="path-enforcement">
          <summary>OUT theo đường dẫn: mỗi công cụ cưỡng chế đến đâu ({hosts.length} host)</summary>
          <table className="stages"><thead><tr><th>Công cụ</th><th>Cách xử lý</th><th>Chặn request tới đường dẫn OUT?</th></tr></thead>
            <tbody>{data.path_rules.enforcement.map((t) => <tr key={t.tool}><td>{t.tool}</td><td>{t.how}</td><td>{t.stops_request ? "Có" : "Không"}</td></tr>)}</tbody></table>
        </details>
      )}

      <details className="adv" data-testid="budget-preview">
        <summary>Ngân sách thời gian của scan ({Math.round(config.scan_timeout / 60)} phút)</summary>
        <p className="muted">Mỗi giai đoạn có trần theo phần trăm tổng thời gian; thời gian không dùng hết được chuyển sang giai đoạn sau. Mỗi lệnh trong một giai đoạn cũng bị giới hạn theo phần còn lại, nên một đợt chậm không làm mất các đợt sau.</p>
        <ul>{data.stage_shares.map((s, i) => <li key={s.key}>{STAGE_NAME[s.key] || s.key}: xong trước {Math.round(s.until * 100)}% ({s.seconds}s){i === 0 ? "" : ""}</li>)}</ul>
      </details>
    </Panel>
  );
}
