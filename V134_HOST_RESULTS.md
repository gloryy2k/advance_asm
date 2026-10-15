# BBASM c11440d — host QA (2026-10-16)

Nguồn: `origin/claude/upbeat-thompson-b7bb23` tại `c11440d`; nhánh kết quả `test/v134-host-results`. Windows host, Docker Linux image `bbasm-v12-bbasm`, QA stack `bbasm-v12` tại `127.0.0.1:18765`. Không gọi HackerOne, không chạy Wolt, không dùng token/cookie, không scan host ngoài. Scan kiểm thử dùng `TestClient`, process giả trong bộ nhớ và dữ liệu tạm. Ảnh UI lấy từ stack localhost, chỉ tạo draft.

## Kết quả

| Mã | Lệnh / hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| T0 | `git fetch origin`; checkout `c11440d`; `docker compose -p bbasm-v12 up -d --build --force-recreate` | PASS | Image build và stack healthy tại `127.0.0.1:18765`. |
| T1 | `docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm-v12test:/src:ro' -w /src bbasm-v12-bbasm -m pytest -m 'not integration' -q --disable-warnings` | PASS | 372 passed, 32 deselected, 4 warnings; 39.23 s. |
| T2 | `cd frontend; npm ci; npm test` | PASS | Vitest: 54 passed; 9.18 s. Docker rebuild cũng chạy frontend build. |
| T3 | `docker run --rm --network none --entrypoint bash -v 'E:\code\bbasm\advance_asm-v12test:/src:ro' -w /src bbasm-v12-bbasm -lc 'mkdir -p /app/vendor && cp -a /opt/claude-bug-bounty /app/vendor/ && python -c "from pathlib import Path; import backend.config; backend.config.PROJECT_ROOT=Path(\"/app\"); import pytest; raise SystemExit(pytest.main([\"-m\",\"integration\",\"-q\",\"--disable-warnings\"]))"'` | PASS (phần chạy được) | 13 passed, 19 skipped, 372 deselected, 5 warnings; 98.94 s. Các mục cần Docker/browser/recon riêng bị skip theo gate test. Lần chạy đầu trên vendor checkout Windows gặp 8 fail do đường dẫn/CRLF của fixture; chạy lại với vendor chuẩn trong image cho kết quả trên. |
| S1 | `docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm:/src:ro' -w /src bbasm-v12-bbasm review_tools/v134_scale_check.py` | PASS | Fixture 750 host + 12.750 URL, scan #1 `done`, không error; 3 vòng poll mỗi 1 s, đọc cả scan/phases/review; poll chậm nhất 0,052 s. `stage` running/ok đầy đủ: ingest 0,6 s; monitors 0,0 s; diff 0,0 s; rank 0,5 s; brief 0,0 s; sự kiện cuối `done`. Thời gian stage được engine làm tròn một chữ số thập phân. |
| S2 | Cùng script, scan #2; giữ điểm trả về của ingest sau khi đã ghi đủ fixture, POST `/api/scans/{id}/cancel` | PASS | Cancel HTTP 200 trong 0,026 s (<10 s), trạng thái cuối `cancelled`, sự kiện cuối `done`/`cancelled`; stage cuối `ingest`. Poll chậm nhất 0,024 s. Đây là điểm chặn có kiểm soát trong mock, không phải phép đo ingest chậm thực tế. |
| H1 | `docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm:/src:ro' -w /src bbasm-v12-bbasm review_tools/v134_header_check.py` | PASS | Policy giả chứa `X-HackerOne-Research`. Light và Strong thiếu header: HTTP 422 `header_required`, draft giữ nguyên. Có header: HTTP 200, scan `done`. `skip_required_headers=true`: HTTP 200, scan `done`. Passive không header: HTTP 200, scan `done`. Process đều giả, không có request tới target. |
| U1 | Playwright headless Chrome, Review tại `127.0.0.1:18765`, desktop 1366px | PASS | Bảy ảnh `review_evidence/v134_header_gate/`: Light/Strong × thiếu header/có header/chọn bỏ qua, và Passive không header. Với ca bỏ qua, ô xác nhận trên UI đã được chọn. Cả 7 ảnh: `scrollWidth=innerWidth=1366`. Không Launch từ browser. |

Tổng: **8 PASS; 0 FAIL; 0 SKIP** ở cấp hạng mục trên. Trong suite integration có **19 test skip** theo điều kiện môi trường; không coi là pass.

## Finding

**P2 — Review không khôi phục xác nhận bỏ qua header từ config đã lưu.** Tạo draft với policy nhắc `X-HackerOne-Research`, `PUT /api/scans/{id}/config` chứa `skip_required_headers=true` và `request_headers=[]`, mở lại `/#/scan/{id}/review`. Ô “Tôi đã đọc policy và không dùng header…” vẫn chưa chọn, trang vẫn báo cần header. `Review.tsx` khởi tạo `skipHint=false` và không đồng bộ từ `config.skip_required_headers`; lệnh Launch dùng `skipHint` để ghi đè flag. Hướng sửa: đồng bộ trạng thái ô với config khi tải draft, hoặc xác định rõ cờ bỏ qua chỉ áp dụng cho lần Launch và không lưu nó vào config. Ảnh `review_light_skip.png` ghi trạng thái sau khi người dùng chọn ô, còn API harness xác nhận backend nhận flag đúng.

## Giới hạn và dọn dẹp

- Mốc `used_s=0,0` là thời gian dưới độ phân giải log, không phải không chạy.
- Fixture S1/S2 dùng output giả và `--network none` để đo lifecycle/API; không suy ra tốc độ recon trên mạng thật. Không có scan kẹt nên không cần thread dump của `faulthandler`; script sẽ dump nếu vượt 180 s.
- Bảy draft UI chỉ chứa `127.0.0.1` và policy giả. QA stack `bbasm-v12` được giữ chạy để người dùng xem, không prune container/image/volume.
- Không thay đổi code sản phẩm. Hai script `review_tools/v134_*_check.py` và các PNG là bằng chứng QA.
