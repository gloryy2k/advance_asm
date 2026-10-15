# Kiểm lại sửa lỗi UI/logic tại 54411e5

Ngày 16/10/2026, Windows + Docker Linux, stack QA `bbasm-v12` tại `127.0.0.1:18765`. Nguồn `claude/upbeat-thompson-b7bb23` đúng commit `54411e519bafe3b7412f2064abc4baa08137883d`. Chạy `docker compose -p bbasm-v12 up -d --build --force-recreate`; build xong, container healthy. Trước rebuild chỉ có lịch `qa-v12-core` đang tắt. Bảng đầu là vòng kiểm UI/API không Launch; bảng bổ sung bên dưới là vòng scan được người dùng yêu cầu sau đó. Stack QA được giữ chạy để xem.

| Mã | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| UI-1 | Wolt › Dữ liệu › URL, scan mới nhất #59 | PASS | Hiện thông báo scan mới nhất 0 URL, lịch sử 12.512 URL và nút “Xem URL lịch sử”. [Ảnh](review_evidence/v134_fixcheck/wolt_url_latest.png). |
| UI-2 | Bấm “Xem URL lịch sử” | PASS | Phạm vi `all`, 50 dòng trang đầu, cột Scan và link xuất `.txt` có `scan=all&min_score=0`. [Ảnh](review_evidence/v134_fixcheck/wolt_url_history.png). |
| UI-3 | Run #31 | PASS | Có ghi chú scan cũ so với #59; bốn link URL chứa `scan=31`; nút “Xem Brief hiện hành (scan #59)”. [Ảnh](review_evidence/v134_fixcheck/run_31.png). |
| UI-4 | Tổng quan Wolt | PASS | Host inventory 944, HTTP 4, chưa probe 940; lịch có dòng “Mỗi lần chạy”. [Ảnh](review_evidence/v134_fixcheck/wolt_overview.png). |
| UI-5 | Đổi mức lịch thành Light, không bật lịch | PASS | Hiện `X-HackerOne-Research` được gửi kèm và checkbox xác nhận scan tự động. [Ảnh](review_evidence/v134_fixcheck/wolt_schedule_light.png). |
| UI-6 | `qa-v121-diff` › Lịch sử › Diff | PASS | Hiện mốc #19 so #17 và “không phát hiện thay đổi”, không còn thông báo mơ hồ. [Ảnh](review_evidence/v134_fixcheck/diff.png). |
| UI-7 | `qa-v134-ui` › Scope & policy | PASS | Policy nhập tay hiển thị trong mục riêng. [Ảnh](review_evidence/v134_fixcheck/manual_policy.png). |
| UI-8 | Trình xem file với API giả | PASS | Bật “Hiện giá trị” thấy marker giả, công tắc vẫn còn để tắt; sau khi tắt giá trị lại được ẩn. [Bật](review_evidence/v134_fixcheck/artifact_reveal_on.png), [tắt](review_evidence/v134_fixcheck/artifact_reveal_off.png). |
| API-1 | `v134_policy_rescan_check.py` trên DB tạm | PASS | `before_manual_policy=true`, `after_manual_policy=true`, review rescan có hint `X-HackerOne-Research` và user text. |
| API-2 | `v134_schedule_ui_check.py` trên DB tạm, thêm `automation_ack=true` và thử `skipped_headers` | PASS | Header đã lưu → 200 và dùng trong config; thiếu header → 422 `header_required`; bỏ qua header có xác nhận → 200 và lưu đúng tên. |
| API-3 | ZIP Wolt: `brief`, `filtered`, `full` | PASS | Cả ba HTTP 200, ZIP hợp lệ, `MANIFEST.json` parse được và ghi đúng mode/scan #59. Brief 10 entry, không có recon; filtered/full 142 entry, có recon. |
| API-4 | URL `.txt?scan=all` | PASS | 12.448 dòng theo bộ lọc mặc định (ẩn static); `include_static=true` trả đủ 12.512 dòng. Filename `wolt-urls-all.txt`. |
| API-5 | Bật/tắt lịch Passive tuần cho `qa-v134-ui` | PASS | Khi bật: `enabled=1`, lần kế tiếp sau một tuần; khi tắt: `enabled=0`. Số scan 15 trước và sau. |
| API-6 | Tạo, sửa, xóa profile QA tạm | PASS | Sửa description và threads=1 được lưu; xóa xong không còn trong danh sách. |

