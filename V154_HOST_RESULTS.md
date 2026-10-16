# BBASM v1.5.4 — kiểm thử host

Nguồn `claude/upbeat-thompson-b7bb23` tại `14eb287`; nhánh kết quả `test/v154-host-results`. Ngày 16/10/2026, Windows + Docker Desktop Linux. Stack QA riêng `bbasm-v154qa` tại `127.0.0.1:18788`; dữ liệu đều giả và scope chỉ là `127.0.0.2`. Không dùng H1, token, cookie hay quét host ngoài. Bằng chứng tóm tắt ở [api_summary.json](review_evidence/v154/api_summary.json) và [ui_result.json](review_evidence/v154/ui_result.json).

| Mã | Lệnh / hành động | Kết quả | Bằng chứng ngắn |
|---|---|---|---|
| T0 | `docker compose -p bbasm-v154qa up -d --build` trên worktree riêng | PASS | Image `bbasm-v154qa-bbasm:latest`, UI/API bind localhost `18788`. Không tác động stack `bbasm-v12` của người dùng. |
| T1 | Headless Playwright tại `#/tools` bấm **Cài templates**, rồi `docker compose -p bbasm-v154qa up -d --force-recreate` | PASS | Đếm **14.036** template trước và sau recreate; dữ liệu nằm trên volume riêng. |
| T1-F | Cập nhật khi GitHub không tới được bằng proxy QA sai `127.0.0.1:9`; sau đó bỏ proxy | PASS | Job `failed`, UI báo tiếng Việt “Bộ tải về chỉ có 0 template … Bộ template cũ … vẫn được giữ”; đếm vẫn **14.036**. Không gửi request tới target. |
| T2 | `POST /api/tools/templates/custom` với YAML HTTP `{{BaseURL}}/status`, rồi YAML chứa `code:` và URL cố định | PASS | Template `qa-v154-check` nhận `200`; hai mẫu không an toàn đều `422 invalid_template`. |
| T2-R | Chọn `qa-v154-check` tại Review #13, đợi autosave, launch Light với `automation_ack:true`, hủy ngay | PASS | `GET /api/scans/13/config` có tên template; `scan_run.stats_json.nuclei_templates.custom=["qa-v154-check"]`, official count 14.036. [Ảnh Review](review_evidence/v154/review_custom_autosaved.png). |
| T3 | Tạo draft #2–#4, lọc `qa-v154-draft-`, chọn và xóa hàng loạt bằng UI; launch #4 rồi thử bulk delete | PASS | UI báo “Đã xoá 2 bản nháp”; API bỏ qua #4 với `not_draft`. [Ảnh chọn](review_evidence/v154/drafts_selected.png), [ảnh sau xóa](review_evidence/v154/drafts_deleted.png). |
| T4 | Bật lịch rồi lưu trữ `qa-v154-archive`; thử đổi lịch/header; khôi phục | PASS | Archive trả `schedule_paused=true`, Portfolio mặc định ẩn program, DB `schedule.enabled=0`; hai mutation đều `422 program_archived`; restore giữ lịch tắt. UI hiện banner lưu trữ. |
| T5 | Xem preview rồi xóa vĩnh viễn `qa-v154-delete` | PASS | Preview: 1 scan/asset/URL/finding, 4 file, 0 blocker. Sai slug `422`; đúng slug `200`. Sau đó 0 hàng program/child, folder và `.trash` rỗng; có `data/audit-archive/qa-v154-delete-*.jsonl`. UI khóa nút cho tới khi gõ đúng slug: [ảnh](review_evidence/v154/delete_confirmation.png). |
| T5-R | Dựng trạng thái đã đánh dấu `deleting_at` và đã chuyển folder sang `.trash`, `docker compose -p bbasm-v154qa restart` | PASS | Startup tự xóa program còn pending: 0 hàng, không còn folder hay trash. Đây là mô phỏng điểm gián đoạn xác định, không phải kill đúng giữa lệnh xóa. |
| T6 | Seed 3 scan hoàn tất #7–#9; mở Tổng quan, “Xem dạng bảng”, Run, dark mode tại 1366px | PASS | Trend lần lượt live `2→3→4`, URL `10→20→30`, finding `0→1→2`; bảng khớp API. Phân bố HTTP `2xx/4xx/5xx=1/1/1`, nginx=2, host URL=5, ma trận high=2/low=1. Run có timeline `12s/30s`, `4s/15s`; dark mode nền `rgb(14,22,19)`, không cuộn ngang. [Ảnh biểu đồ](review_evidence/v154/charts_table.png), [ảnh timeline](review_evidence/v154/run_timeline.png). |
| R1 | Hồi quy sitemap tree bằng `backend/tests/test_v138_sitemap.py` | PASS | Có trong bộ 33 test Linux bên dưới. Chưa lặp lại thao tác cây 5.000 URL trên UI ở vòng này. |
| R2 | ZIP `mode=filtered` trên fixture IN `127.0.0.2`, OUT `http://127.0.0.2/admin` | **FAIL** | Trong `qa-urls.txt`, URL đầy đủ `/admin/x` bị bỏ, nhưng dòng `127.0.0.2/admin [200]` vẫn còn cùng dòng `/safe`. |
| R3 | Lịch Light của H1 giả: hạ policy sang `public_dump`, ép tick rồi restart | PASS | Không sinh scan scheduled; `summary.schedule.last_error` có lý do tiếng Việt, `last_error_at` có giá trị. Sau phép thử đã tắt lịch. |
| R4 | `GET /api/health` | PASS | HTTP 200, `ok=true`, `h1_api=false`; các khóa vẫn là `ok`, `tools`, `missing_by_depth`, `h1_api`, `runtime`, `optional_tools` với đúng kiểu dữ liệu. |
| R5 | `docker run --rm --network none … python -m pytest -q` cho templates/lifecycle/charts/sitemap/scheduler/export | PASS | **33 passed**, 1 deprecation warning. Mount QA wrapper cho binary `nuclei` để test dùng fake executable theo fixture; không sửa mã sản phẩm. |

