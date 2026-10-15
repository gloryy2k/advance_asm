# BBASM v1.3 — kiểm thử host

Nguồn: `d53fe09` (`claude/upbeat-thompson-b7bb23`); nhánh kết quả: `test/v13-host-results`. Ngày 15/10/2026, Windows + Docker Desktop Linux, project `bbasm-v12`, cổng UI/API `127.0.0.1:18765`. Toàn bộ scan thật trong vòng này chỉ nhắm `127.0.0.1` bên trong container; các integration test nguồn công khai dùng fake tools và `--network none`. Không dùng H1/token/cookie.

| Mã | Hành động / lệnh | PASS/FAIL/SKIP | Bằng chứng ngắn |
|---|---|---|---|
| T0 | `git fetch origin`; checkout `d53fe09`; `docker compose -p bbasm-v12 up -d --build --force-recreate` trong `advance_asm-v12test` | PASS | Image mới `sha256:cbf1685c...`; container healthy; compose bind `127.0.0.1:18765`. Giữ stack chạy. |
| T1-U | `docker run --rm --network none --entrypoint python -v <worktree>:/src:ro -w /src bbasm-v12-bbasm -m pytest -m 'not integration' -q --disable-warnings` | PASS | **355 passed**, 31 deselected, 28.86s. Chạy từ mount nguồn đầy đủ vì `/app` trong image không chứa `scripts/` cho collection. |
| T1-F | `cd frontend && npm test -- --run` | PASS | **54 passed** trong 1 file, 9.24s. Build frontend trong `docker compose --build` cũng thành công (`vite` 203 modules). |
| T2 | Help và version của subfinder, katana, nuclei, ffuf, httpx trong container | PASS | subfinder **v2.17.0** có `-max-time`; katana **v1.8.0** có `-H`; nuclei **v3.11.1** có `-H`; ffuf **v2.3.0** có `-H`; httpx **v1.12.0**. |
| T3-HC | Raw `127.0.0.1`, Light #32, `request_headers=["X-HackerOne-Research: tester"]`, crawl bật, nuclei low; HTTP fixture bind `127.0.0.1:80` trong container | PASS | #32 `done`; fixture ghi httpx tới `/` có header; **22/22 request curl** có header. `GET /api/scans/32` báo 1 live host. |
| T3-HK | Cùng scan #32: kiểm mọi request katana tới fixture | **FAIL** | Katana gửi `/robots.txt` và `/sitemap.xml` **không có header**, sau đó `/`, `/admin`, `/public` có header. Integration `test_policy_header_reaches_the_http_tools_that_run_but_never_discovery_or_the_logs` cũng fail ở assertion mọi request đều có header. |
| T3-HN | Nuclei low trong #32 và #34; template kiểm thử độc lập trên localhost | **FAIL** | Scan ghi `nuclei on 1 hosts` rồi `no findings`, nhưng fixture nhận **0 request nuclei**; image có **0 file `*.yaml`** trong `/root/nuclei-templates`. Chạy nuclei binary v3.11.1 với template tạm `GET /nuclei-check`, `-H ... -duc` thì fixture nhận header. Vì thiếu template, chưa thể xác nhận luồng nuclei tích hợp thực gửi header. |
| T3-SEC | Tìm `tester` trong `data/logs/{32,33,34,35}.jsonl`, `targets/qa-v13-*/audit.jsonl`, `scan_run.stats_json` và `docker compose logs` | PASS | 0 lần trong bốn loại log/trạng thái; `stats_json` chỉ chứa tên header. Marker giả chỉ có ở cấu hình scan/fixture tạm. |
| T4-OFF | Raw `127.0.0.1`, OUT `http://127.0.0.1/admin`, Light #33, `allow_active_on_path_rules=false` | PASS | #33 `done`; fixture ghi đúng **1 request `/`** để probe, **0 `/admin*`**; không có curl/katana/nuclei tới path OUT. Review giải thích host chỉ được probe. |
| T4-ON | Cùng OUT, Light #34, `allow_active_on_path_rules=true` | PASS | #34 `done`; fixture ghi **1 `/admin` từ katana**; không thấy curl/nuclei tới `/admin` trong lần này. Đây là hành vi được Review cảnh báo: công cụ active không cưỡng chế OUT theo path. |
| T5-LIVE | Passive #35 trên raw `127.0.0.1`, `skip_historical=true` | PASS | #35 `done`, không crash, không request tới host ngoài. IP literal không chạy subfinder/curl historical nên scan này không sinh `.source_status.tsv`. |
| T5-SHIM | `docker run --rm --network none ... pytest backend/tests/test_v13_pipeline.py::test_wayback_hang_is_bounded_and_every_source_result_is_kept` với fake tools | PASS | 1 passed; `.source_status.tsv`: `subfinder ok`, `crt.sh ok`, `web.archive.org timeout 2s`. Không gọi nguồn thật. |
| T5-REG | Toàn bộ integration `backend/tests/test_v13_pipeline.py` trong image, copy vendor đã chuẩn hóa tới path fixture, `--network none` | **FAIL** | **5 passed, 1 failed, 2 deselected** trong 85s. Test fail chính là T3-HK: request katana thiếu header. |
| T6 | Playwright + Chrome headless, viewport 1366px: Review draft #36 và Run #32 | PASS | Review hiển thị panel **Header gửi kèm request tới target** và **OUT theo đường dẫn**; Run hiển thị **Giai đoạn & độ phủ**. Cả hai `document.documentElement.scrollWidth=1366`. Ảnh: [Review](review_evidence/v13_host/review_1366.png), [Run](review_evidence/v13_host/run_1366.png). |

