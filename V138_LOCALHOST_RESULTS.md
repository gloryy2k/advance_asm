# Kiểm thử localhost trên `39cc484`

Ngày 2026-10-16, nhánh kết quả `test/39cc484-host-check`. Dữ liệu là fixture `*.example.com` trong DB QA riêng; không gọi HackerOne, Wolt hay bất kỳ asset ngoài localhost. Frontend được build từ commit này và phục vụ tại `127.0.0.1:18787`; ảnh chụp bằng Playwright Chromium headless 1366×900.

| Mã | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| Cây sitemap — dữ liệu | Resolve raw `*.example.com`; ghi 5.000 URL giả thuộc 5 host, đường dẫn lồng 4 thư mục, biến thể `?id=`, thư mục `/mega` có 350 mục | PASS | API trả 5 host A→Z; `/mega` có `total=350`, trang đầu 200. [JSON](review_evidence/v138_localhost/api_result.json), [ảnh cây](review_evidence/v138_localhost/tree_root.png). |
| Cây sitemap — thao tác | Mở/thu mũi tên, “Mở tới cấp 3”, “Xem thêm”, ↑↓←→ | PASS | “Xem thêm (150 mục)” xuất hiện sau trang 200 và tải phần còn lại; ↑↓ đổi focus, → mở, ← thu. Không cuộn ngang. [Ảnh phân trang](review_evidence/v138_localhost/tree_more_before.png), [cấp 3](review_evidence/v138_localhost/tree_level3.png). |
| Cây sitemap — tìm kiếm sâu | Tìm `item0999`, là file ở sau 4 thư mục lồng | **FAIL** | API lọc còn các nhánh khớp nhưng UI chỉ mở đến cấp 3: 15 hàng hiển thị, **0** hàng `item0999`. Người dùng phải tự mở các nhánh còn lại. [Ảnh](review_evidence/v138_localhost/tree_search_deep.png). |
| F4 | Resolve 2 lần cùng tên `qa-policy` với policy khác; mở Review draft #2, thử launch Light không header | PASS | Review draft #2 hiện cảnh báo và link draft #3, vẫn hiển thị policy cũ và hint `X-HackerOne-Research`; launch trả `422 header_required`. [Ảnh Review](review_evidence/v138_localhost/f4_old_review.png). |
| F5 | Nhập OUT `api*.example.com` ở Thêm program và ô loại trừ Review; thử cùng mẫu ở IN | PASS | Preview OUT `ok=true`, Resolve HTTP 200, PUT config Review HTTP 200; UI cho Resolve. IN `ok=false`, UI vô hiệu Resolve. [Ảnh OUT](review_evidence/v138_localhost/f5_new_out.png), [Review](review_evidence/v138_localhost/f5_review_out.png), [IN bị chặn](review_evidence/v138_localhost/f5_new_in_rejected.png). |
| Kiểm thử sẵn có | `pytest -q backend/tests/test_v138_sitemap.py backend/tests/test_v137_scope_selection.py -k "sitemap or f4 or f5"` trong Linux image `--network none` | PASS | 7 passed, 6 deselected. Cùng lệnh trên Windows gốc: 6 passed, 1 failed vì case F4 thử queue Passive trên Windows không có recon (môi trường `platform_unsupported`); API assertion `header_required` trước đó vẫn đạt. |

## Thời gian phản hồi UI

Một lượt đo bằng Playwright, tính từ click/nhập đến khi DOM cập nhật; đây là thời gian trên máy QA, chưa phải p95. [Dữ liệu thô](review_evidence/v138_localhost/browser_result.json).

| Thao tác | ms |
| --- | ---: |
| Chuyển sang Cây sitemap, thấy host đầu | 317 |
| Mở host | 61 |
| Mở `/mega` | 182 |
| Xem thêm 150 mục | 106 |
| Thu host | 117 |
| Mở tới cấp 3 | 302 |
| Phím → mở host | 14 |
| Tìm `item0349` và mở nhánh nông tới kết quả | 847 (gồm debounce 300 ms) |

## Finding mới

**P2 — Tìm kiếm cây không đưa URL sâu vào tầm nhìn.** Với URL `https://alpha.example.com/a7/b9/c3/d5/item0999?v=0`, nhập `item0999` ở Cây sitemap. UI có host và nhánh `/a7/b9`, nhưng file không hiện; các thư mục còn lại đang thu. Thành phần `SitemapTree` dùng `depth=3` cố định khi `searching`, nên tự mở chỉ đến cấp đó dù kết quả nằm sâu hơn. Nên mở toàn bộ đường dẫn khớp trong giới hạn số node, hoặc hiển thị danh sách kết quả khớp trực tiếp kèm nút mở vị trí trong cây. Nếu vượt giới hạn, cần thông báo rõ số kết quả bị ẩn và cách xem tiếp.

## Phạm vi và lưu ý

- Không chạy recon hay scan target; scan #1 được đánh dấu hoàn tất trong DB QA để UI có thể hiển thị 5.000 URL fixture. F4 chỉ thử launch Light không header, request bị từ chối trước khi chạy.
- Thử unit F4 trên Windows gốc không phù hợp với phần cuối của test vì runtime từ chối queue recon trên Windows; cùng tập test đã PASS trong Linux image không mạng. Đây không phải finding sản phẩm của ba luồng được yêu cầu.
- Chỉ kiểm desktop 1366px và một lượt đo; chưa đo tải nhiều người dùng hay các cỡ màn hình khác.
