# Dữ liệu đánh giá scan #9–#12

Ngày 2026-10-14. Target đã nhập là đúng host `vuihoc.vn` (raw scope), program `qa-vuihoc-v11`. Dữ liệu runtime gốc vẫn ở **worktree Docker QA trên máy này**, không nằm trong checkout Git thông thường:

- `E:\code\bbasm\advance_asm-v11test\targets\qa-vuihoc-v11\recon\scans\9\` đến `...\12\`: output các bước recon, gồm URL lịch sử, HTTP probe và output monitor.
- `E:\code\bbasm\advance_asm-v11test\data\bbasm.db`: bảng `scan_run`, `scan_config`, `asset`, `url`, `finding`, `diff_event`.
- `E:\code\bbasm\advance_asm-v11test\targets\qa-vuihoc-v11\AGENT_BRIEF.md`, `PROGRAM.md`, `.scope`, `audit.jsonl`: trạng thái workspace hiện tại. `AGENT_BRIEF.md` đã được scan #12 ghi lại, không còn là bản riêng của #9.

File máy đọc [review_evidence/v11_scan_9_12.json](review_evidence/v11_scan_9_12.json) là **bản xuất để review** từ SQLite và cây artifact. Nó chứa từng scan, cấu hình, trạng thái, số liệu, danh mục file với bytes/số dòng/số dòng duy nhất/SHA256, phân bố exact-scope so với host khác, toàn bộ các nhóm URL đã chuẩn hóa và tên tham số query kèm tần suất. Hash cho phép đối chiếu với file gốc trên máy này. Không có URL đầy đủ, giá trị query, nội dung JS, token, đường dẫn tuyệt đối, hay tên host ngoài scope. Đường dẫn URL được gom tối đa ba segment; segment số, dài, Unicode hoặc ký tự đặc biệt thay bằng `*`. Vì vậy bản xuất **không đủ để tái dựng hay xác minh từng URL cụ thể**; cần file gốc local nếu Claude được chạy trên cùng máy và có quyền đọc worktree QA.

## Tóm tắt từ DB và artifact

| Scan | Mức/trạng thái | Cấu hình | DB sau scan | Output đáng chú ý |
| --- | --- | --- | --- | --- |
| **#9** | Passive, `done` | threads 1, rate 1, 300s; bỏ active crawl/nmap/nuclei | observed 8837, subs 1, live 0, URLs 8836, findings 0; diff `new=1` | `gau.txt` 10.306 dòng, 9.332 dòng duy nhất; `all.txt` 9.332 URL raw; 295 JS URL, 786 URL có tham số, 5 API endpoint, 18 sensitive path. Brief #9 817 byte. |
| **#10** | Light, `cancelled` | threads 1, rate 1, 600s; active crawl bật, nmap/nuclei tắt | Chưa ingest kết quả cuối vì đã hủy | HTTP probe có 1 dòng live. `katana.txt` 14.174 dòng nhưng chỉ 796 duy nhất, gồm nhiều host ngoài exact scope. Tiến trình katana chạy `-c 50 -p 20`; hủy khi phát hiện cấu hình không tuân giới hạn đã chọn. |
| **#11** | Light, `cancelled` | threads 1, rate 1, 600s; active crawl/nmap/nuclei tắt | Chưa ingest kết quả cuối vì đã hủy | HTTP probe có 1 dòng live. Monitor nhận 284 JS URL exact scope, tải 100 bundle (~13 MB) bằng `curl` không có rate limiter; hủy khi phát hiện. `regex_hits.txt` và `trufflehog.jsonl` rỗng tại thời điểm hủy. |
| **#12** | Light giới hạn thêm, `done` | threads 1, rate 1, 600s; active crawl/nmap/nuclei tắt; monitor tải JS/takeover tắt tạm trong container QA rồi khôi phục | observed 8722, subs 1, live 1, URLs 8721, findings 0; diff `new=0, changed=0, gone=0` | HTTP 200 của `vuihoc.vn`, có tech fingerprint; `all.txt` 9.210 URL raw; 295 JS URL, 775 URL có tham số, 5 API endpoint, 17 sensitive path. Brief #12 888 byte. |

Các file `all.txt` là output thô từ tool, không đồng nghĩa với số URL hợp lệ đã ingest: #9 có 9.109 dòng exact host, 221 dòng `www` và 1 dòng từ subdomain khác; còn 1 dòng không parse được. #11/#12 có 8.988 dòng exact host, 221 dòng `www`, 1 dòng không parse được. DB cuối có 8.836 URL duy nhất cho program. Phạm vi nhập chỉ là host `vuihoc.vn`, vì vậy `www`/subdomain khác không tự được xem là IN. Cần kiểm từng bước gate nếu muốn giải thích chênh lệch giữa output thô và `stats.urls`.

## Điều cần Claude đánh giá

1. **Hiệu quả Passive:** 8.836 URL đã ingest nhưng Brief/UI gần như chỉ cho một host và tổng số; xem nhóm URL đã chuẩn hóa trong JSON để đề xuất phân loại tín hiệu hữu ích, không gắn nhãn live cho URL lịch sử.
2. **Chất lượng và scope của output:** `katana` #10 có nhiều dòng trùng và host ngoài exact scope; kiểm bước lọc trước ingest/export và bảo đảm không gửi active request tới host ngoài scope. File JSON chỉ cho phân bố, không chứa raw URL.
3. **Giới hạn tốc độ toàn pipeline:** xem `V11_FOLLOWUP_NOTES.md` để biết bằng chứng argv katana và JS monitor. #12 chỉ xác nhận HTTP probe giới hạn; **không đại diện full Light**.
4. **Diff:** Passive #9 không có HTTP status, Light #12 có HTTP 200/tech nhưng tổng changed bằng 0, sau hai scan bị hủy. Cần kiểm thuật toán baseline và tiêu chí thay đổi.
5. **Brief:** #12 chỉ 888 byte cho 8.721 URL; nên chọn một số URL/endpoint đáng xem kèm provenance, giữ dưới 12 KB và tránh cắt chuỗi tech giữa JSON.

Không commit `data/`, `targets/`, JS bundle, raw URL, token hay key. Docker QA vẫn chạy tại `127.0.0.1:18765` để người dùng kiểm tra. Kết luận và bước tái hiện chi tiết ở [V11_FOLLOWUP_NOTES.md](V11_FOLLOWUP_NOTES.md).
