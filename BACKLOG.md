# BBASM — việc để sau (đã đánh giá, chưa làm)

Nguyên tắc hiện tại: **hoàn chỉnh các chức năng đang có trước**, rồi mới thêm chức năng mới. Mục dưới đây là đánh giá độc lập
của `V134_PRODUCT_PROPOSALS.md` (nhánh `test/v134-host-results`, commit 296af57) đối chiếu với code `c11440d`.
Chưa có mục nào được triển khai, trừ khi ghi "ĐÃ LÀM".

## Đã làm (hoàn chỉnh chức năng cũ)
- Xác nhận bỏ qua header policy (P2 của V134_HOST_RESULTS): lưu theo tên header trong config nháp (`skipped_headers`),
  Review khôi phục từ config, nháp được lưu khi sửa, schedule kiểm tra lại lúc chạy, audit ghi tên (không ghi giá trị). Xem NOTES v1.3.5.

## Thứ tự đề xuất khi quay lại — ĐÃ LÀM HẾT (2026-10-16)
Mục 1–8 cũ (trạng thái công cụ, trang Công cụ, cập nhật Nuclei templates, loại tag nguy hiểm, dọn draft hàng loạt, archive/restore,
xóa vĩnh viễn, import template riêng) đã xong: xem NOTES v1.5.0–v1.5.3.

## Còn dở trên chức năng hiện có
Không còn mục nào (A3–A7 và hiển thị lỗi lịch đã xử lý, xem NOTES v1.3.8–v1.5.0).


## Đã chốt sau audit luồng input→output (không làm)
- R1–R7 (chặn request tới endpoint OUT theo đường dẫn): bỏ. Quy tắc của người dùng: **GET tới endpoint OUT trong domain được chấp nhận**, chỉ cần tránh POST/PUT/PATCH/DELETE. Giữ nguyên logic hiện tại (host có path OUT mặc định chỉ probe, có ô cho phép quét chủ động). Không merge phần hạn chế của commit `2d540fd` (xóa ô cho phép, ép probe-only vĩnh viễn).
- Còn nếu quay lại: nuclei là công cụ duy nhất có thể gửi request không phải GET (template POST) nên khi bật quét chủ động trên host có path OUT có thể cân nhắc `-fhr`; xóa URL OUT cũ trong DB. (F4, F5: ĐÃ LÀM, xem NOTES v1.3.8.)

## Visualization (thêm 2026-10-16, chưa làm)
**V1 — Sitemap dạng cây như Burp Suite — ĐÃ LÀM (NOTES v1.4.0; còn: nhớ trạng thái mở, chọn nhiều nút).** Tab Dữ liệu › URL có thêm chế độ "Cây sitemap" cạnh bảng hiện tại.
- Cây: host → thư mục → file (→ các biến thể query gộp thành một nút "?id=… N biến thể"). Mỗi nút có mũi tên mở/thu (▸/▾, bàn phím ←/→,
  `role="tree"`, `aria-expanded`), nút "Mở hết / Thu hết / Mở tới cấp N"; **sắp xếp A→Z** (host rồi từng cấp đường dẫn; tuỳ chọn thư mục trước file,
  hoặc theo điểm / số URL).
- Mỗi nút hiện số URL của cây con, điểm cao nhất, nhãn (api/auth/admin…), mức kiểm chứng (đã crawl / lịch sử), "mới", scan thấy lần đầu→gần nhất.
  Dùng chung bộ lọc và phạm vi scan (mới nhất / tất cả / tới scan N) của UrlExplorer; tìm kiếm tự mở các nhánh khớp.
- Quy mô (12k+ URL): API `GET /api/programs/{slug}/urls/tree?host=&prefix=&scan=` trả **một cấp con mỗi lần** (tải khi mở nút), tối đa ~200 con/nút kèm "xem thêm";
  lưu trạng thái mở trong URL/sessionStorage. Không có method/status/length cho mọi URL (httpx chỉ probe gốc) nên hiện mức kiểm chứng thay cho status.
- Hành động trên nút: chép URL, mở tab mới, (sau này) "loại trừ nhánh này" ghi vào lựa chọn loại trừ của program (liên quan F1).
- Tiêu chí: 12k URL không treo UI; sắp xếp ổn định; mở/thu bằng chuột và bàn phím; số cây con khớp bảng; test Vitest + test API cho một cấp con.

