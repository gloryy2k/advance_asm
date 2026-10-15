# Đề xuất sau host QA c11440d

Ngày 2026-10-16. Tài liệu để Claude đánh giá trên nhánh nguồn `claude/upbeat-thompson-b7bb23`; không thay đổi code sản phẩm. Bằng chứng kiểm thử nằm trong `V134_HOST_RESULTS.md` của nhánh `test/v134-host-results`.

## Hiện trạng đã xác nhận

- Container có binary Nuclei v3.11.1 nhưng có 0 template YAML. `/api/health` trả `tools.nuclei=true`, `tools["nuclei-templates"]=false`; Light/Strong báo thiếu template và bỏ qua bước Nuclei. Stack QA đặt `BBASM_UPDATE_TEMPLATES=0`. `docker-compose.yml` hiện chỉ mount `data/` và `targets/`, chưa có volume bền vững cho templates.
- `Portfolio.tsx` chỉ hiển thị các badge boolean của `/api/health`. Review và Run báo công cụ thiếu ở vị trí khác nhau. `bbscope` là optional nhưng vẫn nhận nhãn đỏ “thiếu”, dễ hiểu thành lỗi scan.
- Stack QA có 27 draft và 15 program hiển thị tại thời điểm kiểm tra; 15 draft `qa-v134-ui` là dữ liệu QA do Codex tạo khi chụp ảnh. Trong 15 program hiển thị có 13 tên `qa-*`, cùng `wolt` và `127.0.0.1`. Không xóa dữ liệu trong vòng này; draft #57 đang được người dùng xem.
- Giao diện/API cho xóa draft (`DELETE /api/scans/{id}`), chỉ chấp nhận status `draft`. API chưa có xóa hoặc archive program đã chạy. Xóa draft cuối của program chưa từng chạy và không có schedule thì record program cũng bị xóa.
- Finding P2 riêng: Review không khôi phục checkbox bỏ qua policy header từ `config.skip_required_headers=true` đã lưu. Chi tiết tái hiện trong `V134_HOST_RESULTS.md`.

## P1 — Trang “Công cụ & môi trường”

Thêm mục điều hướng riêng. Đây là trạng thái môi trường toàn cục; Profile quét vẫn quản lý lựa chọn của từng scan. Dùng chung một nguồn trạng thái cho trang này, Portfolio, Review và Run.

Đề xuất API chỉ đọc cho mỗi công cụ: `id`, vai trò/bước sử dụng, trạng thái phân biệt `ready`, `missing_binary`, `missing_data`, `error`, `optional`, lý do, phiên bản (nếu lấy được với giới hạn thời gian), ảnh hưởng đến Passive/Light/Strong và cách khắc phục. Không biến health check thường xuyên thành thao tác chạy tool hoặc truy cập target. Tách kiểm tra sâu/phiên bản ra một tác vụ được gọi chủ động nếu cần.

Review phải nói rõ “Nuclei đã cài; thiếu templates; bước Nuclei sẽ bỏ qua” và dẫn tới trang Công cụ. `bbscope` phải có nhãn “tùy chọn”, không trông như blocker. Không hứa toàn bộ Light/Strong chạy đủ khi chỉ một phần step khả dụng.

**Chấp nhận:** trạng thái trên ba màn hình nhất quán với `/api/health`; Nuclei binary có nhưng 0 template được mô tả đúng; tool tùy chọn không bị tính là thiếu cho depth; mỗi step bị bỏ qua nêu rõ công cụ/dữ liệu còn thiếu.

## P1 — Cài/cập nhật Nuclei templates có chủ đích

Dùng bộ `projectdiscovery/nuclei-templates` làm nguồn mặc định. Thêm nút “Cài/Cập nhật templates” trong trang Công cụ; Review chỉ có liên kết tới đó. Tác vụ chạy ngoài scan, có khóa để tránh hai lần update đồng thời, giới hạn thời gian, tiến độ/trạng thái, kết quả gồm số template hợp lệ, lần cập nhật và lỗi. Không tự tải template giữa scan; giữ hành vi skip và log rõ khi chưa có template. Không cho UI nhập URL/lệnh shell tùy ý.

Lưu template trong volume/bind mount bền vững, kiểm tra qua `docker compose up --force-recreate` rằng template còn và `/api/health` chuyển từ false sang true. Xác định rõ quan hệ giữa nút cập nhật và `BBASM_UPDATE_TEMPLATES` lúc boot để tránh tải hai lần hoặc UI báo sai. Sau update phải làm mới trạng thái Review/plan mà không buộc tạo draft mới.

