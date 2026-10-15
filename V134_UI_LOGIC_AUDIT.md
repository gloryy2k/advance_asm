# Rà soát logic UI/UX sau scan Wolt #59

Ngày 2026-10-16; code nguồn `c11440d`, nhánh kết quả `test/v134-host-results`. Chỉ đọc API/Playwright headless tại `127.0.0.1`; riêng test schedule dùng DB tạm và container `--network none`. Không chạy scan, không gọi H1, không sửa/xóa dữ liệu Wolt hay code sản phẩm. Số liệu dưới đây là snapshot của stack QA tại lúc kiểm tra.

| ID | Mức | Kết luận và bằng chứng | Tái hiện / hướng sửa |
| --- | --- | --- | --- |
| UI-1 | P1 | **Tab URL tạo cảm giác mất dữ liệu.** Scan Wolt #59 `done`, `url_history=empty`, 0 URL; `/api/programs/wolt/urls/summary` trả `total=0`. `/api/programs/wolt/urls?scan=all&min_score=0` vẫn trả 12.448 URL (505 URL với `min_score=1`). `/#/program/wolt/data` mặc định vào URL và Playwright thấy 0 hàng, thông báo “Không có URL phù hợp”. | Mở route trên sau scan mới không có URL. Thêm lựa chọn “Scan mới nhất / Tất cả scan” (backend đã nhận `scan=all`), ghi scan ID và thời gian/nguồn trên danh sách; khi latest=0 mà history>0, hiện CTA xem lịch sử thay vì nói “chưa có URL”. Đừng ngầm trình bày URL cũ như kết quả scan mới. |
| UI-2 | P1 | **Link kết quả từ Run cũ mất ngữ cảnh scan.** Scan Wolt #31 có phase `url_history=ran`, count 4.667. `Run.tsx` dùng `dataLink(slug, phase.view)` để mở Program URL; link này không mang scan ID và chuyển vào danh sách latest của #59, hiện trống. | Mở `/#/scan/31`, bấm “Xem URL” ở bước URL lịch sử. Truyền scan ID trong link và hỗ trợ lọc URL theo scan, hoặc mở artifact của đúng scan. Cùng nguyên tắc cho nút “Xem Brief” trên Run cũ: nêu rõ nếu đó là brief hiện hành của program. |
| UI-3 | P1 | **Bật giám sát Light không dùng header đã lưu.** Với policy giả yêu cầu `X-HackerOne-Research`, lưu header qua `PUT /api/programs/<slug>/request-headers`; summary trả header đúng. `Program.tsx` chỉ POST `{interval,depth,enabled}`; `backend/api/programs.py:schedule` tạo `default_config` không có header, nên API trả HTTP 422 `header_required`. Đã tái hiện bằng `review_tools/v134_schedule_ui_check.py` trên DB tạm, không launch scan. | Program có header mặc định → chọn Light, tick xác nhận → “Bật giám sát”. Backend cần áp header mặc định vào cấu hình lịch (hoặc UI truyền config đúng) và hiển thị rõ header/rate limit/depth trước khi bật. Test cả bật, cập nhật và tick thật; không dùng policy/H1 thật. |
| UI-4 | P2 | **“Host đang hoạt động” bị hiểu là live.** Tổng quan Wolt ghi `944 Host đang hoạt động`; API trả 944 asset `state=active` nhưng 940 không có `status_code`, và scan #59 là Passive (không probe HTTP). `active` ở đây là trạng thái inventory, không chứng minh host trả lời HTTP. | Mở Tổng quan/Dữ liệu → Host của Wolt. Đổi nhãn thành “Host trong inventory/được quan sát”, tách số `HTTP live`, `chưa probe`, `biến mất`; trong bảng, hiển thị “chưa kiểm tra” thay cho dấu gạch ngang mơ hồ. |
| UI-5 | P2 | **Thông báo Diff trống nêu sai lý do.** Program QA `qa-v121-diff` có scan #17 và #19 hoàn tất, `baseline_scan_id=17`, Diff tổng 0. Playwright tại `/#/program/qa-v121-diff/history?v=diff` vẫn hiện “Diff xuất hiện sau khi program có từ hai scan hoàn tất.” | Nếu có baseline và diff=0, hiển thị “Đã so sánh #19 với #17: không phát hiện thay đổi”; chỉ dùng thông báo cần 2 scan khi thật sự thiếu baseline. |
| UI-6 | P1 | **“Scan lại” làm mất policy nhập tay của raw program.** Trên DB tạm, resolve raw với `policy_text` yêu cầu `X-HackerOne-Research`; trước rescan `program.policy.user_policy_text` có nội dung. POST `/api/programs/<slug>/rescan` xong, trường đó rỗng và Review draft mới có `request_header_hints=[]`. Không launch scan. | Chạy `review_tools/v134_policy_rescan_check.py`. `rescan` gọi raw ResolveRequest không mang policy; resolver thay `policy_json` của program bằng policy raw mới. Giữ `user_policy_text` khi rescan/re-resolve nếu người dùng không cung cấp bản thay thế; kiểm lại header gate và PROGRAM.md. |
| UI-7 | P1 | **Tab Scope & policy không hiển thị policy nhập tay.** `GET /api/programs/qa-v134-ui` có `policy.user_policy_text` dài 61 ký tự; `ScopeView` chỉ đọc `policy_text` hoặc `program.policy`. Playwright tại `/#/program/qa-v134-ui/guide?v=scope` báo “Chưa có nội dung policy” dù Review #57 hiển thị policy đó. | Hiển thị cả policy nguồn và phần người dùng bổ sung, ghi nhãn nguồn rõ; cập nhật khi người dùng sửa. Đây là lỗi độc lập với UI-6: ngay cả trước rescan, policy đã lưu vẫn bị ẩn ở tab này. |
| UI-8 | P2 | **Trình xem file không cho ẩn lại sau khi hiện secret.** `ArtifactViewer.tsx` chỉ render checkbox “Hiện giá trị” khi response `redacted=true`; sau khi chọn reveal, backend trả `redacted=false` và checkbox biến mất. Playwright dùng API giả với marker `H1_TOKEN=FAKE-MARKER`: checkbox từ 1 thành 0, marker thô còn hiển thị. Không đọc secret thật. | Giữ công tắc hiện/ẩn độc lập với `page.redacted`; cho tắt reveal và tải lại bản đã che. Cảnh báo trước tải file thô, tránh để nút tải đổi chế độ một cách khó nhận ra. |