Lệnh: `Get-Content -Raw review_tools/v134_policy_rescan_check.py | docker compose -p bbasm-v12 exec -T bbasm python -`; tương tự với `v134_schedule_ui_check.py`. `python review_tools/v134_fix_ui_check.py` chạy Playwright headless 1366px; `python review_tools/v134_fix_api_check.py` kiểm API qua localhost. Ảnh ở `review_evidence/v134_fixcheck/`. Chín màn hình đều không cuộn ngang ở 1366px.

## Kiểm nốt scan, scheduler và Wolt

Đã dùng Light Wolt #60 do người dùng tạo; không tạo bản Light trùng. Strong Wolt #64 được giới hạn vào `corporate.wolt.com` (asset IN), 1 luồng/1 req/s, 180 giây ngân sách pipeline, header `X-HackerOne-Research` đã lưu. Tắt historical, takeover, secrets, crawl, nmap, ffuf và nuclei (image thiếu template). Vì vậy #64 là kiểm Strong có giới hạn, không phải quét toàn bộ Wolt. Cấu hình và kết quả đã loại giá trị header trong [wolt_strong.json](review_evidence/v134_fixcheck/wolt_strong.json). Dữ liệu thô tóm tắt của #60–#65 ở [remaining_scans.json](review_evidence/v134_fixcheck/remaining_scans.json).

| Mã | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| R-1 | Passive #61 → Light #62 trên fixture HTTP `127.0.0.1` | PASS | #61 `done` sau 4,3s; #62 `done` sau 11,9s, HTTP live=1, URL=1, Diff changed=1 với baseline #61. [JSON](review_evidence/v134_fixcheck/local_flow.json). |
| R-2 | Lịch Passive localhost tới hạn sau restart | PASS | Dừng riêng stack QA, đặt `next_run_at=2026-01-01T00:00:00+00:00`, khởi động lại: scan #63 `trigger=scheduled`, `done`; lịch đã tắt (`enabled=0`). |
| R-3 | Đọc metadata H1 công khai Wolt khi tạo draft Strong | PASS | `policy_source=public_page`, IN 12/12, OUT 12/12, 0 unclassified, Light/Strong được mở khóa; `h1_api=false`, không dùng token. |
| R-4 | Light Wolt #60 của người dùng | PASS | Kết thúc `done_partial`; nhập được 711 host, 259 có HTTP, 556 URL, 59 finding; 404/704 host khám phá chưa probe. Diff so #59: 235 new, 227 changed, 0 gone. Wayback và các stage probe/deep hết thời gian, lý do hiện rõ. [Run](review_evidence/v134_fixcheck/run_60_light.png). |
| R-5 | Strong Wolt #64 có giới hạn | PASS | `done`, 1 host live, 1 URL, 0 finding, baseline #60; 24 scope rule của Wolt còn nguyên. Tổng khoảng 200s. [Run](review_evidence/v134_fixcheck/run_64_strong.png), [Dữ liệu URL](review_evidence/v134_fixcheck/wolt_latest_after_strong.png). |
| R-6 | Strong localhost #65 với nmap thật | PASS | `done` sau 17,4s; phase `port_scan=ran`, 4 cổng ghi nhận, baseline #63. [JSON](review_evidence/v134_fixcheck/local_strong.json). |
| R-7 | UI sau Light/Strong | PASS | Run #60 có 5 link URL mang `scan=60`; Run #64 và tab URL mới nhất nêu rõ scan #64. Ba ảnh 1366px không cuộn ngang. |
| R-8 | Thời gian xếp hạng Wolt #64 | FAIL | Recon stage chính 3s nhưng `rank` mất 177,1s; scan thực tế gần 200s dù cấu hình `scan_timeout=180`. DB có 1.479 asset, 12.857 URL; `EXPLAIN QUERY PLAN` cho tra URL/finding trong `rank_program` đều `SCAN` toàn bảng. |
| R-9 | Phân loại URL do httpx probe | FAIL | URL #64 Wolt và #65 localhost đều `source=httpx`, `verification=historical` dù HTTP đã phản hồi. Run #64 nói 0 URL tool tìm thấy trong khi thống kê latest có 1 URL. |
| R-10 | Lý do bỏ qua config check khi tắt crawl | FAIL | #64 có 1 host HTTP nhưng log ghi “No live hosts — skipping config check”; kế hoạch nói config check sẽ chạy, Run ghi `no_output`/lý do chung. Cấu hình thực tế có `skip_active_crawl=true`. |
| R-11 | Nmap/ffuf/nuclei và crawl toàn Wolt | SKIP | Không chạy trên Wolt: policy loại trừ brute force, Light #60 mới probe 300/704 host, và image thiếu nuclei templates. Nmap Strong đã được kiểm trên localhost #65. |

