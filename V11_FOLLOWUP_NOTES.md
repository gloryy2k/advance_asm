# v1.1 — follow-up H1, Passive và Active

Ngày 2026-10-14. Bằng chứng từ Docker QA `bbasm-v11` trên `127.0.0.1:18765`; không ghi token. Đây là backlog kiểm thử/cải thiện, không thay đổi code sản phẩm.

## H1 URL `verisk_vdp`

- URL có `?type=team` được chuẩn hóa đúng thành handle `verisk_vdp` (PASS).
- Không có H1 API credentials: provider dùng `public_dump` (`bounty-targets-data`). Resolve trả hai mục IN dạng wildcard; Review ghi `policy_text` rỗng và cảnh báo nguồn công khai có thể cũ/thiếu policy. `PROGRAM.md` yêu cầu người dùng đối chiếu policy chính thức. Vì vậy **chưa thể kết luận scope trả về đúng và đầy đủ**, cũng chưa tự động lấy được guideline/policy đầy đủ từ URL này.
- Draft scan #8 được giữ ở trạng thái `draft`; không launch vì chưa xác nhận được điều kiện automation từ policy chính thức. Không tự suy quyền scan từ việc URL resolve thành công.
- **Cần hoàn thiện (P1):** khi H1 API không khả dụng, làm rõ trạng thái “scope chưa xác minh / policy thiếu” ngay ở Review; cung cấp đường dẫn và các bước đối chiếu chính thức, không trình bày nguồn dump như scope đã xác nhận. Khi có API credentials hợp lệ, dùng cấu trúc policy/scope của H1 để điền đầy đủ `PROGRAM.md` và kiểm IN/OUT từng asset. Thêm test với public dump thiếu policy và API trả policy thật.
- **Tiêu chí nghiệm thu:** Review hiển thị `source`, `fetched_at`, mức độ đầy đủ, cảnh báo rõ; policy chính thức hoặc policy người dùng dán có trong `PROGRAM.md`; không cho người dùng hiểu nhầm metadata công khai là policy/authorization cho active scan.

## Passive raw scope `vuihoc.vn`

- Scan #9 `done`: 1 asset (`vuihoc.vn`), 0 live, 0 findings; `stats.urls=8836`, `stats.observed=8837`, brief chỉ 817 byte. Không có wildcard trong scope nên các subdomain/historical host khác không được nhận làm asset. Passive bỏ HTTP/DNS live probe, nmap, nuclei, crawl; vì vậy không có tech, trạng thái live hay finding xác nhận.
- Recon artifacts đã có URL lịch sử: `gau.txt` ~829 KB, `all.txt` ~744 KB, `with_params.txt` ~63 KB, `js_files.txt` ~18 KB, cùng file API/sensitive paths. Brief chỉ cho tổng URLs, 1 host và gợi ý chung; UI Assets hiển thị host, không có danh sách URL có lọc/tìm kiếm. Đây là lý do cảm giác “ít thông tin” dù đã thu được nhiều dữ liệu thô.
- Nguồn lịch sử có 223 dòng URL thuộc 3 host ngoài scope. Scope gate không nhận các host đó vào assets; ZIP `include_recon=true` vẫn chứa recon thô. Người dùng cần biết rõ sự khác nhau giữa raw recon và dữ liệu đã qua scope gate.
- **Cần hoàn thiện (P1):** thêm view URL/endpoints được scope gate chấp nhận, phân trang/lọc theo API, tham số, JS, đường dẫn nhạy cảm; hiển thị số URL thô, hợp lệ, ngoài scope, trùng lặp. Brief chọn tối đa N URL/endpoint nổi bật kèm lý do và đường dẫn tới artifact, giữ <12 KB. Không biến URL lịch sử thành “live” hay finding khi chưa kiểm chứng.
- **Cần hoàn thiện (P2):** làm rõ Passive chỉ là OSINT/historical, không probe live; đưa mô tả này vào Review và màn kết quả. Xem lại xuất ZIP: cảnh báo hoặc tùy chọn chỉ xuất recon đã lọc scope, để tránh bàn giao dữ liệu ngoài scope trong `recon/`.
- **Tiêu chí nghiệm thu:** với dữ liệu scan #9, người dùng xem được các URL/endpoint trong scope thay vì chỉ một host; số liệu funnel khớp artifacts, 0 live/0 finding vẫn được ghi đúng; export có nhãn rõ dữ liệu thô và dữ liệu đã lọc.

## Active scan — giới hạn tốc độ bị bỏ qua ở katana (P1)

