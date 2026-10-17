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
Không còn mục nào cũ (A3–A7 và hiển thị lỗi lịch đã xử lý, xem NOTES v1.3.8–v1.5.0).

**(Mới, nghiêm trọng) Scan có thể kẹt vĩnh viễn ở "running" nếu ghi trạng thái cuối thất bại** — bắt quả tang trực tiếp trên scan #67 (`verisk-vdp`, 2026-10-18): pipeline chạy xong thật (ingest/monitors/diff OK, rank timeout 300s — bình thường), nhưng `_finalize()` (`runner.py`) thử ghi trạng thái cuối 4 lần đều gặp `OperationalError`, log "Không ghi được trạng thái cuối", rồi im bặt — **0 tiến trình recon nào còn chạy** (kiểm `/proc` trong container) nhưng DB vẫn ghi `status=running` mãi mãi, không agent/UI nào biết scan đã chết. `_worker()` có fallback ghi `status=failed` khi `_execute()` raise, nhưng fallback đó tự nó cũng là một lần ghi DB có thể gặp lỗi tương tự mà không có retry — nếu fail tiếp thì mất luôn, không terminal state nào được ghi. Chưa xác định chắc chắn nguyên nhân gốc của `OperationalError` (nghi SQLite lock dưới tải ghi đồng thời, dù đã `PRAGMA journal_mode=WAL` + `sqlite3.connect(timeout=30)`). Hướng sửa: (1) fallback trong `_worker()` cũng cần retry giống `_finalize()`, không raise tiếp nếu fail; (2) cân nhắc thêm cơ chế "scan running quá X giờ không cập nhật log → coi là treo, UI cảnh báo" độc lập với `JobRunner.recover()` (chỉ chạy lúc khởi động lại dashboard).

**Audit recon_engine.sh (2026-10-18, chưa làm — xem NOTES v1.6.10 cho phần đã sửa cùng đợt audit này):**
- **Phase 10 "Subdomain Takeover Quick-Check" (CNAME-fingerprint qua `dig`) hoàn toàn mồ côi** — chạy mỗi scan Light/Strong (tới 500 subdomain tuần tự ở Full), ghi `takeover_candidates.txt`, nhưng **không có chỗ nào trong backend đọc file này** (đã grep toàn bộ, 0 kết quả). Trùng chức năng với bước "Takeover" chính thức (subjack+dnsreaper qua `Monitors`) đã có và hiện đúng trong UI. Tốn thời gian thật, không mang lại gì. Hướng sửa: xoá hẳn Phase 10 khỏi `recon_engine.sh`.
- **ffuf (Dò thư mục) chỉ fuzz 2 (Quick)/5 (Full) host đầu của `live/urls.txt`** — hardcode, không có config nào nâng lên được (khác `nmap_timeout`/`ffuf_maxtime`/`deep_hosts` đã có ô nhập), và UI không cảnh báo số host bị bỏ qua. Cùng loại vấn đề D1 từng sửa cho nuclei. Hướng sửa: thêm `BBASM_FFUF_HOSTS`/`ScanConfig.ffuf_hosts` theo đúng mẫu `nuclei_timeout`, Run page nói rõ "chỉ X/Y host được dò".
- **katana (Crawl chủ động) hardcode `head -50`** trên `live/urls.txt` — hiện bị che vì `deep_hosts` mặc định cũng là 50, nhưng nếu người dùng tăng `deep_hosts` (tối đa 200) thì katana vẫn chỉ crawl 50 host đầu, không theo kịp.
- (Nhẹ) "File cấu hình lộ" chỉ kiểm 30 host đầu, "Phân tích JavaScript" (bản regex thô, khác bước "Bí mật trong JS"/trufflehog chính thức đã có `max_js_files` cấu hình được) chỉ 50 file JS đầu — đều hardcode, không disclose trong UI. Ưu tiên thấp, đây là các bước phụ/rẻ.


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
4. ~~Nhập kết quả ffuf và nmap vào bảng dữ liệu có cấu trúc (tab “Đường dẫn dò được”, “Cổng/Dịch vụ”).~~ **ĐÃ LÀM (NOTES v1.6.3, UX-1):** `GET /api/programs/{slug}/ports|/dirs` + 2 tab trong Dữ liệu.
5. Ngân sách tự co giãn theo số host khám phá.
6. ~~Sửa `open_ports.txt` ở engine (submodule): parse đúng từng cặp host/cổng (BBASM đã bù ở tầng đọc).~~ **ĐÃ LÀM (NOTES v1.6.3, ENG-1).**

## Độ phủ nuclei (NUCLEI_COVERAGE_FOLLOWUP.md → NOTES v1.6.1–v1.6.7) — D1 đã chốt và làm xong
**Đã sửa:**
- `recon_engine.sh` ghi `nuclei/coverage.json` (URL thật đưa vào, bị cắt bao nhiêu, template/request nuclei tự báo, timeout, lỗi); Run hiện số thật thay vì chỉ "14.036 template đã cài" (NOTES v1.6.1, v1.6.2).
- Đo `nuclei/stats.jsonl` ở fixture dài thật ~322s (66 dòng/11.794 byte, ngoại suy 1800s ≈ 64 KiB — không phình bất thường) và xác nhận scan Strong qua orchestration thật (main+deep) gộp đúng — QA Codex `test/v163-host-audit`, PASS cả hai (xem COORD_TASKS.md lịch sử).
- **Lọc thông minh hơn — phương án B (auto-select theo công nghệ, `-as`):** `ScanConfig.nuclei_auto_select`, panel tra cứu template theo tag (`GET /api/tools/templates/lookup`), file `nuclei/templates_loaded.txt` (từ `-vv`) để xem Run thực nạp gì sau khi scan. Xem NOTES v1.6.5, v1.6.6 (2 vòng QA sửa thêm 3 lỗi thật khi dùng binary nuclei thật).
- **D1 — giới hạn URL/lượt: đã chốt (2026-10-17), bỏ hẳn.** Không còn cắt 50 (quick)/200 (full) URL mỗi lệnh nuclei — mọi URL đang sống đều được đưa vào. An toàn thời gian dựa vào ngân sách giai đoạn đã có từ v1.6.0 (mỗi lệnh chỉ được phần còn lại của giai đoạn), không thêm cơ chế "quét tiếp" riêng. Thêm `ScanConfig.nuclei_timeout`/`Settings.BBASM_NUCLEI_TIMEOUT` (cùng mẫu `nmap_timeout`/`ffuf_maxtime`) làm lưới an toàn phụ. Xem NOTES v1.6.7.
**Chưa làm (không thuộc D1, có thể làm riêng nếu muốn):**
- Phương án A (lọc theo `-tags` include cụ thể, không chỉ severity) — độc lập với `-as` đã có.