Tổng hai vòng: **21 PASS · 3 FAIL · 1 SKIP**. Lệnh chính: `python review_tools/v134_remaining_local.py`, `python review_tools/v134_schedule_due.py <đường dẫn DB QA>` (chỉ khi container dừng), `docker compose -p bbasm-v12 start`, `python review_tools/v134_local_strong.py`, `python review_tools/v134_final_ui_check.py`. Script `v134_wolt_strong_check.py` chỉ chạy lại khi đặt `BBASM_ALLOW_WOLT_STRONG=1` rõ ràng; lần kiểm này đã chạy với cấu hình ghi trong JSON, không cần chạy lại. Script `v134_remaining_evidence.py` và `v134_rank_diagnostic.py` chỉ đọc DB/log QA.

## Finding mới

1. **P1 — Xếp hạng có độ trễ lớn theo kích thước lịch sử program.** Tái hiện: chạy Strong #64 một host trên DB QA Wolt; đọc `data/logs/64.jsonl`, stage `rank` mất 177,1s, trong khi stage recon chính 3s. `backend/asm/ranking.py::rank_program` lặp qua mọi asset, tra URL và finding theo asset nhưng DB không có index phù hợp (`EXPLAIN`: `SCAN url`, `SCAN finding`). Hướng sửa: thêm index `(asset_id,last_seen_scan)` cho URL và `(asset_id,type,last_seen_scan)` cho finding; gom dữ liệu theo batch hoặc chỉ xếp hạng asset bị ảnh hưởng. Benchmark lại trên bản sao DB Wolt. Thời gian hậu xử lý cần được nêu riêng nếu `scan_timeout` chỉ áp cho pipeline.
2. **P2 — URL httpx bị gắn nhãn “lịch sử”.** Tái hiện: GET `/api/programs/wolt/urls?scan=latest&min_score=0` sau #64 hoặc program localhost sau #65; dòng `source=httpx` có `verification=historical`. Trong `backend/jobs/ingest.py`, mọi URL không thuộc tập katana đều thành historical. Hướng sửa: gán `live` cho URL do httpx xác nhận, hỗ trợ lọc/hiển thị `live` trên UI, và giải thích rõ phần URL probe nằm ngoài funnel archive/crawl hoặc tính nó vào funnel.
3. **P2 — Kế hoạch và lý do bỏ qua config check không khớp cấu hình.** Tái hiện: #64 có `skip_active_crawl=true` và 1 host HTTP; plan vẫn `config_expose=on`, log ghi “No live hosts”, Run ghi `no_output`. Engine thực tế bỏ config check vì `skip_active_crawl`, không phải vì thiếu live host. Hướng sửa: cho plan/phase biết phụ thuộc này và log “bỏ qua theo cấu hình”; tách trường hợp không có host thật.

Không sửa code sản phẩm trong vòng QA này.

## Giới hạn

- Wolt Light #60 là `done_partial`: 404 host khám phá chưa probe; số finding chưa chứng minh tính hợp lệ của lỗ hổng.
- Strong Wolt #64 chỉ kiểm một asset và các bước được bật như bảng trên. Kết quả không đại diện cho toàn scope hay đầy đủ khả năng Strong; nuclei chưa có template.
- Sau #64, tab URL mặc định xem scan mới nhất chỉ có 1 URL điểm thấp nên bị bộ lọc “đáng xem” ẩn. Chọn “Hiện tất cả” hoặc phạm vi lịch sử để xem dữ liệu #60 và các scan trước.
- Trình xem file ở vòng đầu dùng response giả; chỉ kiểm desktop 1366px.

## Dọn dẹp

Lịch QA đã tắt, profile QA tạm đã xóa, fixture HTTP 127.0.0.1:80 đã dừng. Scan QA localhost #61–#63 và #65, Wolt Light #60 của người dùng, Wolt Strong #64 còn trong stack QA để đối chiếu. Scope Wolt vẫn có 24 rule. Container `bbasm-v12` vẫn chạy ở `127.0.0.1:18765`.
