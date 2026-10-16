# BBASM — việc để sau (đã đánh giá, chưa làm)

Nguyên tắc hiện tại: **hoàn chỉnh các chức năng đang có trước**, rồi mới thêm chức năng mới. Mục dưới đây là đánh giá độc lập
của `V134_PRODUCT_PROPOSALS.md` (nhánh `test/v134-host-results`, commit 296af57) đối chiếu với code `c11440d`.
Chưa có mục nào được triển khai, trừ khi ghi "ĐÃ LÀM".

## Đã làm (hoàn chỉnh chức năng cũ)
- Xác nhận bỏ qua header policy (P2 của V134_HOST_RESULTS): lưu theo tên header trong config nháp (`skipped_headers`),
  Review khôi phục từ config, nháp được lưu khi sửa, schedule kiểm tra lại lúc chạy, audit ghi tên (không ghi giá trị). Xem NOTES v1.3.5.

## Thứ tự đề xuất khi quay lại
1. **Mô hình trạng thái công cụ** — một hàm `tool_inventory(settings)`; hai trục `state` (ready / missing_binary / missing_data /
   wrong_binary / unverified) và `role` theo depth (bắt buộc / tùy chọn). `DEPTH_TOOLS` suy từ `phases.tools_needed`. Hook
   `useHealth()` dùng chung cho NewScan/Portfolio/Review/Run. Giữ `tools` + `missing_by_depth` của `/api/health`.
2. **Trang "Công cụ & môi trường"** `#/tools` (`GET /api/tools`, `POST /api/tools/check` chủ động, `-duc` + timeout; phiên bản
   ghim lấy offline từ `scripts/tool-releases.json`). Review/Run chỉ có liên kết `#/tools?focus=...`.
3. **Cập nhật Nuclei templates có chủ đích** — named volume (không bind mount: chậm/symlink trên Windows), biến
   `BBASM_NUCLEI_TEMPLATES`, tải vào staging rồi đổi tên nguyên tử, giữ bản trước, khóa single-flight, trạng thái bền trong
   `data/`, marker `.bbasm-templates.json` để health khỏi `rglob` 14k file, audit egress, ghi bộ template vào `stats_json` của scan.
   Quyết định cần chốt: `BBASM_UPDATE_TEMPLATES` lúc boot (chạy nền qua updater, hay mặc định 0); named volume hay `data/`.
4. **Loại tag nguy hiểm khỏi nuclei Light/Strong** (`dos`, `intrusive`, `bruteforce`, `fuzz`) — nuclei hiện chạy toàn bộ template
   theo severity; policy kiểu Wolt cấm brute-force.
5. **Dọn draft hàng loạt** — đã có xóa từng cái và tự xóa sau 7 ngày lúc boot (`purge_drafts`). Cần: lọc/sắp xếp, chọn tay,
   kiểm tra lại `status='draft'` trong transaction, Review xử lý draft đã bị xóa, ghi ngưỡng 7 ngày lên UI. Không tự chọn theo `qa-*`.
6. **Archive / restore program** — migration v4 `program.archived_at`; archive tạm dừng schedule và gỡ job APScheduler; từ chối khi
   có scan queued/running; endpoint ghi từ chối program đã archive; Resolve lại thì khôi phục lúc Launch (có audit).
7. **Xóa vĩnh viễn program** — xóa tường minh theo thứ tự con→cha (asset/url/finding/diff_event không có FK); đổi tên
   `targets/<slug>` → `.trash` trước, xóa DB, rồi xóa trash (khôi phục lúc boot nếu đứt giữa chừng); dọn log `data/logs/<id>.jsonl`
   và `_REPORT_CACHE` vì ID scan có thể được cấp lại; giữ bản `audit.jsonl`; `confirm_slug`; từ chối symlink/slug lạ.
8. **(P3) Import template riêng** — chỉ YAML tải lên, giới hạn kích thước, từ chối `code/javascript/headless/file` và host tuyệt đối,
   `nuclei -validate -duc`, bật theo program; cần shim ghép `-t` (engine hiện chạy nuclei không có `-t`).

## Còn dở trên chức năng hiện có (xử lý trước các mục trên)
- Strong chưa có xác nhận theo từng bước khi policy cấm brute-force (ffuf).
- `LogBuffer.emit` ghi file đồng bộ trên event loop (có thể chậm trên bind mount).
- `purge_drafts` xóa luôn draft không có dòng `scan_config` ở mỗi lần boot (`COALESCE(created_at,'')<cutoff`).
- Schedule bị `header_required` lúc dispatch chỉ ghi lỗi trong log tiến trình; chưa hiện trên trang Program.


