import { useData } from "../hooks/useData";
import { PageHead, Panel, Chip } from "../components/layout";
import { State } from "../components/ui";
import { PRESETS } from "../lib/presets";

type Cat = { key: string; title: string; what: string; touches: boolean; tools: string[]; count_label: string; view: { kind: string; label: string } };
const WHERE: Record<string, string> = { hosts: "Dữ liệu › Host", urls: "Dữ liệu › URL & endpoint", findings: "Phát hiện", file: "Trang scan › “Kết quả theo bước” › đọc file" };

const OTHER = [
  ["Brief (AGENT_BRIEF.md)", "Tóm tắt một trang để agent bắt đầu hunt: scope, số liệu, host/URL đáng xem, gợi ý test. Sinh lại sau mỗi scan hoàn tất.", "Hướng dẫn & scope › Brief"],
  ["Hướng dẫn cho agent (PROGRAM.md)", "Luật chơi bền của program: policy, scope, ghi chú của bạn. Không bị ghi đè khi scan lại.", "Hướng dẫn & scope › Hướng dẫn cho agent"],
  ["So sánh thay đổi (Diff)", "So scan hoàn tất mới nhất với scan hoàn tất trước đó: host mới, host đổi (trạng thái/tech), host biến mất.", "Lịch sử › So sánh thay đổi"],
  ["Xếp hạng bề mặt", "Chấm điểm host theo tín hiệu (API, đăng nhập, tech rủi ro, mới, nuclei) để biết nên xem gì trước.", "Dữ liệu › Xếp hạng, và Top 5 ở Tổng quan"],
  ["Giám sát liên tục", "Tự quét lại theo lịch (6 giờ/ngày/tuần) với scope hiện hành, không qua xem lại từng lần. Chỉ dùng khi program cho phép.", "Tổng quan › Giám sát liên tục; kết quả trong Lịch sử"],
  ["Profile quét", "Lưu cách quét của bạn (tốc độ, bước nào bật, giới hạn dữ liệu…) để dùng lại. Không lưu scope.", "Profile quét (menu trái) · Xem lại › Mức quét"],
  ["Xuất ZIP", "Đóng gói thư mục program để mang đi: chỉ brief, đã lọc scope (khuyến nghị) hoặc recon thô.", "Hướng dẫn & scope › Xuất ZIP"],
];

export function Help() {
  const phases = useData<Cat[]>("/api/meta/phases");
  return (
    <>
      <PageHead eyebrow="TRỢ GIÚP" title="Chức năng & kết quả" sub="Mỗi chức năng làm gì, có gửi request tới target không, và xem kết quả ở đâu." />
      <Panel id="flow-h" title="Quy trình 3 bước">
        <ol className="plain steps3">
          <li><strong>1. Thêm program</strong> — nhập scope HackerOne hoặc dán scope thô. Chưa quét gì.</li>
          <li><strong>2. Xem lại</strong> — đọc policy, kiểm scope, chọn mức quét và các bước. Xác nhận rồi mới chạy.</li>
          <li><strong>3. Kết quả</strong> — xem từng bước đã làm gì; mở dữ liệu; chép lệnh <code>cd … &amp;&amp; claude</code> để hunt.</li>
        </ol>
      </Panel>
      <Panel id="phases-h" title="Các bước quét" hint="Đây là những gì một scan có thể làm. Mỗi scan cho biết từng bước đã chạy, bỏ qua (và vì sao) hay không có dữ liệu.">
        <State data={phases.data} error={phases.error}>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Bước</th><th>Làm gì</th><th>Request tới target?</th><th>Công cụ</th><th>Xem kết quả ở</th></tr></thead>
              <tbody>
                {phases.data?.map((p) => (
                  <tr key={p.key}>
                    <td><strong>{p.title}</strong></td>
                    <td>{p.what}</td>
                    <td><Chip tone={p.touches ? "touch" : "quiet"}>{p.touches ? "Có" : "Không"}</Chip></td>
                    <td>{p.tools.join(", ") || "—"}</td>
                    <td>{WHERE[p.view.kind] || p.view.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </State>
      </Panel>
      <Panel id="presets-h" title="Mức quét" hint="Preset chỉ là điểm xuất phát. Bạn chỉnh từng bước và từng giá trị ở màn Xem lại, và lưu thành profile.">
        <div className="cards3">
          {PRESETS.map((p) => (
            <div className="panel" key={p.depth}><h3>{p.title}</h3><p className="hint">{p.tagline}</p><p>{p.detail}</p><p className="muted">{p.touches ? "Có gửi request" : "Không gửi request"} · {p.eta}</p></div>
          ))}
        </div>
      </Panel>
      <Panel id="other-h" title="Các chức năng khác">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Chức năng</th><th>Làm gì</th><th>Xem ở</th></tr></thead>
            <tbody>{OTHER.map(([a, b, c]) => <tr key={a}><td><strong>{a}</strong></td><td>{b}</td><td>{c}</td></tr>)}</tbody>
          </table>
        </div>
      </Panel>
      <Panel id="terms-h" title="Từ cần biết">
        <dl className="terms">
          <dt>Lịch sử</dt><dd>URL lấy từ archive (gau, Wayback): từng tồn tại, chưa chắc còn chạy.</dd>
          <dt>Đã crawl thấy</dt><dd>URL do katana tìm được trên host đang chạy: mạnh hơn “lịch sử”.</dd>
          <dt>Ngoài scope</dt><dd>URL/host không thuộc scope IN; luôn bị loại khỏi kết quả và không dùng để quét.</dd>
          <dt>Chạm target</dt><dd>Bước gửi request tới target. Bước “không chạm” chỉ dùng nguồn công khai.</dd>
          <dt>0 kết quả</dt><dd>Bước đã chạy nhưng không tìm thấy gì. Không có nghĩa target an toàn.</dd>
        </dl>
      </Panel>
    </>
  );
}
