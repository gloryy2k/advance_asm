# QA-1 — các thay đổi sau scan selector

Nguồn QA: `claude/upbeat-thompson-b7bb23` tại `c596bc9` (18/10/2026). `COORD_TASKS.md`: QA-1 `READY_FOR_QA`, base `58c5c3f`, result `2ea7e19`; cả hai là tổ tiên của HEAD. Submodule `vendor/claude-bug-bounty` tại `ccae299`. Nhánh kết quả `test/v170-host-audit`. Chỉ dùng fixture, container không mạng và localhost; không chạy scan target, không đụng stack `bbasm-v12` hay DB người dùng. Không QA lại lõi scan selector đã PASS.

**Kết luận: QA-1 FAIL một phần.** Endpoint và phần Findings đúng; thay đổi mặc định Strong sang 7.200 giây xung đột với `.env.example` vẫn đặt trần 2.700 giây. Khi `.env` được tạo từ file mẫu, preset Strong mới bị backend từ chối.

| Commit / mã | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| `941f112` / QA-1.1 | Overview khi xem scan cũ; TECH thu/mở; chi tiết Findings wrap; CSS spinner/scroll shadow | PASS logic, CSS chưa kiểm ảnh pixel | Test QA riêng xác nhận Overview phân biệt scan #1 với inventory hiện hành; TECH hiện 3 badge + `+2 nữa`, mở/thu đúng. `.detailcell` giới hạn 420px/wrap. Vitest/tsc/build đều xanh. |
| `895381e` / QA-1.2 | Dải severity Findings không click-to-filter | PASS | Test QA riêng: dải có `1 critical`, `2 medium`, ghi rõ “toàn bộ program, mọi lần scan”, **0 button**; bộ lọc select riêng vẫn gửi `severity=critical`. |
| `73015ba` / QA-1.3 | `GET /api/meta/tool-defaults` phản ánh Settings thật, UI hiển thị số mặc định | PASS | TestClient: HTTP 200; mặc định `900/300/3600/50`, override `111/222/333/44` trả đúng. Vitest hiện placeholder và ghi chú tương ứng; config không bị điền giá trị khi để trống. |
| `9dac165` / QA-1.4 | Tài liệu v1.6.10 và backlog | PASS đọc tài liệu | `NOTES.md` ghi dải severity là thống kê toàn program; `BACKLOG.md` ghi riêng các vấn đề recon chưa sửa, không lẫn trạng thái PASS của QA-1. |
| `2ea7e19` / QA-1.5 | Mặc định Strong 7.200 giây trên code/frontend | **FAIL — P1** | `Settings()` mặc định = 7200, preset frontend = 7200, nhưng `.env.example` dòng 55 còn `BBASM_SCAN_TIMEOUT_STRONG=2700`; `_validate` từ chối preset với `scan_timeout exceeds configured depth hard limit`. |

## Finding QA-1/F1 — preset Strong không launch được với `.env` tạo từ mẫu (P1)

**Cách tái hiện an toàn:** đọc `.env.example`, lấy `BBASM_SCAN_TIMEOUT_STRONG=2700`; khởi tạo Settings tạm với giá trị này; đưa cấu hình preset Strong `scan_timeout=7200` qua `JobRunner._validate`. Kết quả là `ScopeError: scan_timeout exceeds configured depth hard limit` (`review_evidence/qa1_probe_output.txt`). Trong triển khai Docker, `docker-compose.yml` nạp `.env`; nếu `.env` sao từ file mẫu, giới hạn 2.700 này sẽ ghi đè giá trị mặc định 7.200 ở `backend/config.py`. Không đọc hay thay đổi `.env` hiện có của người dùng, nên **không khẳng định stack của họ đang gặp lỗi**.

**Tác động:** Người dùng chọn preset Strong mới thấy 2 giờ trên Review nhưng lưu config hoặc Launch có thể nhận 422 khi server giữ trần 45 phút. Đây là lỗi tích hợp code + cấu hình đóng gói, không phải lỗi test `test_safe_defaults` (test đó loại `.env`).

**Hướng sửa:** cập nhật `.env.example` lên 7.200; đồng thời xử lý `.env` đã tồn tại bằng cách cho UI đọc cả hard cap thực từ server (hoặc hiện lỗi rõ kèm giá trị trần và cách đổi `.env`). Test thêm Settings nạp file mẫu và luồng Review/Launch với hard cap thấp hơn preset. Không tự sửa trong nhánh QA.

## Lệnh và phạm vi kiểm chứng

- Backend Linux trong container tạm `--network none`, mount source chỉ đọc: `python -m pytest -q -p no:cacheprovider ... test_tool_defaults_endpoint_reflects_the_running_server_settings test_safe_defaults test_diff_rejects_a_draft_or_foreign_scan_id` → **3 passed**. Test `/diff` chỉ là hồi quy nhẹ, không QA lại scan selector.
- `python -m review_evidence.qa1_probe` trong container tạm → 2 response HTTP 200 đúng số mặc định/override; Strong cap mismatch tái hiện. Script và output kèm trong `review_evidence/`.
- Frontend: `npm ci` → OK; `npm test` trên source gốc → **96 passed**; sau thêm 3 test QA trong `frontend/src/qa1_host.test.tsx` → **99 passed**; `npx tsc --noEmit` → 0 lỗi; `npm run build` → OK (có cảnh báo bundle >500 kB, không liên quan các commit QA-1).
- Native Windows: test có TestClient bị treo khi chạy từ host sandbox, đã dừng; cùng test chạy xong trong Linux container. Chưa chụp ảnh CSS/đo scroll shadow trên browser thật, nên PASS của `941f112` chỉ cho logic/compile, không xác nhận chất lượng thị giác pixel.
