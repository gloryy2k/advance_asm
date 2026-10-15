# Wolt H1 — kiểm metadata công khai và Passive trên BBASM v1.3.3

Ngày 15/10/2026. Image nguồn `9e6af8d`, stack QA `bbasm-v12` ở `127.0.0.1:18765`. Chỉ gọi metadata công khai của [Wolt trên HackerOne](https://hackerone.com/wolt/policy_scopes), không token/cookie; scan #43 là **Passive**, không probe HTTP/DNS/cổng hoặc chạy nuclei lên target. Không chạy Light/Strong.

| Mã | Hành động | PASS/FAIL/SKIP | Bằng chứng |
|---|---|---|---|
| H1-1 | Resolve `https://hackerone.com/wolt?type=team` qua BBASM | PASS | Draft #43, `policy.source=public_page`; API credential không cấu hình. Policy dài 6.182 ký tự. `completeness`: IN 12/12, OUT 12/12; 24 classified, 0 unclassified. 2 wildcard, 18 web, 4 mobile. |
| H1-2 | Đọc policy và Review trước khi chạy | PASS | Policy yêu cầu header `X-HackerOne-Research: [H1 username]` cho request tới target; cấm brute force và DoS. Review có `request_header_hints=["X-HackerOne-Research"]`, nhưng chưa có giá trị header. |
| H1-3 | Launch #43 Passive, `threads=1`, `rate_limit=1`, `scan_timeout=300`, các bước active tắt | **FAIL** | Passive không gửi HTTP request tới asset Wolt nên không cần header. Log: subfinder 719 subdomain, crt.sh 64; HTTP/DNS check và nmap bị skip. 12.508 URL, 759 asset và 329 diff event đã lưu, nhưng sau >10 phút vẫn `running`; event cuối ID 921 lúc 16:33:32 UTC, không có `done`. `docker compose top` chỉ còn backend. |
| H1-4 | `POST /api/scans/43/cancel` khi kẹt | **FAIL** | Client chờ 25 giây rồi `httpx.ReadTimeout`; GET status vẫn `running`. |
| H1-5 | `docker compose -p bbasm-v12 restart`; kiểm phục hồi | PASS | Container trở lại healthy; #43 chuyển `failed` (`Dashboard interrupted; create a new scan to retry`), không có process tool. 12.508 URL, 759 asset và 329 diff event vẫn trong DB QA. |
| H1-6 | Light/Strong Wolt | SKIP | Passive #43 bị kẹt nên chưa tiếp tục. Nếu bật bước gửi HTTP tới asset Wolt, cần kiểm yêu cầu header trong policy và điền username H1 thực. |

## Finding mới

### P1 — Wolt Passive không kết thúc sau khi đã nạp dữ liệu; Cancel không phản hồi

- **Tái hiện:** image `9e6af8d`, Resolve Wolt H1 công khai, launch Passive #43 với timeout 300 giây và các bước active tắt. Chờ >10 phút. Log dừng ở stage `main: ok` (event 921, 16:33:32 UTC); `docker compose top` không còn recon child. DB đã có 12.508 URL/759 asset/329 diff event, song status vẫn `running`. Gọi Cancel bị timeout sau 25 giây.
- **Ảnh hưởng:** Run kẹt dù dữ liệu đã nạp, không có brief/trạng thái cuối cho scan mới; nút Cancel không giải phóng được tác vụ qua API. Restart container phục hồi service nhưng đổi #43 thành `failed`.
- **Hướng sửa:** đo/giới hạn thời gian cho các bước sau `_pipeline` (ingest, diff, ranking, intel, brief); phát progress event cho từng bước; bảo đảm Cancel có đường thoát khi coroutine đang chờ I/O hoặc thread. Bổ sung integration với cỡ dữ liệu Wolt ~12,5k URL và xác nhận terminal event, timeout và cancel. Chưa kết luận bước cụ thể gây kẹt. Xếp hạng chạy trên bản sao DB cùng dữ liệu mất 2,55 giây, nên riêng hàm đó chưa tái hiện lỗi.

### P2 — Bước gửi HTTP của Light/Strong có thể chạy khi thiếu header policy

- **Tái hiện:** Review #43 có `request_header_hints=["X-HackerOne-Research"]`, `request_headers=[]`, nhưng `launch_gate.allowed_depths=["passive","light","strong"]`. Passive không bị ảnh hưởng vì không gửi HTTP tới asset Wolt. Light/Strong có thể bật httpx/crawl/nuclei và gửi request tới asset; policy Wolt yêu cầu username H1 thực trong header của những request đó.
- **Hướng sửa:** khi phát hiện header bắt buộc trong policy, hiển thị rõ việc thiếu giá trị ngay cạnh nút Launch và chặn bước chạm target hoặc buộc xác nhận riêng sau khi điền header. Không tự điền giá trị giả. Policy cũng cấm brute force/DoS; người dùng cần duyệt từng bước Strong trước khi cho chạy.

## Giới hạn và trạng thái bàn giao

- Một Resolve H1 công khai đã thành công qua provider; không dùng token/cookie, không đăng nhập. Nội dung policy đầy đủ không được đưa vào repo.
- Không có phép đo packet egress liên tục. Kết luận không probe dựa trên cấu hình Passive, log skip và `docker compose top`.
- Không chạy Light/Strong vì Passive #43 còn lỗi. Khi thử bước có request HTTP tới asset, cần chọn rate/steps và header theo policy hiện hành.
- Giữ stack `bbasm-v12` healthy ở `127.0.0.1:18765` cùng dữ liệu QA; không prune và không sửa code sản phẩm.