## Finding mới

### P1 — ZIP “filtered” vẫn chứa đường dẫn OUT khi dòng không có scheme

- **Tái hiện:** tạo raw program IN `127.0.0.2`, OUT `http://127.0.0.2/admin`; đặt một file recon `.txt` có các dòng `http://127.0.0.2/safe`, `http://127.0.0.2/admin/x`, `127.0.0.2/admin [200]`; tải `GET /api/programs/qa-v154-zip/export?mode=filtered` rồi đọc file trong ZIP.
- **Thực tế:** ZIP giữ `/safe` (đúng), bỏ URL đầy đủ `/admin/x` (đúng), nhưng vẫn giữ `127.0.0.2/admin [200]` (sai). Điều này có thể đưa dữ liệu OUT vào gói xuất được gắn nhãn đã lọc.
- **Hướng sửa:** chuẩn hóa token host/path không có scheme trước khi kiểm scope, kể cả IP literal và hậu tố trạng thái trong dòng; lọc nguyên dòng nếu bất kỳ URL/host-path token nào thuộc OUT. Thêm regression test đúng fixture trên.

## Giới hạn và ghi chú

- Không kill process thật giữa hai lệnh xóa vì cửa sổ đó rất ngắn; đã dựng đúng trạng thái sau bước đánh dấu/chuyển trash và xác nhận startup hoàn tất. Unit lifecycle cũng nằm trong bộ 33 test pass.
- Scan #1 thất bại do harness ban đầu ghi SQLite từ Windows trong khi container Linux đang dùng DB; sau đó mọi seeding DB chuyển vào trong container và `PRAGMA integrity_check=ok`. Không tính đây là lỗi sản phẩm. Scan #13 xác nhận template riêng trong stats sau khi UI autosave.
- 7 test templates ban đầu dùng nhầm binary nuclei thật có sẵn trong image khi chạy `--network none`. Chạy lại bằng wrapper QA trỏ đúng fake executable của fixture: 33/33 pass. Không sửa mã sản phẩm.
- Thông điệp lỗi cập nhật template được đối chiếu bằng `ui_result.json`; các ảnh được giữ lại đều chụp trên desktop 1366px.
- Dữ liệu/target QA, `.env` và template thật không được commit. Chỉ commit báo cáo và bằng chứng đã chọn. Không scan target bên ngoài.
- Kết thúc: `docker compose -p bbasm-v154qa down -v` và `docker image rm bbasm-v154qa-bbasm:latest` đã xóa đúng container, network, volume và image QA. Stack `bbasm-v12` của người dùng không bị đụng tới.