- Người dùng yêu cầu test active; mặc định chỉ `vuihoc.vn` vì Verisk chưa xác minh được policy/scope đầy đủ. Tạo rescan #10 với scope snapshot đúng một host IN `vuihoc.vn`; config Light, `threads=1`, `rate_limit=1`, timeout 600s, `skip_nmap=true`, `skip_nuclei=true`, `skip_active_crawl=false`, `automation_ack=true`.
- **Phát hiện:** `docker compose -p bbasm-v11 top` trong lúc chạy cho thấy `katana ... -field-scope fqdn ... -c 50 -p 20` dù Review/scan config đặt 1 thread và rate limit 1. Trong `vendor/claude-bug-bounty/tools/recon_engine.sh`, phase URL Collection hard-code `-c 50 -p 20` (khoảng dòng 450); `backend/jobs/recon_orch.py` có truyền `BB_THREADS`/`BB_RATE_LIMIT`, nhưng katana không dùng hai giá trị này. Đây là lỗi P1 về giới hạn lưu lượng/độ tin cậy của Review. Không kết luận lưu lượng thực tế là 50/20 req/s, nhưng cấu hình tiến trình cho phép vượt mức đã chọn.
- **Hành động:** POST `/api/scans/10/cancel` ngay khi phát hiện; API trả `cancelled`; `docker compose top` sau hủy chỉ còn init và backend, không còn katana/recon_engine. Không tiếp tục crawl với cấu hình này.
- **Hướng sửa:** truyền giới hạn người dùng vào katana (`-c` và `-p`/rate flag phù hợp phiên bản), có cap bảo thủ; thêm integration test kiểm argv thực tế ở Light/Strong với `threads=1`, `rate_limit=1`; Review phải hiển thị công cụ nào chưa áp dụng được rate limit và không launch preset vi phạm. Không sửa code sản phẩm trong phiên QA.
- **Bước tiếp theo đã thực hiện:** chạy lại Light với HTTP probe có `-threads 1 -rate-limit 1`, tắt active crawl, nmap và nuclei; kết quả scan mới ở phần bên dưới. Phần katana/nuclei/nmap chưa thể xác nhận an toàn trong phiên này.

### Light giới hạn thêm — JS monitor không tuân rate limit (P1)

- Người dùng xác nhận **chỉ `vuihoc.vn`**. Rescan #11 dùng đúng một IN `vuihoc.vn`; Light, `threads=1`, `rate_limit=1`, timeout 600s, tắt katana crawl/nmap/nuclei, `automation_ack=true`.
- HTTP probe của scan #11 đã chạy và ghi `https://vuihoc.vn [200]`, title cùng tech fingerprint vào `live/httpx_full.txt`. Lệnh httpx trong `recon_engine.sh` dùng `-threads "$THREADS" -rate-limit "$RATE_LIMIT"`; đây là phần active có bằng chứng đúng cấu hình.
- Runner sau đó tự chạy `secrets_hunter.sh --js-bundle` (monitor). Script lấy tối đa 100 URL JS đã lọc scope rồi gọi `curl -sk --max-time 10` từng URL **không có sleep/rate limiter**. `docker compose top` xác nhận curl tới cùng host; artifact có 100 JS bundle. Cấu hình `rate_limit=1` không áp dụng cho bước này. Số request thực tế mỗi giây chưa đo được, vì vậy không khẳng định tốc độ thực đã vượt 1 req/s, nhưng không có cơ chế bảo đảm giới hạn người dùng chọn.
- **Hành động:** POST `/api/scans/11/cancel`; API trả `cancelled`. `docker compose top` sau hủy chỉ còn init/backend, không còn recon hoặc monitor subprocess. Docker tiếp tục healthy cho người dùng xem. Không chạy thêm active scan trên domain ngoài khi rate limit chưa áp cho mọi bước.
- **Hướng sửa:** áp rate limiter chung cho JS downloader và mọi HTTP-capable monitor; hoặc thêm cờ rõ ràng để bỏ monitor trong Review. Kiểm số request thực tế bằng HTTP fixture localhost trong integration test khi đặt `rate_limit=1`, bao phủ katana, JS downloader, httpx và mọi công cụ active; test cancel giữa monitor. Cập nhật UI để không hứa giới hạn toàn scan khi chỉ một số tool tôn trọng.
- **Trạng thái nghiệm thu:** active cơ bản HTTP probe **PASS giới hạn**; Light end-to-end **chưa PASS** vì scan #10 và #11 phải hủy an toàn. Katana, JS monitor, nuclei/nmap và findings chưa thể xác nhận đầy đủ trên target này.
