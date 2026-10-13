# P3–P8 — Review & nghiệm thu (Kali/Linux thật)

> **Người review:** chạy thật trên Kali, không dựa báo cáo. **Ngày:** 2026-10-13.
> **Nhánh:** `build/p8-acceptance` **commit `4882a9d`**; submodule vendor `7acb66a`.
> **Môi trường:** venv Python 3.14.7, Node v24.18, Docker engine 26.1.5 (KHÔNG có compose plugin), RAM ~3.8GB. Chỉ scan `127.0.0.1` (máy local — được phép tuyệt đối) + 1 web server local trên :80.

## 1. Kết luận nhanh
Code P3–P7b **đạt chuẩn spec** (diff/ranking/scheduler/monitors/brief/export/portfolio review từng file, khớp §9/§10/§12/§22). Test + nghiệm thu live phần lớn **PASS**. Phát hiện **1 bug HIGH** (cancel/timeout rò rỉ tiến trình tool), 1 MED, 2 LOW. Một số mục **chưa chạy được** trên host này (Docker build, browser E2E, Windows/WSL2) — ghi SKIP, không đánh dấu hoàn tất.

## 2. Test tự động

| Lệnh | Kết quả |
|---|---|
| `pytest -m "not integration"` | **163 passed, 5 deselected** ✅ (khớp claim) |
| `pytest -m integration` | **3 passed, 2 skipped** (Docker/browser gated sau ENV) ✅ |
| coverage `--cov=backend/asm --cov=backend/brief` | **94%** (diff 100%, ranking 100%, monitors 95%, scheduler 94%, generator 90%, export 87%) ✅ |
| `cd frontend && npm ci && npm test` | **6 passed** ✅ |
| `npm run build` | build OK, 176 modules, dist tạo ✅ |
| `bash -n` entrypoint.sh / install_container_tools.sh | OK ✅ |

## 3. Nghiệm thu LIVE (localhost + web server :80, authorized)

| Hạng mục (§17/§22/§24) | KQ | Bằng chứng |
|---|---|---|
| resolve → review (PUT config) → launch → done | ✅ | scan_id 3 done 15s; PUT /config đổi skip_nuclei được tôn trọng |
| httpx live + tech fingerprint | ✅ | `127.0.0.1 [200] [Admin API Login] [Python:3.14.7,SimpleHTTP:0.6]` |
| Ranking §12.3 trên dữ liệu thật | ✅ | rank **6.5**, reasons `[api, auth, fresh, status_200]` (title "Admin API Login") |
| Portfolio NEW/asset_count | ✅ | `new_count:1, asset_count:1, latest_scan.done` |
| Diff NEW + không false-NEW | ✅ | scan đầu `diff{new:1}`; rescan host đã biết `diff=[]` (idempotent) |
| Diff GONE | ⚠️ unit-only | Seed IP luôn được tái quan sát → GONE không kích hoạt cho seed; GONE dành cho subdomain discovered biến mất (đã test ở test_asm_core/pipeline). Không tái hiện live được với 1 seed IP. |
| Brief ≤12KB + regen | ✅ | 630 bytes; generator raise lỗi nếu scope > 12KB (không lược scope) |
| PROGRAM.md persist + user-editable | ✅ | PUT /program (field `content`) = 200; user section cập nhật, `## Policy` giữ nguyên; không ghi đè khi regen |
| ZIP include_recon true/false | ✅ | true có PROGRAM/BRIEF/.scope/recon; false → 0 recon dir |
| MANIFEST.json | ✅ | đủ slug/source/scan_id/depth/stats/scope{in,out}/files/bbasm_version |
| Monitors (toggle an toàn) | ✅ | nuclei chạy `-no-interactsh -severity low,medium` (đúng T2 + depth light) |
| Cancel → trạng thái | ✅ (nhưng xem BUG-H1) | cancel trả `cancelled`; scan 3 sau đó done bình thường |
| Scheduler persist qua restart | ✅ | POST /schedule (daily/light) → DB row; kill+restart backend → startup không lỗi, row còn nguyên |
| Token benchmark | ✅ | `measure_tokens.py`: old **32004** → new **994** tokens, **giảm 96.89%** (fixture 30 host/2000 URL/5 nuclei); brief 2638B. Lưu ý: chỉ input fixture, không phải đo hunt thật. |

## 4. Mục CHƯA chạy (không đánh dấu hoàn tất)

- **Docker build/compose** — SKIP: host này **chưa cài compose plugin** (`docker compose` báo lỗi), không build/parse được. Đã validate `bash -n` entrypoint + install script. Cần chạy trên máy có `docker-compose-plugin`: `docker compose config`, `BBASM_DOCKER_TESTS=1 pytest ... test_docker_integration.py`, kiểm health/static + volume DB/target sau restart.
- **Browser E2E** (`test_browser_integration.py`) — SKIP: cần Playwright + domain được phép; không có target ngoài. Chạy: `BBASM_E2E_TARGET=<authorized> pytest -m integration backend/tests/test_browser_integration.py`.
- **Windows/WSL2** — CHƯA kiểm: chỉ test trên Kali Linux. `.gitattributes` ép LF có sẵn nhưng chưa xác nhận build/run thực trên Docker Desktop/WSL2.
- **H1 light thật** (review IN/OUT/category/policy, mobile/source routing) — CHƯA: chỉ test raw IP. Nên chạy với một program H1 có quyền.
- **CI GitHub Actions của commit bàn giao** — CHƯA xác nhận kết quả remote.