**V2 — biểu đồ — ĐÃ LÀM (NOTES v1.5.4):** xu hướng theo scan, phân bố mã trạng thái/công nghệ/host theo số URL, ma trận mức nghiêm trọng × host, thanh thời gian dùng/ngân sách từng giai đoạn ở trang Run.
Không làm: đồ thị quan hệ subdomain/IP (nặng, ít giá trị); treemap diện tích (thanh ngang đủ so sánh và đọc được bằng chữ).

## Tính năng sau này (chưa triển khai): so sánh sitemap với Burp Suite
- Import sitemap xuất từ Burp (XML "save items", có thể cả "Copy URLs"), **chỉ giữ method/URL/status/length/mime, bỏ body request/response**; đọc dạng luồng,
  giới hạn kích thước, tắt entity ngoài; mọi URL phải qua cổng scope (`effective_gate`) và dữ liệu OUT bị bỏ, ghi nguồn `burp`.
- So sánh hai cây (BBASM vs Burp): chỉ có ở BBASM / chỉ có ở Burp / có ở cả hai (khác status/mime), khoá nút = host + đường dẫn chuẩn hóa + tên tham số.
  Xem dưới dạng cây có màu + bảng, xuất danh sách khác biệt. Thiết kế V1 để API cây chấp nhận nguồn dữ liệu bất kỳ (scan hoặc import).

## Còn mở sau audit arc-bbp #65 (xem ARC_BBP_TRIAGE.md, mục “Cần quyết định”)
1. Cưỡng chế giới hạn thư mục của repo (trufflehog `--include-paths`, sửa `secrets_hunter.sh` ở submodule); hiện chỉ khóa + xác nhận cả repo.
2. “Probe tiếp” phần chưa quét từ `stats.unprobed_hosts`: cần chốt ngữ nghĩa diff/Brief/lịch.
3. Adapter riêng cho mobile / source code (SAST, dependency) / other (smart contract, cloud, ASN…), quyền theo từng asset.
4. Nhập kết quả ffuf và nmap vào bảng dữ liệu có cấu trúc (tab “Đường dẫn dò được”, “Cổng/Dịch vụ”).
5. Ngân sách tự co giãn theo số host khám phá.
6. Sửa `open_ports.txt` ở engine (submodule): parse đúng từng cặp host/cổng (BBASM đã bù ở tầng đọc).

## Độ phủ nuclei (NUCLEI_COVERAGE_FOLLOWUP.md → NOTES v1.6.1/v1.6.2) — quan sát đã sửa, giới hạn vẫn chờ quyết định
**Đã sửa (quan sát, không đổi giới hạn):** `recon_engine.sh` giờ ghi `nuclei/coverage.json` (URL thật đưa vào, bị cắt bao nhiêu, template/request nuclei tự báo, timeout, lỗi); Run hiện số thật thay vì chỉ "14.036 template đã cài". Xem chi tiết NOTES v1.6.1, v1.6.2.
**Chưa làm — cần quyết định:**
- Giới hạn cứng **50 URL/lượt (quick) hoặc 200 (full)** cho mỗi lệnh nuclei vẫn còn (`NUC_LIMIT` trong `recon_engine.sh`). Một scan Strong có hàng trăm URL sống vẫn chỉ nuclei được một phần mỗi lượt. Phương án: (a) giữ nguyên, chỉ hiện rõ số bị bỏ (hiện trạng); (b) tăng giới hạn kèm siết `-maxtime`/`-rl`; (c) thêm vòng "nuclei tiếp" trên phần chưa được đưa vào — nên làm cùng lúc với mục 2 ("Probe tiếp") ở trên nếu chọn hướng này, không làm hai lần.
- Chưa đo `nuclei/stats.jsonl` phình bao nhiêu ở một scan Strong dài thật (~1800s); chỉ đo được tới ~44s trên fixture.
- Chưa chạy một scan Strong **qua orchestration thật** (nhiều lệnh nuclei trong 1 scan, main + deep) để xác nhận gộp đúng ngoài fixture ghép tay.
