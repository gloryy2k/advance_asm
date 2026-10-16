# Kiểm thử F1–F3 trên `e2bd684`

Ngày kiểm thử: 2026-10-16. Nhánh QA: `test/e2bd684-host-check`. Chỉ dùng fixture và loopback (`127.0.0.1`, `127.0.0.2`); không gọi HackerOne, Wolt hoặc scan host ngoài. Stack QA dùng DB/targets riêng và mạng Docker `--internal`; stack `bbasm-v12` của người dùng không bị thay đổi.

| Mã | Hành động | Kết quả | Bằng chứng ngắn |
| --- | --- | --- | --- |
| Chuẩn bị | Fetch nguồn, tạo worktree từ `e2bd684`; chạy `pytest backend/tests/test_v137_scope_selection.py` trong Linux image; `npm ci --offline && npm run build` | PASS | HEAD `e2bd684`; 5 unit passed; frontend build thành công. |
| F1 | Resolve raw `a.example.com`, `b.example.com`; loại `b.example.com` và `https://a.example.com/admin`; launch Passive; Scan lại; bật lịch Passive và ép tick | PASS, có giới hạn | Config của draft #2 và scan lịch #3 đều giữ đúng 2 `excluded_hosts`; #3 `done`. Review hiển thị b bỏ chọn và textarea chứa cả 2 dòng. [Review](review_evidence/e2bd684/f1_review.png), [vùng scope](review_evidence/e2bd684/f1_scope.png). |
| F2 | Tải ZIP `mode=filtered` với recon chứa dòng 2 URL, URL OUT theo host/path, host/path không scheme, và nuclei JSONL | **FAIL** | URL thường: chỉ còn `/safe` và `/administrator`, đúng. JSONL thông thường và `\/` một tầng bị loại. JSONL với URL escape **hai tầng** vẫn còn trong ZIP dù giá trị giải mã là `https://a.example.com/admin/x`. |
| F3 | Program H1 giả có lịch Light; thay policy thành `public_dump`; ép tick | PASS | Không có `scan_run` mới (`COUNT=0`); schedule ghi `last_error` và thời điểm; Program hiện cảnh báo “đã bị bỏ qua”. [Ảnh desktop 1366px](review_evidence/e2bd684/f3_program.png). |

## Cách chạy và dữ liệu kiểm chứng

- Backend QA trên `127.0.0.1:18786`, DB và targets riêng tại `E:\code\bbasm\qa_e2bd684`. Hai hostname giả ánh xạ loopback trong container fixture. Script QA chạy các bước `f1_start`, `f1_check`, `f2`, `f3_setup`, `f3_check` qua API localhost; fixture ghi mọi request nhận được.
- F1: `POST /api/scope/resolve` → `PUT /api/scans/1/config` với `excluded_hosts=["b.example.com","https://a.example.com/admin"]` → `POST /launch` → `POST /api/programs/qa-f1/rescan` → `POST /schedule`. Sau khi đặt `next_run_at` về quá khứ và khởi động scheduler, scan lịch #3 hoàn tất, config vẫn có 2 loại trừ. Fixture không nhận request nào trong lúc Passive và tick lịch. Đây chỉ xác nhận tính **kế thừa cấu hình** và hành vi Passive; Passive vốn không gửi probe tới target, nên không chứng minh chặn đường dẫn ở Light/Strong.
- F2: file `qa-filter.txt` gồm các dòng URL IN/OUT cùng dòng, URL path OUT `/admin/users`, `a.example.com/admin [200]`, `b.example.com/private [200]`; ZIP chỉ giữ `https://a.example.com/safe` và `https://a.example.com/administrator`. File `qa-findings.jsonl` gồm 3 dạng URL OUT: thường, escape một tầng, escape hai tầng. Dạng thứ ba còn nguyên trong ZIP.
- F3: policy H1 là fixture cục bộ ghi trực tiếp vào DB QA; không lấy từ H1. `POST /api/programs/qa-h1-fake/schedule` bật Light, sau đó policy đổi thành `public_dump` và ép tick. API summary báo `schedule.last_error`, UI desktop hiển thị cảnh báo. Không có scan lịch mới.
- Lần scan Passive #1 ban đầu `failed` do submodule shell script CRLF khi mount từ Windows vào container QA. Sau khi dùng vendor script LF sẵn trong image, scan lịch #3 `done`. Đây là lỗi cách dựng fixture ban đầu, không tính là lỗi sản phẩm.

## Finding mới

**P2 — ZIP `filtered` giữ URL OUT khi chuỗi JSONL escape hai tầng.** Tạo file recon JSONL chứa `{"host":"a.example.com","matched-at":"https:\\\\/\\\\/a.example.com\\\\/admin\\\\/x"}` (một JSON string chứa các ký tự `\/`), rồi tải `GET /api/programs/qa-f1/export?mode=filtered` với OUT `https://a.example.com/admin`. Dòng này còn trong ZIP; giải mã giá trị `matched-at` cho URL thuộc OUT. Bộ lọc hiện thay `\/` bằng `/` một lượt trước khi tách token; escape lồng nhau còn dấu gạch chéo chưa chuẩn hóa nên path OUT không được nhận diện. Nên phân tích JSONL và kiểm từng giá trị chuỗi đã giải mã, hoặc chuẩn hóa escape có giới hạn trước khi kiểm tất cả URL/host token trong dòng. Kiểm thêm dữ liệu thật từ các tool để xác định tần suất của dạng escape lồng nhau; JSONL nuclei thông thường đã được lọc đúng.

## Giới hạn

- Không chạy Light/Strong hay kiểm chặn request active tới `/admin`; yêu cầu vòng này chỉ launch Passive cho F1.
- F3 dùng program H1 giả và sửa policy trên DB QA để tạo chuyển trạng thái; không gọi H1 thật.
- Ảnh chụp bằng Playwright Chromium headless ở 1366px. Review và Program không có cuộn ngang. Ảnh Review có thanh Launch cố định che một phần textarea ở ảnh viewport; giá trị textarea đã được đọc trực tiếp bằng Playwright và chứa đủ hai dòng.
