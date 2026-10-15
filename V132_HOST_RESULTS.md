# BBASM v1.3.2 — kết quả kiểm thử host

Nguồn `3f2af8c` (`claude/upbeat-thompson-b7bb23`), nhánh kết quả `test/v132-host-results`. Ngày 15/10/2026, Windows + Docker Desktop Linux; stack QA `bbasm-v12` ở `127.0.0.1:18765`. Mọi scan nhắm HTTP fixture `127.0.0.1:80`; test có một template nuclei chạy trong container tạm `--network none`. Không dùng H1, token hay target ngoài localhost.

| Mã | Lệnh / hành động | PASS/FAIL/SKIP | Bằng chứng ngắn |
|---|---|---|---|
| T0 | `git fetch origin`; checkout `3f2af8c`; `docker compose -p bbasm-v12 up -d --build --force-recreate` | PASS | Image mới `sha256:83b6f86e5646...`; container healthy. Ban đầu `/root/nuclei-templates` có **0 YAML**, `/api/health` báo `nuclei-templates=false`. |
| T1 | `docker run --rm --network none --entrypoint python -v <worktree>:/src:ro -w /src bbasm-v12-bbasm -m pytest -m 'not integration' -q --disable-warnings` | PASS | **362 passed**, 32 deselected, 30.13s. Mount source chỉ đọc để test cần `scripts/` được collect. |
| T2-A | Light #39, raw `127.0.0.1`, nuclei bật, crawl bật, `request_headers=["X-HackerOne-Research: tester"]`, `skip_historical=true` | PASS | Scan `done` sau **18.79s**, không timeout; fixture **25/25 request có header**, không có `/robots.txt` hay `/sitemap.xml`; log ghi `[!] nuclei skipped theo cấu hình scan`. Sau scan vẫn **0 YAML** và health vẫn `nuclei-templates=false`. |
| T2-B | Kiểm `docker compose -p bbasm-v12 top`, `docker compose ... logs --no-color`, log scan #39 và `/proc/net/tcp` trong lúc chạy | PASS | `top` trong và sau scan không thấy nuclei; compose log có 0 dòng nuclei/template; scan log xác nhận skip. Snapshot `/proc/net/tcp` có **0 kết nối ESTABLISHED** ra ngoài. Kết hợp cờ `BBASM_SKIP_NUCLEI=1` từ `recon_env`, không có bằng chứng nuclei được spawn. |
| T2-C | GET `/api/scans/39/phases`; xem Run #39 headless 1366px | PASS | Phase Nuclei có `status=missing_tool`; Run nêu `nuclei-templates` thiếu. |
| T2-D | Kiểm Run có ghi chú **“chặn tải template tự động”** | **FAIL** | Run không có câu này. Cảnh báo cũ vẫn viết “nuclei chạy nhưng không kiểm tra gì” dù log scan cho thấy nuclei **đã bị bỏ qua**. |
| T2-NET | Kiểm egress liên tục bằng `ss -tnp` | SKIP | Image không cài `ss`; chỉ có snapshot `/proc/net/tcp` và kiểm tiến trình/log như T2-B. Không khẳng định có phép đo egress liên tục. |
| T3 | `docker run --rm --network none` trên cùng image; thêm 1 YAML tạm chỉ GET `/nuclei-check`; Light có header | PASS | Health `false → true`; scan `done`; fixture nhận **1 request nuclei** và tên header được so không phân biệt hoa thường, giá trị đúng. Theo dõi `/proc/*/cmdline` thấy `/usr/local/bin/nuclei -duc ...`. Container tạm tự hủy, template không còn. |
| T4 | `BBASM_TEST_REAL_KATANA=$(command -v katana) python -m pytest -m integration backend/tests/test_v13_pipeline.py -k "policy_header or katana" -q` trong image có vendor ở path fixture, `--network none` | PASS | **2 passed**, 8 deselected, 12.40s. Dùng binary katana thật, chỉ recorder localhost. |

## Finding mới

### P2 — Run giải thích sai khi chặn nuclei thiếu template

- **Tái hiện:** từ image không có template, chạy Light #39 với nuclei bật. `/api/scans/39/phases` trả `missing_tool` và log engine nói nuclei bị skip. Mở Run #39: không có ghi chú “chặn tải template tự động”; cảnh báo nói “nuclei chạy nhưng không kiểm tra gì”.
- **Hướng sửa:** khi `nuclei-templates` thiếu, Run/log nên nói rõ **nuclei không được chạy và BBASM chặn tải template tự động**. Đồng bộ câu chữ giữa warning, phase và log engine; tránh diễn đạt như thể nuclei đã chạy.

## Giới hạn và dọn dẹp

- Không có template nào được cài trong stack `bbasm-v12`; test template dùng container tạm `--network none`. Không có scan target ngoài localhost. `ss` không có trong image nên trạng thái kết nối được kiểm bằng snapshot `/proc/net/tcp`, không phải giám sát liên tục.
- HTTP fixture, log fixture và script/template tạm đã dọn. Giữ stack QA healthy tại `127.0.0.1:18765` và dữ liệu scan #39 để người dùng xem. Chỉ commit báo cáo này; không commit `.env`, DB hoặc targets.