Finding đã ghi trong `V134_HOST_RESULTS.md`: Review không khôi phục checkbox `skip_required_headers` từ config đã lưu. Các đề xuất về trang Công cụ, template Nuclei và archive/xóa program nằm trong `V134_PRODUCT_PROPOSALS.md`.

## Lệnh kiểm chứng nhanh

```text
GET http://127.0.0.1:18765/api/programs/wolt/urls/summary
GET http://127.0.0.1:18765/api/programs/wolt/urls?scan=all&min_score=0&limit=1
GET http://127.0.0.1:18765/api/programs/wolt/assets?state=active&limit=1000
GET http://127.0.0.1:18765/api/scans/31/phases
GET http://127.0.0.1:18765/api/scans/59/phases
docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm:/src:ro' -w /src bbasm-v12-bbasm -m review_tools.v134_schedule_ui_check
```

Không có dữ liệu Wolt nào bị dọn trong lần rà soát này; API vẫn truy cập được URL lịch sử và host. Các finding liên quan tới ngữ cảnh dữ liệu, cấu hình lịch, policy và trình xem file.

## Mức độ bao phủ bổ sung

- Playwright headless desktop 1366px đã mở 17 route chính: Danh mục, Thêm program, Profiles, Help, năm tab Program cùng các view URL/Host/Xếp hạng/Lịch sử/Brief/Scope/Export, Run #59, Review #57. Không có JS exception, HTTP API >=400 hay cuộn ngang ở các route này. Script: `review_tools/v134_full_ui_routes.py`.
- Raw scope preview `127.0.0.1` trên NewScan trả 1 IN và bật nút Resolve; không bấm Resolve.
- Form Profile mới mở được, plan preview tải xong, không có lỗi và chưa lưu profile.
- Các tương tác có kiểm tra chuyên biệt: URL latest/all, Host, Diff, schedule header trên DB tạm, raw policy qua rescan trên DB tạm, và Artifact Viewer với API giả. Script DB tạm: `docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm:/src:ro' -w /src bbasm-v12-bbasm -m review_tools.v134_policy_rescan_check`.
- Chưa kiểm toàn bộ tổ hợp thao tác: chỉnh/xóa profile, bật/tắt schedule trên stack người dùng, export/download mọi chế độ, mọi bộ lọc và phân trang, mobile/390px, H1 thật, Light/Strong thật, hơn 1.000 hàng, hỗ trợ trình duyệt khác. Không gọi là “đã kiểm toàn bộ sản phẩm”.
