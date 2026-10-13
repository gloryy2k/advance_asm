# P8 FIX — Xác minh thật trên Kali (sau commit 101b0ef)

> **Ngày:** 2026-10-13. **Nhánh:** `build/p8-acceptance` **commit `101b0ef`**; submodule vendor `7acb66a` (giữ nguyên). **Môi trường:** venv Python 3.14 (+psutil 7.0.0), Kali Linux.
> Tiếp nối `P3_P8_REVIEW_RESULTS.md` / `P8_FIX_HANDOFF.md`.

## Kết quả: 4/4 fix ĐẠT; HIGH-1 xác nhận bằng nuclei thật ✅

| Fix | KQ | Bằng chứng |
|---|---|---|
| **FIX-1 (HIGH)** cancel/timeout giết cả cây tiến trình | ✅ **CONFIRMED (real nuclei)** | xem chi tiết dưới |
| **FIX-2 (MED)** orphan output khi DB reset | ✅ | `recon_orch.build`: nếu `root.exists()` là orphan → `rename` sang `.orphan-<scan_id>-<uuid>` + warning (không fail); giữ raise "already exists for an executed scan" cho reuse thật |
| **FIX-3 (LOW)** diff host 200→offline | ✅ | `diff_engine.apply`: khi `complete` + depth≠passive + `http_probed` + không `http_live` + mất `status_code` + baseline active → ghi CHANGED `{status→null}` + null asset status; có test trong `test_asm_core.py` |
| **FIX-4 (LOW doc)** TC-RK-1 | ✅ | `BUILD_SPEC §16`: TC-RK-1 đổi thành `score≥6` kèm breakdown 2.5+1.5+1.5+0.5=6.0 |

## Test
| Lệnh | KQ |
|---|---|
| `pytest -m "not integration"` | **177 passed, 7 deselected** ✅ (khớp claim) |
| `pytest -m integration backend/tests/test_recon_integration.py` | **4 passed** ✅ (có thêm test teardown) |
| coverage lõi | ~93% (theo claim; asm/brief ~94% ở lần trước) |

## FIX-1 — bằng chứng thật (điểm chặn merge)

Teardown mới: `terminate_family(pid)` = `psutil.Process(pid).children(recursive=True)` **+** mọi tiến trình cùng **session id** (`os.getsid == bash pid`) → TERM → wait grace → re-snapshot → KILL → `killpg` belt-and-suspenders. Bắt được cả tiến trình ở **process group tách bởi `timeout`**.

Thực nghiệm (scan light thật, localhost + web :80, scan_id 6):
```
# TRƯỚC cancel — nuclei ở pgroup của timeout, cùng session bash:
PID 753036 nuclei …   PPID 753034  PGID 753034(timeout)  SESS 752613(bash)
PID 753034 timeout 600 nuclei -no-interactsh -severity low,medium …

# POST /api/scans/6/cancel  -> status=cancelled
# SAU cancel (~4s):
ps -p 753034,753036  -> (chỉ header, cả hai đã chết)
pgrep -x nuclei      -> rỗng  ✓
ps -C timeout        -> không còn tiến trình timeout thật  ✓
recon_engine         -> none  ✓
```
→ Khác hẳn lần review trước (nuclei sống >25s sau cancel). **HIGH-1 đã được vá và kiểm chứng thực tế.** Đường hard-timeout dùng **chung** `terminate_family` (qua `stop_process_group` trong `_command.finally`), nên cũng được vá; không chờ 600s để tái hiện riêng.

## Khuyến nghị
- **Gỡ chặn merge liên quan HIGH-1**: blocker đúng-đắn/an toàn đã được giải quyết và xác minh bằng nuclei thật. FIX-2/3/4 cũng đạt.
- **Vẫn CHƯA đủ để tuyên bố P8 hoàn tất** (các mục môi trường, không phải lỗi code): Docker build + `BBASM_DOCKER_TESTS=1` test (host review thiếu compose plugin), **browser E2E** (cần domain được phép), **Windows/WSL2**, **H1 program thật**, **CI GitHub Actions** của commit bàn giao. Cần chạy trên môi trường phù hợp trước khi đóng P8.

## Lệnh đã chạy (host Kali, scan ID 6 trên program 127.0.0.1; không scan target ngoài)
```
pip install -r requirements.txt            # +psutil 7.0.0
pytest -m "not integration"                # 177 passed
pytest -m integration backend/tests/test_recon_integration.py   # 4 passed
uvicorn backend.main:app ; resolve+launch(light)+cancel qua curl ; ps/pgrep kiểm family
```
