# Kiểm lại sửa lỗi UI/logic tại 54411e5

Ngày 16/10/2026, Windows + Docker Linux, stack QA `bbasm-v12` tại `127.0.0.1:18765`. Nguồn `claude/upbeat-thompson-b7bb23` đúng commit `54411e519bafe3b7412f2064abc4baa08137883d`. Chạy `docker compose -p bbasm-v12 up -d --build --force-recreate`; build xong, container healthy. Trước rebuild chỉ có lịch `qa-v12-core` đang tắt. Không Launch, không scan target, không gọi H1. Stack QA được giữ chạy để xem.

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

## Finding mới

Không phát hiện lỗi mới trong phạm vi kiểm này.

## Giới hạn

- Không chạy scan mới, nên chưa kiểm việc lịch thực sự dispatch khi đến hạn hay dữ liệu của bản scan mới.
- Không gọi HackerOne và không kiểm policy/scope hiện hành của Wolt.
- Trình xem file dùng response giả để kiểm công tắc; không đọc file chứa secret thật.
- Chỉ kiểm desktop 1366px và các route nêu trong yêu cầu.

## Dọn dẹp

Lịch QA vừa tạo đã tắt; profile QA tạm đã xóa; số scan của program QA giữ nguyên. Container `bbasm-v12` vẫn chạy cho người dùng xem.