**Chấp nhận:** bắt đầu với 0 template → UI báo thiếu; cập nhật thành công → count >0, health true, Review Nuclei sẵn sàng; tạo lại container → count và health giữ nguyên; update thất bại/timeout → giữ bộ template trước, có thông báo rõ; không có request tới target trong tác vụ update.

## P2 — Import template riêng sau khi luồng mặc định ổn định

Phù hợp cho template nội bộ hoặc theo program, chưa cần cho bản sửa đầu tiên. Cho import YAML/thư mục hoặc gói nén vào vùng `custom/` riêng, kiểm tra cấu trúc, đường dẫn, kích thước, template ID trùng và tính hợp lệ trước khi kích hoạt. Hiển thị nguồn và khả năng bật/tắt; không mặc định đưa toàn bộ template mới vào mọi scan. Đánh giá các protocol có khả năng thực hiện thao tác mạnh (code/JavaScript/headless) và chính sách ký template của phiên bản Nuclei đang dùng.

**Chấp nhận:** template lỗi/trùng/đường dẫn traversal bị từ chối; import không chạy scan; chỉ template được chọn mới tham gia plan; xóa custom không xóa bộ chính thức; có thể kiểm tra chính xác bộ template nào đã dùng cho một scan.

## P1/P2 — Dọn danh mục và vòng đời program

1. **P1: dọn draft.** Có lọc/sắp xếp draft theo tuổi, nguồn, slug; hỗ trợ chọn nhiều và xem danh sách chính xác trước khi xóa. Giữ quy tắc chỉ xóa `draft`; không chọn tự động các draft thật của người dùng. Các draft `qa-v134-ui` (#44–#58) là ứng viên dọn khi người dùng đã xem xong, bao gồm #57 đang mở.
2. **P1: archive program.** Ẩn khỏi Danh mục mặc định nhưng giữ scan, Diff, findings, export và file; có bộ lọc “Đã lưu trữ” và thao tác khôi phục. Khi archive program đang có schedule, yêu cầu quyết định rõ về schedule; không để scan nền tiếp tục một cách khó thấy.
3. **P2: xóa vĩnh viễn program.** Chỉ sau khi có archive. Màn hình xác nhận hiển thị số scan, schedule, finding và thư mục `targets/<slug>` sẽ bị ảnh hưởng; cân nhắc cho export/backup trước khi xóa. Chặn xóa khi scan đang chạy, xử lý quan hệ DB và file theo trình tự có thể phục hồi nếu bước file lỗi. Không hướng dẫn người dùng xóa thủ công DB hoặc `targets/`.

**Chấp nhận:** archive/restore không đổi lịch sử và Diff; chỉ program active xuất hiện mặc định; xóa draft không ảnh hưởng program đã scan; xóa vĩnh viễn đúng một program, không ảnh hưởng program khác; lỗi giữa chừng không để UI và DB/file ở trạng thái mâu thuẫn.

## P2 — Đồng bộ xác nhận header trên Review

Chọn một nghĩa rõ ràng cho `skip_required_headers`: hoặc là trạng thái draft được lưu và checkbox phải khôi phục khi mở lại, hoặc là xác nhận chỉ cho lần Launch và không lưu vào config. Cùng một nghĩa phải được dùng ở API, UI và audit. Đừng để `skip_required_headers=true` trong config nhưng Review vẫn hiển thị chưa xác nhận.

**Chấp nhận:** lưu draft, tải lại trang, xem đúng trạng thái; đổi giữa Passive/Light/Strong không tạo hiểu lầm; API vẫn từ chối Light/Strong thiếu header và thiếu xác nhận, còn Passive không bị gate header.

## Thứ tự đề xuất

1. Thống nhất mô hình trạng thái công cụ và sửa câu chữ Review; làm trang Công cụ.
2. Tạo volume template và tác vụ cập nhật Nuclei; kiểm tra qua recreate Docker.
3. Dọn draft và thêm archive/restore để giảm nhiễu Danh mục.
4. Sửa trạng thái xác nhận header; thêm import template và xóa vĩnh viễn khi thiết kế vòng đời đã rõ.

Claude cần kiểm tra lại ưu tiên, phạm vi API và rủi ro migration trước khi triển khai. Không cần chạy Wolt hoặc H1 thật để đánh giá các đề xuất này.
