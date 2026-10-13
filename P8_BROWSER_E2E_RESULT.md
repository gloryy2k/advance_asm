# P8 — Browser E2E (TC-FE-6) kết quả thật trên Kali

> **Ngày:** 2026-10-13. **Nhánh:** `build/p8-acceptance` **commit `262b254`**, submodule `7acb66a`. **Cách chạy:** container `docker compose up -d`, Playwright chromium, target `127.0.0.1` depth **passive** (máy local, được phép, không active-scan).

## Kết quả: ❌ FAILED — phát hiện 1 bug sản phẩm (HIGH) + 1 bug test (MED)

Chạy `BBASM_E2E_TARGET=127.0.0.1 pytest test_browser_integration.py` và một full-flow script với locator đã sửa. Backend hoạt động đúng (resolve tạo draft, scan chạy tới `done` trong DB), nhưng **dashboard không phản ánh hoàn tất** và test không qua.

### 🔴 FINDING B1 (HIGH, sản phẩm) — WebSocket `/ws/scan/{id}` trả 404 → realtime log + status "done" hỏng trên dashboard
**Bằng chứng:**
- WS handshake trực tiếp tới container: `GET /ws/scan/8 Upgrade: websocket` → **`HTTP/1.1 404 Not Found`**.
- `requirements.txt` chỉ có `uvicorn==0.38.0` — **thiếu `websockets`/`wsproto`** (và không dùng `uvicorn[standard]`). uvicorn trần **không phục vụ được WebSocket** → mọi kết nối `/ws/scan/{id}` thất bại.
- UI: sau Launch, scan hiển thị `queued` mãi + "Mất kết nối — đang thử lại" / "Đang chờ log…", trong khi **DB: scan 8 = `done`** (backend chạy xong bình thường).
**Root cause kép:**
1. Thiếu thư viện WS cho uvicorn → `/ws/scan/{id}` 404 (cả container lẫn venv vì cùng requirements).
2. Frontend cập nhật status **chỉ** khi WS gửi event `done` (App.tsx ~431-433 set revision/connection); WS hỏng → không refetch `/api/scans/{id}` → **kẹt "queued"**, không có fallback poll REST.
**Vì sao test/CI không bắt:** unit/integration dùng Starlette `TestClient` (xử lý WS in-process, bỏ qua tầng protocol của uvicorn) nên không lộ việc thiếu lib WS khi chạy thật.
**Hướng sửa (cho Codex):**
- Thêm `websockets` (hoặc `wsproto`) vào `requirements.txt`, hoặc đổi `uvicorn` → `uvicorn[standard]`. Rồi xác nhận WS handshake trả `101 Switching Protocols`.
- (Robustness) Frontend nên **poll `/api/scans/{id}`** định kỳ làm fallback để status đạt trạng thái cuối kể cả khi WS không khả dụng; không phụ thuộc duy nhất vào WS.

### 🟠 FINDING B2 (MED, test TC-FE-6) — locator `get_by_label("Depth", exact=True)` = 0 match
**Bằng chứng (probe trên trang review thật):**
- `get_by_label("Depth", exact=True)` → **count=0** (chính dòng test dùng).
- `get_by_label("Depth")` (non-exact) → 1; `get_by_role("combobox", name="Depth")` → 1.
- DOM: `<label>Depth<select><option>passive…</option></select></label>` → accessible name không đúng hệt `"Depth"` nên `exact=True` trượt.
**Hướng sửa:** đổi test sang non-exact / `get_by_role("combobox", name="Depth")`, HOẶC gắn `aria-label="Depth"` / `htmlFor`+`id` cho select để tên chính xác.

## ✅ Phần đã xác minh hoạt động (manual, locator đúng)
- Trang `/#/new`: fill scope + "Resolve & review" → tạo draft scan OK.
- Trang review `/#/scan/{id}/review`: render đúng (Depth passive/light/strong, threads, rate_limit, nuclei severity, skip toggles, scope IN/OUT, "Launch scan"), **không lỗi console**.
- Launch → backend chạy scan passive tới `done` (DB). Chỉ UI không cập nhật do B1.

## Trạng thái P8 — Browser E2E
❌ **chưa đạt** cho tới khi sửa B1 (WS 404 — bug sản phẩm, ưu tiên) và B2 (locator test). Sau khi Codex sửa: thêm lib WS + fallback poll, sửa locator, rồi chạy lại `BBASM_E2E_TARGET=<authorized> pytest test_browser_integration.py`.

## Hai mục P8 còn lại (môi trường — cần người dùng)
- **Windows/WSL2**: chưa kiểm (máy review là Kali Linux). Cần chạy trên Docker Desktop/WSL2.
- **H1 program thật**: cần một program được phép; chưa chạy (chỉ test raw `127.0.0.1`).