## 5. FINDINGS (theo mức ưu tiên)

### 🔴 HIGH-1 — Cancel/timeout RÒ RỈ tiến trình tool (`timeout`-wrapped): scan vẫn tiếp tục bắn traffic sau khi huỷ
**Bằng chứng:** sau `POST /scans/2/cancel` (status=`cancelled`), tiến trình `nuclei` (pid 719489) **vẫn sống >25s**, `ps` cho **PGID=719488 ≠ pid bash** mà runner track. Phải `kill -KILL -719488` thủ công mới dừng.
**Root cause:** `recon_engine.sh` chạy tool qua GNU `timeout` (dòng 696 `timeout "$NUC_TIMEOUT" nuclei …`; tương tự `timeout 300 katana` dòng 446, `timeout 300 amass` dòng 316, và gau historical). GNU `timeout` đặt tiến trình con vào **process group riêng**. Runner `stop_process_group` dùng `os.killpg(process.pid, …)` chỉ giết group của bash session → **không với tới** group của tool. Hệ quả: cancel VÀ hard-timeout đều để lại nuclei/katana/amass tiếp tục **active-scan target** → vi phạm §2.6/§18 (cancel phải dọn process group) và rủi ro scope/tài nguyên.
**Vì sao test không bắt:** `TC-RUN-2` dùng child đơn giản (sleep) trong group được track → false confidence; không phủ tiến trình cháu ở group tách bởi `timeout`.
**Hướng sửa:** runner phải giết **toàn bộ cây tiến trình / cả session**, không chỉ 1 process group. Ví dụ: liệt kê hậu duệ qua `psutil.Process(pid).children(recursive=True)` rồi SIGKILL; hoặc kill theo SID (bash là session leader do `start_new_session`) bằng cách duyệt `/proc/*/stat` lọc theo session id; hoặc trong recon_engine dùng `setsid`/`timeout --foreground` để tool ở cùng group (kém chắc hơn). Bổ sung test cancel/timeout với tiến trình bọc `timeout` để tái hiện.

### 🟠 MED-1 — DB reset nhưng `targets/` còn lại → scan_id tái dùng, đụng dir cũ, scan fail ngay
**Bằng chứng:** sau khi xoá `data/bbasm.db` (reset counter về 1) mà `targets/127.0.0.1/recon/scans/1/` cũ vẫn còn → launch fail: `ValueError: Scan output already exists; create a new scan instead of reusing stale output` (recon_orch.build).
**Tác động:** DB và thư mục output trên 2 volume có thể lệch nhau (restore backup, copy targets, reset DB) → scan chết khó hiểu. Guard là cố ý (không ghi đè output cũ) nhưng gắn scan_id–dir quá chặt.
**Hướng sửa:** namespace output bằng token duy nhất (vd uuid/ts) thay vì chỉ scan_id; HOẶC khi `root.exists()` nhưng DB không có scan tương ứng → coi là orphan, dọn/di chuyển thay vì fail; HOẶC ghi chú rõ DB và targets phải đi cùng nhau.

### 🟡 LOW-1 — Diff không ghi CHANGED khi host 200 → offline
**Bằng chứng:** tắt web :80 rồi rescan (complete) → host 127.0.0.1 vẫn `active`, `diff=[]` (không CHANGED). Do `diff_engine.apply` chỉ so status khi observation mới **có** `status_code`; host không probe-live → bỏ qua.
**Tác động (nhẹ):** "host vừa 200 giờ offline" vô hình trong diff ASM. Có thể là chủ ý (tránh nhiễu downtime tạm thời). Cân nhắc ghi CHANGED khi mất live.

### 🟡 LOW-2 (doc) — TC-RK-1 lệch công thức §12.3
Spec §16 TC-RK-1 kỳ vọng ≥7, nhưng §12.3 cho api+graphql+200+fresh = **6.0**. Code giữ đúng công thức (đã ghi ở ACCEPTANCE). Sửa kỳ vọng TC-RK-1 trong BUILD_SPEC xuống ≥6 (hoặc chỉnh trọng số nếu muốn 7). Không phải bug code.

## 6. Giới hạn đã xác nhận (kế thừa P2, không phải lỗi mới)
- Audit ghi scope + subprocess spawn, **không chặn/giám sát mọi request nội bộ của tool** (đã nêu từ P2). Không khẳng định network containment. Nhất quán với quyết định "không xây egress isolation nặng".

## 7. Lệnh đã chạy (tóm tắt, không chứa secret)
```
pytest -m "not integration"            # 163 passed
pytest -m integration                  # 3 passed, 2 skipped
pytest --cov=backend/asm --cov=backend/brief   # 94%
cd frontend && npm ci && npm test && npm run build   # 6 passed, build OK
python -m uvicorn backend.main:app     # backend; resolve/launch/cancel/schedule/brief/export qua curl
python scripts/measure_tokens.py       # 96.89% reduction (fixture)
```
Host: Kali Linux 6.12 x86_64; scan ID 2/3/4/5 trên program `127.0.0.1`.

## 8. Đề xuất nghiệm thu
- **Chặn merge P8** cho tới khi fix **HIGH-1** (rò rỉ tiến trình khi cancel/timeout) — đây là vấn đề an toàn (tiếp tục scan sau huỷ) + đúng đắn teardown.
- MED-1 nên fix trước khi deploy đa-volume. LOW-1/LOW-2 có thể để sau.
- Chạy nốt Docker build, browser E2E, Windows/WSL2, H1 thật và CI remote trước khi coi P8 hoàn tất.
