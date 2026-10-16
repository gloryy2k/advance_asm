# Audit read-only: `arc-bbp` Strong scan #65

**Nguồn:** image/checkout v1.5.5 `42e3a0d`, stack `bbasm-v12` tại `127.0.0.1:18765`, 2026-10-16. Chỉ đọc API localhost, SQLite ở chế độ `mode=ro`, file output và UI qua Chrome headless 1366px. Không khởi chạy scan mới, không gọi HackerOne, không gửi request tới asset trong scope. Đây là audit chất lượng **kết quả và luồng BBASM**, không xác minh lỗ hổng trên target.

## Kết quả tổng quát

| Mục | Kết quả | Bằng chứng |
| --- | --- | --- |
| Trạng thái | **Hoàn tất một phần** | Scan #65 `strong`, 07:42:48–08:22:23 UTC (~39m34s), `done_partial`. `web.archive.org` timeout 45s; giai đoạn probe host đã khám phá timeout 1554s. |
| Scope/policy snapshot | Có, nhưng vẫn cần người dùng đối chiếu | `public_page`, IN 6/6, OUT 3/3, 0 chưa phân loại, `verified=false`. Ba host OUT (`community.arc.io`, `explorer.arc.io`, `help.arc.io`) và apex `arc.io` không nằm trong bảng asset. |
| Dữ liệu | Có nhưng thiếu phủ | 132 asset (129 web + 3 source code), 35 có HTTP, 97 không có mã HTTP; 489 URL (487 historical, 2 observed); diff 132 new, baseline null. |
| Findings | **Không được coi 138 mục là 138 lỗi thật** | 128 takeover High, 7 secret Medium đều chưa xác minh, 3 nuclei đã khử trùng từ 5 dòng thô. Một nuclei Critical là tín hiệu cần chuyên gia xác minh riêng, audit này không kết luận CVE thật. |
| Output | Được tạo | `AGENT_BRIEF.md` 6.509 byte (<12 KB), `PROGRAM.md` có `## Policy`; audit có `ack` và `scan_finished` cho #65. `/api/health` báo `ok=true`, không thiếu tool theo depth. |
| UI desktop | Tải được | Overview, Dữ liệu URL/Host/Xếp hạng/Cây sitemap, Findings, Lịch sử/Diff, Scope, Brief, Export, Run #65 tại 1366px: không lỗi JavaScript, không API 4xx/5xx ở các trang đã quan sát, không cuộn ngang. Ảnh tại `review_evidence/arc_bbp_strong/`. |

## Finding cần Claude xử lý

### F1 — P1: 124 kết quả “Not Vulnerable” bị nâng thành takeover High

**Tái hiện:** Mở `targets/arc-bbp/recon/scans/65/monitors/takeover/subjack.txt` trên máy chạy stack; 128 dòng gồm **124 `[Not Vulnerable]`** và 4 `[GEMFURY]`. DB và tab Phát hiện lại có 128 `takeover/high` cùng tên `subjack.txt:candidate`. Ví dụ dòng đầu là `[Not Vulnerable] cpcalendars.arc.io`, nhưng asset đó có finding High. Code `backend/asm/monitors.py` vòng đọc `subjack.txt` lấy domain từ *mọi* dòng; `vendor/claude-bug-bounty/tools/takeover_scanner.sh` cũng đếm mọi dòng là candidate.

**Tác động:** Overview, ma trận severity, Findings và Agent Brief bị nhiễu mạnh; High trở nên không đáng tin. **Hướng sửa:** parser nhận trạng thái của subjack, bỏ `[Not Vulnerable]`; chỉ lưu `[SERVICE]` như ứng viên chưa xác minh. Đếm và nhãn hiển thị theo số candidate hợp lệ, thêm fixture regression cho cả hai kiểu dòng. Dữ liệu #65 đã lưu cần tính lại hoặc gắn cờ số liệu cũ không chính xác, tránh UI tiếp tục hiển thị 128 High sau khi code sửa.

### F2 — P1: hướng dẫn “partial scope” của repo bị mất khi quét source code

**Tái hiện:** Scope IN của `repo:https://github.com/circlefin/malachite` có `instruction`: chỉ `code/crates`, trừ `starknet` và `test`; mọi chỗ còn lại OUT. Trong `backend/jobs/recon_orch.py::_source`, lệnh truyền URL repo nguyên vẹn qua `--git`; `vendor/claude-bug-bounty/tools/secrets_hunter.sh` gọi `trufflehog git <URL>` không có bộ lọc subpath. Output `65/1/trufflehog.jsonl` có 22 kết quả chưa xác minh từ chế độ quét git; metadata không đủ path để chứng minh từng kết quả đến từ thư mục nào.

**Tác động:** BBASM có thể đọc/quét phần repo ngoài phạm vi được program mô tả, trong khi Review cho mở Strong. **Hướng sửa:** không tự động quét repo có giới hạn subpath dạng văn bản khi chưa biểu diễn và cưỡng chế được điều kiện đó; đưa asset sang bước kiểm tay/khóa command tự động. Nếu hỗ trợ, kiểm soát path và lịch sử git ở tầng chạy tool, rồi ghi rõ độ phủ thực tế. Không chỉ lọc kết quả sau scan.

