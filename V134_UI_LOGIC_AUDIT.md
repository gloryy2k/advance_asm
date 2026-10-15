# Rà soát logic UI/UX sau scan Wolt #59

Ngày 2026-10-16; code nguồn `c11440d`, nhánh kết quả `test/v134-host-results`. Chỉ đọc API/Playwright headless tại `127.0.0.1`; riêng test schedule dùng DB tạm và container `--network none`. Không chạy scan, không gọi H1, không sửa/xóa dữ liệu Wolt hay code sản phẩm. Số liệu dưới đây là snapshot của stack QA tại lúc kiểm tra.

| ID | Mức | Kết luận và bằng chứng | Tái hiện / hướng sửa |
| --- | --- | --- | --- |
| UI-1 | P1 | **Tab URL tạo cảm giác mất dữ liệu.** Scan Wolt #59 `done`, `url_history=empty`, 0 URL; `/api/programs/wolt/urls/summary` trả `total=0`. `/api/programs/wolt/urls?scan=all&min_score=0` vẫn trả 12.448 URL (505 URL với `min_score=1`). `/#/program/wolt/data` mặc định vào URL và Playwright thấy 0 hàng, thông báo “Không có URL phù hợp”. | Mở route trên sau scan mới không có URL. Thêm lựa chọn “Scan mới nhất / Tất cả scan” (backend đã nhận `scan=all`), ghi scan ID và thời gian/nguồn trên danh sách; khi latest=0 mà history>0, hiện CTA xem lịch sử thay vì nói “chưa có URL”. Đừng ngầm trình bày URL cũ như kết quả scan mới. |
| UI-2 | P1 | **Link kết quả từ Run cũ mất ngữ cảnh scan.** Scan Wolt #31 có phase `url_history=ran`, count 4.667. `Run.tsx` dùng `dataLink(slug, phase.view)` để mở Program URL; link này không mang scan ID và chuyển vào danh sách latest của #59, hiện trống. | Mở `/#/scan/31`, bấm “Xem URL” ở bước URL lịch sử. Truyền scan ID trong link và hỗ trợ lọc URL theo scan, hoặc mở artifact của đúng scan. Cùng nguyên tắc cho nút “Xem Brief” trên Run cũ: nêu rõ nếu đó là brief hiện hành của program. |
| UI-3 | P1 | **Bật giám sát Light không dùng header đã lưu.** Với policy giả yêu cầu `X-HackerOne-Research`, lưu header qua `PUT /api/programs/<slug>/request-headers`; summary trả header đúng. `Program.tsx` chỉ POST `{interval,depth,enabled}`; `backend/api/programs.py:schedule` tạo `default_config` không có header, nên API trả HTTP 422 `header_required`. Đã tái hiện bằng `review_tools/v134_schedule_ui_check.py` trên DB tạm, không launch scan. | Program có header mặc định → chọn Light, tick xác nhận → “Bật giám sát”. Backend cần áp header mặc định vào cấu hình lịch (hoặc UI truyền config đúng) và hiển thị rõ header/rate limit/depth trước khi bật. Test cả bật, cập nhật và tick thật; không dùng policy/H1 thật. |
| UI-4 | P2 | **“Host đang hoạt động” bị hiểu là live.** Tổng quan Wolt ghi `944 Host đang hoạt động`; API trả 944 asset `state=active` nhưng 940 không có `status_code`, và scan #59 là Passive (không probe HTTP). `active` ở đây là trạng thái inventory, không chứng minh host trả lời HTTP. | Mở Tổng quan/Dữ liệu → Host của Wolt. Đổi nhãn thành “Host trong inventory/được quan sát”, tách số `HTTP live`, `chưa probe`, `biến mất`; trong bảng, hiển thị “chưa kiểm tra” thay cho dấu gạch ngang mơ hồ. |
| UI-5 | P2 | **Thông báo Diff trống nêu sai lý do.** Program QA `qa-v121-diff` có scan #17 và #19 hoàn tất, `baseline_scan_id=17`, Diff tổng 0. Playwright tại `/#/program/qa-v121-diff/history?v=diff` vẫn hiện “Diff xuất hiện sau khi program có từ hai scan hoàn tất.” | Nếu có baseline và diff=0, hiển thị “Đã so sánh #19 với #17: không phát hiện thay đổi”; chỉ dùng thông báo cần 2 scan khi thật sự thiếu baseline. |

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

Không có dữ liệu Wolt nào bị dọn trong lần rà soát này; API vẫn truy cập được URL lịch sử và host. Các finding là về cách UI chọn/ngữ cảnh hóa dữ liệu và cấu hình lịch.
