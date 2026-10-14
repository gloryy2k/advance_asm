# Đánh giá sản phẩm BBASM v1.1 — chức năng và UI/UX

Ngày 2026-10-14. Đánh giá trên nhánh `test/v11-host-results` tại `913c88e`, kết hợp kết quả trong [V11_HOST_RESULTS.md](V11_HOST_RESULTS.md), [V11_FOLLOWUP_NOTES.md](V11_FOLLOWUP_NOTES.md), mã frontend/backend và quan sát Playwright headless trên Docker QA ở 1366px/390px. Đây là đề xuất cho vòng phát triển tiếp theo, không phải thay đổi code sản phẩm. Ảnh chụp QA nằm ngoài repo, không commit.

## Nhận định

V1.1 có nền tảng tốt: resolve và review scope trước khi chạy; scope gate IN/OUT; ba mức scan; audit, persistence, cancel, scheduler, export; brief và workspace cho agent. Các luồng cốt lõi đã chạy được trên Docker. Tuy nhiên, kết quả recon chưa chuyển thành thông tin đủ hữu ích cho người dùng và UI chưa cho thấy rõ độ tin cậy của dữ liệu. Full Light chưa được nghiệm thu an toàn trên target thực vì một số bước không tuân giới hạn tốc độ đã chọn. Không suy diễn `0 findings` thành target an toàn.

## Backlog ưu tiên