### F3 — P2: “đã probe 0” gây hiểu sai khi có output HTTP dở dang

**Tái hiện:** `/api/scans/65/phases` trả `coverage={discovered:126,probed:0,unprobed:126,batches:1,batches_done:0}` vì `_pipeline.done()` chỉ cập nhật khi **cả batch hoàn tất**. Batch timeout, nhưng `65/5/live/httpx_full.txt` có **33 dòng** và DB có tổng 35 host có mã HTTP (gồm hai host được nêu trực tiếp). Overview/Run vẫn nói “126 chưa probe”.

**Tác động:** Người đọc tưởng không host khám phá nào được probe; số liệu coverage không thể hiện kết quả dở dang đã nhập. **Hướng sửa:** tính riêng `attempted`, `responded`, `completed` từ output per-host; trạng thái batch timeout vẫn giữ, nhưng label không gọi các host đã có bằng chứng HTTP là “chưa probe”.

### F4 — P2: funnel ghi “456 trong scope (đang xem)” nhưng bảng có 489 URL

**Tái hiện:** `/api/programs/arc-bbp/urls/summary?scan=latest` trả `total=489`, `funnel.in_scope=456`. Trang Dữ liệu ghi “1.990 URL do tool tìm thấy → 456 trong scope (đang xem)”, trong khi bảng là 489. Trong `backend/jobs/ingest.py`, `funnel.in_scope` đếm vòng URL recon, còn URL `httpx` được thêm trước vòng đó; 33 URL `httpx` tạo chênh lệch.

**Hướng sửa:** tách nhãn “URL recon qua gate” và “URL HTTP bổ sung” rồi cho tổng khớp với bảng, hoặc điều chỉnh funnel đếm cùng tập dữ liệu mà UI khẳng định đang xem. Kiểm thử invariant tổng.

### F5 — P2: nhãn `auth` bắt nhầm URL nội dung có chữ “token”

**Tái hiện:** Dữ liệu URL gắn “đăng nhập” cho `/arc-token-whitepaper`, `/blog/...tokenization...`, `/ecosystem/imtoken`; code `backend/asm/urlintel.py::_AUTH` tìm chuỗi `token` ở bất kỳ vị trí nào trong path. Chín URL `auth` đều là lịch sử theo scan này, nhiều mục là bài viết.

**Tác động:** Điểm ưu tiên và “Việc nên làm tiếp” bị lệch. **Hướng sửa:** dùng segment/ranh giới từ hoặc mẫu endpoint xác thực cụ thể; “token” chỉ nâng điểm khi là endpoint (`/token`, `/oauth/token`) hoặc tham số liên quan, không phải từ trong nội dung. Thêm test với `tokenization`, `imtoken`, `arc-token-whitepaper`.

### F6 — P3: Diff scan đầu được diễn đạt như so với scan trước

**Tái hiện:** Scan #65 có `baseline_scan_id=null`, `diff.new=132`. Overview ghi “Xem 132 thay đổi so với scan trước”. Program chỉ có một scan.

**Hướng sửa:** với baseline null, dùng nhãn “132 asset khởi tạo”/“lần ghi nhận đầu”, không gọi là thay đổi so với scan trước.

## Giới hạn và lưu ý sử dụng kết quả

- Scan Strong dùng `threads=50`, `rate_limit=150`, timeout 2700s; audit này không xác định các giá trị đó phù hợp với policy thực tế. Snapshot scope có điều kiện “Only for Circle-owned assets” cho `*.arc.io`; BBASM chưa tự xác minh quyền sở hữu từng subdomain.
- 4 dòng `[GEMFURY]` của subjack là **ứng viên**, chưa phải takeover đã chứng minh. Bảy secret Medium có `verified=false`. Một nuclei Critical và hai Low cần xác minh thủ công trước khi kết luận/report; không tiếp tục probe target trong audit này.
- 97 asset không có mã HTTP không có nghĩa không tồn tại. `web.archive.org` đã timeout; giai đoạn deep là `empty`, crawl chỉ có 2 URL quan sát. Kết quả Strong này không đại diện cho độ phủ đầy đủ.
- Không có scan trước để đánh giá Diff xu hướng. Không có schedule cho program này.
- `AGENT_BRIEF.md` hiện mang tín hiệu takeover bị nhiễu bởi F1; Claude/agent hunt không nên ưu tiên 128 mục High trước khi parser và dữ liệu cũ được xử lý.

## Lệnh và bằng chứng có thể tái hiện, không chạm target

```text
GET http://127.0.0.1:18765/api/programs/arc-bbp/summary
GET http://127.0.0.1:18765/api/scans/65/phases
GET http://127.0.0.1:18765/api/programs/arc-bbp/urls/summary?scan=latest
docker compose -p bbasm-v12 ps
```

Các thống kê DB lấy bằng `sqlite3.connect('file:.../data/bbasm.db?mode=ro', uri=True)`, chỉ SELECT. File output đối chiếu: `targets/arc-bbp/recon/scans/65/monitors/takeover/subjack.txt`, `65/5/live/httpx_full.txt`, `65/4/nuclei/findings.jsonl`, `data/logs/65.jsonl`. Ảnh UI là bản headless localhost, không thao tác cửa sổ người dùng. Không commit DB, raw output, policy đầy đủ hay giá trị secret.