## Finding mới

### P1 — Katana gửi request khởi đầu thiếu header bắt buộc

- **Tái hiện:** chạy Light #32 với `X-HackerOne-Research: tester`, fixture trả HTML link. Katana v1.8.0 dùng `-kf all`. Request của nó tới `/robots.txt` và `/sitemap.xml` không có header; các request crawl tiếp theo có. Bài integration `test_policy_header_reaches_the_http_tools_that_run_but_never_discovery_or_the_logs` fail cùng lý do.
- **Tác động:** Với program yêu cầu header trên *mọi* request, scan Light không tuân thủ policy dù Review đã nhập header.
- **Hướng sửa:** buộc header áp dụng cho request known-files/robots/sitemap của katana hoặc tắt tính năng đó khi không đảm bảo được; thêm regression test ghi nhận toàn bộ request đến fixture, gồm request khởi đầu.

### P1 — Nuclei báo đã chạy nhưng image thiếu template

- **Tái hiện:** image v1.3 báo nuclei available; Light #32/#34 bật nuclei low, log ghi `nuclei on 1 hosts` và `no findings`, nhưng `/root/nuclei-templates` có 0 YAML và fixture nhận 0 request nuclei. Binary nuclei hoạt động với template tạm chỉ nhắm localhost.
- **Tác động:** UI có thể khiến người dùng hiểu nhầm target đã được kiểm tra bằng nuclei.
- **Hướng sửa:** pin/provision bộ template được phép trong image, hoặc đánh dấu phase `missing_templates`/`skipped` và nêu rõ trong health, Run, brief. Sau đó test header nuclei bằng template fixture trong luồng tích hợp.

## Giới hạn và dọn dẹp

- Với raw IP `127.0.0.1`, Passive không cần nguồn subdomain/historical, nên `.source_status.tsv` được xác minh qua integration fake-tools thay vì scan #35. Không dùng một domain giả để tránh bất kỳ truy vấn ngoài localhost.
- Nuclei tích hợp chưa thể chứng minh header do không có template; phép thử binary độc lập chỉ chứng minh tùy chọn `-H` hoạt động.
- Hai lần chạy integration ban đầu trong container tạm fail do fixture tìm vendor ở `/app/vendor/claude-bug-bounty` trong khi image chỉ đặt ở `/opt/claude-bug-bounty`; lần chạy có copy vendor vào path fixture cho kết quả 5/1 ở trên. Không sửa sản phẩm hay test.
- HTTP fixture và template tạm được dọn sau khi ghi nhận kết quả. Giữ container `bbasm-v12-bbasm-1` và các scan QA #32–#36 để người dùng xem. Không commit DB, targets, `.env` hoặc marker.