## Đã chốt sau audit luồng input→output (không làm)
- R1–R7 (chặn request tới endpoint OUT theo đường dẫn): bỏ. Quy tắc của người dùng: **GET tới endpoint OUT trong domain được chấp nhận**, chỉ cần tránh POST/PUT/PATCH/DELETE. Giữ nguyên logic hiện tại (host có path OUT mặc định chỉ probe, có ô cho phép quét chủ động). Không merge phần hạn chế của commit `2d540fd` (xóa ô cho phép, ép probe-only vĩnh viễn).
- Còn nếu quay lại: nuclei là công cụ duy nhất có thể gửi request không phải GET (template POST) nên khi bật quét chủ động trên host có path OUT có thể cân nhắc `-fhr`; xóa URL OUT cũ trong DB. (F4, F5: ĐÃ LÀM, xem NOTES v1.3.8.)

## Visualization (thêm 2026-10-16, chưa làm)
**V1 — Sitemap dạng cây như Burp Suite (ưu tiên cao).** Tab Dữ liệu › URL có thêm chế độ "Cây sitemap" cạnh bảng hiện tại.
- Cây: host → thư mục → file (→ các biến thể query gộp thành một nút "?id=… N biến thể"). Mỗi nút có mũi tên mở/thu (▸/▾, bàn phím ←/→,
  `role="tree"`, `aria-expanded`), nút "Mở hết / Thu hết / Mở tới cấp N"; **sắp xếp A→Z** (host rồi từng cấp đường dẫn; tuỳ chọn thư mục trước file,
  hoặc theo điểm / số URL).
- Mỗi nút hiện số URL của cây con, điểm cao nhất, nhãn (api/auth/admin…), mức kiểm chứng (đã crawl / lịch sử), "mới", scan thấy lần đầu→gần nhất.
  Dùng chung bộ lọc và phạm vi scan (mới nhất / tất cả / tới scan N) của UrlExplorer; tìm kiếm tự mở các nhánh khớp.
- Quy mô (12k+ URL): API `GET /api/programs/{slug}/urls/tree?host=&prefix=&scan=` trả **một cấp con mỗi lần** (tải khi mở nút), tối đa ~200 con/nút kèm "xem thêm";
  lưu trạng thái mở trong URL/sessionStorage. Không có method/status/length cho mọi URL (httpx chỉ probe gốc) nên hiện mức kiểm chứng thay cho status.
- Hành động trên nút: chép URL, mở tab mới, (sau này) "loại trừ nhánh này" ghi vào lựa chọn loại trừ của program (liên quan F1).
- Tiêu chí: 12k URL không treo UI; sắp xếp ổn định; mở/thu bằng chuột và bàn phím; số cây con khớp bảng; test Vitest + test API cho một cấp con.

**V2 — Gợi ý cải thiện visualization khác (xếp theo giá trị):**
1. Xu hướng theo scan trên trang Program (đường host/URL/finding qua các scan; cột mới/đổi/mất mỗi scan) — dữ liệu có sẵn trong `stats_json` và `diff_event`.
2. Tổng quan: biểu đồ nhỏ phân bố mã trạng thái, top công nghệ, host theo số URL (treemap tuỳ chọn: diện tích = số URL, màu = điểm cao nhất).
3. Run: dòng thời gian (Gantt) các giai đoạn, ngân sách so với đã dùng — chẩn đoán kiểu Wolt #43.
4. Findings: ma trận mức nghiêm trọng × host.
5. Không làm: đồ thị quan hệ subdomain/IP (nặng, ít giá trị). Mọi biểu đồ tuân theo bảng màu/dark mode hiện có, không dùng màu làm tín hiệu duy nhất.

## Tính năng sau này (chưa triển khai): so sánh sitemap với Burp Suite
- Import sitemap xuất từ Burp (XML "save items", có thể cả "Copy URLs"), **chỉ giữ method/URL/status/length/mime, bỏ body request/response**; đọc dạng luồng,
  giới hạn kích thước, tắt entity ngoài; mọi URL phải qua cổng scope (`effective_gate`) và dữ liệu OUT bị bỏ, ghi nguồn `burp`.
- So sánh hai cây (BBASM vs Burp): chỉ có ở BBASM / chỉ có ở Burp / có ở cả hai (khác status/mime), khoá nút = host + đường dẫn chuẩn hóa + tên tham số.
  Xem dưới dạng cây có màu + bảng, xuất danh sách khác biệt. Thiết kế V1 để API cây chấp nhận nguồn dữ liệu bất kỳ (scan hoặc import).
