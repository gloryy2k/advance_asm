# BBASM v1.3.1 — kết quả kiểm thử host

Nguồn `ec1fe54` trên `claude/upbeat-thompson-b7bb23`; nhánh kết quả `test/v131-host-results`. Ngày 15/10/2026, Windows + Docker Desktop Linux, stack QA `bbasm-v12` tại `127.0.0.1:18765`. Fixture HTTP chỉ nghe `127.0.0.1:80` trong container; không dùng token/cookie và không scan target bên ngoài. Phép thử nuclei có template tự tạo được chạy trong container tạm `--network none`.

| Mã | Hành động / lệnh | PASS/FAIL/SKIP | Bằng chứng ngắn |
|---|---|---|---|
| T0 | `git fetch origin`; checkout `ec1fe54`; `docker compose -p bbasm-v12 up -d --build --force-recreate` | PASS | Image `sha256:6fc56e969fa1...`; stack healthy tại `127.0.0.1:18765`. |
| T1 | `docker run --rm --network none --entrypoint python -v <worktree>:/src:ro -w /src bbasm-v12-bbasm -m pytest -m 'not integration' -q --disable-warnings` | PASS | **359 passed**, 32 deselected, 29.61s. Mount nguồn chỉ đọc để các test cần `scripts/` collection được. |
| T2-F | Light #37, raw `127.0.0.1`, `X-HackerOne-Research: tester`, crawl bật; fixture ghi mọi request | PASS | **112/112 request có header**; `/robots.txt=0`, `/sitemap.xml=0`. Tool note ghi `katana: known-files ... tắt`. Scan thành `done_partial` do nuclei tự tải templates và hết ngân sách giai đoạn 98s (T4-R). |
| T2-UI | Mở Run #37 tại 1366px | PASS | “Giai đoạn & độ phủ” có dòng `katana: known-files (robots.txt, sitemap.xml) tắt`. [Ảnh Run](review_evidence/v131_host/run_warning_1366.png). |
| T3 | Light #38 trên fixture, `request_headers=[]`, crawl bật, nuclei tắt | PASS | Fixture nhận `/robots.txt=1`, `/sitemap.xml=1`; `tool_notes=[]`. Xác nhận `-kf` vẫn có hiệu lực khi không cấu hình policy header. |
| T4-H | GET `/api/health` trước template; Review draft #36 ở 1366px | PASS | `tools["nuclei"]=true`, `tools["nuclei-templates"]=false`, `missing_by_depth.light` có `nuclei-templates`; Review đánh dấu Nuclei **“Thiếu công cụ”**; không cuộn ngang (`scrollWidth=1366`). [Ảnh Review](review_evidence/v131_host/review_nuclei_missing_1366.png). |
| T4-R | Light #37 khi image không có template; xem Run/log và trạng thái template sau scan | **FAIL** | Run log cảnh báo thiếu `nuclei-templates`, nhưng pipeline vẫn gọi nuclei; nuclei tự tải **14.036 YAML** vào `/root/nuclei-templates`, health đổi thành `true`, làm giai đoạn timeout. Run vẫn ghi Nuclei “Chạy — 0 kết quả”, dù cũng ghi thiếu công cụ ở chân danh sách. Đã hủy scan và recreate container để xóa bản tải tạm. |
| T4-T | Container tạm `docker run --rm --network none`; thêm một YAML chỉ GET `/nuclei-check` vào `~/nuclei-templates`; Light có header | PASS | Health `false → true`; scan `done`; fixture nhận **1 request nuclei** tới `/nuclei-check` và có header. Template nằm trong container tạm và được xóa; container tự hủy. |
| T5 | Chạy ba regression integration cho header/katana trong image với fake tools và `--network none` | **FAIL** | **2 passed, 1 failed**. `test_policy_header_reaches_the_http_tools_that_run_but_never_discovery_or_the_logs` ghi GET `/` từ katana **thiếu header** khi fake httpx đưa URL có cổng; 11 request curl còn lại có header. Hai test shim/engine mới pass. |

## Finding mới

### P1 — Katana còn gửi request đầu tiên thiếu header với URL có cổng

- **Tái hiện:** chạy `backend/tests/test_v13_pipeline.py::test_policy_header_reaches_the_http_tools_that_run_but_never_discovery_or_the_logs` trong image đã có vendor ở `/app/vendor/claude-bug-bounty`, `--network none`. Recorder ghi `GET /` từ katana thiếu `X-HackerOne-Research`; các request curl có header. Test fake httpx trả `http://127.0.0.1:<port>`. Scan stack trên cổng 80 đạt 112/112, nên lỗi phụ thuộc đường đi này.
- **Hướng sửa:** bảo đảm header cho request mở đầu của katana với URL có cổng; giữ kiểm chứng request thực đến fixture thay vì chỉ kiểm argv. Chạy lại cả test này và ca cổng 80.

### P1 — Nuclei tự tải template và chạy dù đã báo thiếu

- **Tái hiện:** bắt đầu từ image không có YAML; health báo `nuclei-templates=false`; chạy Light bật nuclei. Pipeline vẫn gọi binary, khiến nuclei tự tải 14.036 template và scan #37 `done_partial` do timeout. Run vừa hiển thị Nuclei “Chạy — 0 kết quả”, vừa ghi thiếu template.
- **Hướng sửa:** khi health thiếu template, bỏ qua nuclei thực sự và đánh dấu phase `missing_tool`, hoặc chỉ cài template trong bước setup được người dùng chủ động chọn. Chặn cập nhật tự động trong scan để tuân thủ giới hạn egress; thêm test trong container `--network none` và kiểm không spawn nuclei khi thiếu template.

## Giới hạn và dọn dẹp

- Trong scan #37, nuclei đã **tự thực hiện truy cập để tải template ngoài dự kiến** trước khi tôi phát hiện. Tôi dừng scan, ghi lại sự việc và không chạy nuclei tiếp trên stack có mạng. Không có scan target bên ngoài. Container được recreate sau đó: health trở lại `nuclei-templates=false`; bộ template tự tải không còn trong container.
- Phép thử một template được thực hiện trên **cùng image** nhưng ở container tạm `--network none`, không phải stack đang mở. Cách này xác nhận header nuclei và chuyển trạng thái health mà không thể phát sinh truy cập ngoài localhost.
- HTTP fixture và script/template tạm đã được dọn; giữ stack `bbasm-v12` healthy cho người dùng xem. Chỉ commit báo cáo và ảnh, không commit `.env`, DB, targets hay dữ liệu header.