| Mức | Vấn đề / bằng chứng | Đề xuất và tiêu chí nghiệm thu |
| --- | --- | --- |
| **P1** | `katana` chạy với `-c 50 -p 20` dù scan đặt `threads=1`, `rate_limit=1`; JS monitor tải tối đa 100 bundle bằng `curl` không có rate limiter. Xem scan #10/#11 trong `V11_FOLLOWUP_NOTES.md`. | Áp giới hạn tốc độ chung cho mọi bước gửi request hoặc cho phép tắt từng monitor trong Review. Integration test dùng HTTP fixture localhost để đo giới hạn thực tế với `rate_limit=1`; kiểm argv katana và cancel khi monitor đang chạy. UI chỉ hứa giới hạn toàn scan khi test chứng minh được. |
| **P1** | H1 Verisk không có API credentials dùng `public_dump`: có hai wildcard IN nhưng thiếu policy đầy đủ, scope chưa được đối chiếu nguồn chính thức. | Review và Program hiện nhãn **chưa xác minh** cùng nguồn, thời điểm lấy, mục còn thiếu và đường dẫn đối chiếu. Active chỉ được đề xuất khi policy/scope đã được xác minh và người dùng xác nhận. Thêm test cho public dump thiếu policy và API H1 trả policy/structured scope. |
| **P1** | Passive #9 có 8836 URL lịch sử nhưng UI/Brief gần như chỉ hiện một host và số đếm. | Thêm danh sách URL/endpoint **đã qua scope gate**, phân trang và lọc theo host, API, JS, tham số, đường dẫn nhạy cảm, nguồn và trạng thái xác minh. Hiện số raw / hợp lệ / ngoài scope / trùng. Brief chọn tối đa N tín hiệu đáng xem, nêu lý do và liên kết tới artifact, giữ dưới 12 KB. URL lịch sử không được gắn nhãn live/finding. |
| **P2** | Passive #9 `status_code=null`, Light #12 `status_code=200` và có tech, nhưng `/diff?scan_id=12` trả tổng 0; giữa hai lần có scan bị hủy. | Test riêng chuỗi Passive → Light, và chuỗi có scan hủy xen giữa. Diff phải so với scan hoàn tất hợp lệ trước đó, thể hiện thay đổi status/tech hoặc giải thích rõ vì sao không tính. |
| **P2** | Export `include_recon=true` có thể chứa URL raw ngoài scope; lệnh hunt Windows native bị escape dấu `\` hai lần (xem `V11_HOST_RESULTS.md`). | Cho chọn export recon đã lọc scope hoặc cảnh báo rõ phạm vi raw; kiểm ZIP không âm thầm trình bày dữ liệu ngoài scope như dữ liệu hợp lệ. Sửa quote đường dẫn hunt theo shell đích và kiểm clipboard trên Windows/WSL2. |

## UI/UX: cấu trúc hiện tại và đề xuất

### Vì sao đang rối

- Trang Program có bảy tab ngang: **Overview, Surface, Assets, Diff, Findings, Brief, Program** (`frontend/src/lib/router.ts`, `frontend/src/pages/Program.tsx`). Surface là một tập xếp hạng trong Assets nhưng được đặt ngang hàng; tab Program thực chất là tài liệu/hướng dẫn. Ở 390px, các tab sau Diff nằm ngoài vùng nhìn mà không có dấu hiệu rõ về nội dung còn lại. Không có tràn ngang toàn trang, nhưng điều đó không bảo đảm tab dễ tìm.
- Overview đặt thẻ “Sẵn sàng hunt” lớn trước kết quả, rồi trộn chỉ số, surface, findings, lịch scan và cấu hình giám sát. Người dùng khó thấy ngay **cái gì mới, bằng chứng nào đáng xem, cần làm gì tiếp**.
- Review lặp cảnh báo policy ở đầu và trong PolicyPanel. Trang dài khoảng 2600px ở 390px; khối xác nhận/Launch nằm cuối. Khi nhiều asset hoặc policy dài, khoảng cách còn tăng. Xem finding F2 trong `V11_HOST_RESULTS.md`.
- Run liệt kê nhiều pha bằng dấu ✓ và log kỹ thuật; cần phân biệt “đã chạy”, “bị bỏ qua”, “lỗi”, “không có dữ liệu”. Brief hiển thị Markdown raw, bảng/tech dài khó đọc trên điện thoại.
- Tên tiếng Anh/Việt lẫn nhau (`Portfolio`, `Review`, `Launch`, `Surface`, `Program`, `Giám sát liên tục`). Người mới phải tự suy ra mối quan hệ giữa program, scan, asset, URL, finding và workspace.

### Cấu trúc thông tin đề xuất

| Khu vực | Nội dung chính |
| --- | --- |
| **Tổng quan** | Trạng thái scan, độ tin cậy scope/policy, 3 thay đổi quan trọng, 3 việc tiếp theo, liên kết chứng cứ. Lệnh hunt thu gọn thành hành động phụ. |
| **Dữ liệu** | Assets, URL/endpoint và xếp hạng surface trong một khu vực có lọc/tìm kiếm. Gắn nguồn và mức xác minh cho từng mục. |
| **Phát hiện** | Findings với severity, bằng chứng, trạng thái xác minh và scan nguồn. Empty state giải thích scan nào đã/chưa chạy. |
| **Lịch sử** | Danh sách scan, Diff, các bước lỗi/bỏ qua và mốc so sánh. |
| **Scope & hướng dẫn** | IN/OUT, policy, nguồn H1, hướng dẫn agent, Brief, Export và lệnh hunt. Lịch giám sát đặt trong phần cấu hình riêng. |

Giữ luồng **Nhập scope → Review → Run**, nhưng dùng Review như một trang quyết định ngắn: nguồn scope và độ tin cậy; mức scan và tác động; số IN/OUT; giới hạn request thực tế; xác nhận. Chi tiết từng asset và tùy chọn nâng cao mở khi cần. Trên mobile, thanh hành động cố định dẫn tới xác nhận/Launch và hiện lý do khi bị khóa. Gộp cảnh báo policy lặp thành một thông điệp có hành động cụ thể. Đây là áp dụng nguyên tắc progressive disclosure cho giao diện nhiều tùy chọn, không phải ẩn thông tin an toàn.

## Cải thiện chức năng chính sau khi sửa P1

1. **Kết quả có thể hành động:** URL inventory đã lọc scope, top endpoint có lý do ưu tiên, liên kết đến raw evidence. Phân biệt `historical`, `observed`, `live`, `finding` trong API và UI.
2. **Nguồn và độ tin cậy:** mỗi scope/asset/URL/policy có provenance và thời điểm thu thập. H1 public dump thiếu policy phải có trạng thái chưa xác minh xuyên suốt Review → Program → Brief.
3. **Diff đáng tin:** baseline là scan hoàn tất hợp lệ; thay đổi status, tech, URL và finding có giải thích. Không coi asset biến mất do scan partial/cancel là `gone`.
4. **Báo cáo scan trung thực:** cho từng pha hiện chạy/bỏ qua/lỗi, cấu hình và giới hạn đã áp, số kết quả sau lọc scope; Brief không cắt giữa JSON/Markdown table.
5. **Khả năng sử dụng:** định nghĩa ngắn cho Passive/Light/Strong và tác động thực tế; chọn một bộ thuật ngữ UI thống nhất; kiểm 320–390px, bàn phím, tương phản và dữ liệu >1000 dòng.

## Thứ tự triển khai gợi ý

1. **An toàn và độ đúng:** rate limit toàn pipeline, độ tin cậy H1, Diff baseline. Đây là điều kiện trước khi quảng bá full Light/Strong.
2. **Giá trị của recon:** URL/endpoint inventory trong scope, Brief có lựa chọn và provenance, export rõ raw/filtered.
3. **Tái cấu trúc UI:** nhóm điều hướng, rút gọn Review và Overview, mobile CTA, trạng thái pha scan và Brief dễ đọc.
4. **Kiểm nghiệm UX:** thử tác vụ “thêm program → review → chạy → tìm tín hiệu → bắt đầu hunt” với người mới và người quen bug bounty; đo khả năng hoàn thành, nhầm lẫn giữa Surface/Assets và khả năng tìm Diff/Policy trên mobile. Kiểm accessibility theo WCAG 2.2, đặc biệt reflow và trạng thái được công bố cho công nghệ hỗ trợ.

Không ưu tiên thêm tool quét mới lúc này. Trước tiên cần bảo đảm active scan tuân giới hạn, rồi trình bày dữ liệu đã thu được thành tín hiệu rõ, có nguồn và có thể kiểm chứng.
