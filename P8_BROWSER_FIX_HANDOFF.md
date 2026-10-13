# P8 BROWSER/E2E FIX HANDOFF — cho Codex xử lý

> **Nhánh:** `build/p8-acceptance`. **Nguồn chi tiết:** `P8_BROWSER_E2E_RESULT.md` (bằng chứng chạy thật trên Kali).
> **Ràng buộc giữ nguyên:** reuse framework qua subprocess; agent bridge chỉ sinh folder; path qua `BBASM_BBROOT/BBASM_TOOLS_SUBDIR`; scope safety + audit; giữ LF; không scan target thật khi code; test cần tool/mạng/Docker/browser thật đánh dấu `@pytest.mark.integration`.

## 🔴 FIX-B1 (HIGH, CHẶN E2E + bug sản phẩm) — WebSocket `/ws/scan/{id}` trả 404; UI kẹt "queued"

**Bằng chứng:** WS handshake tới container → `HTTP/1.1 404`. `requirements.txt` chỉ có `uvicorn==0.38.0` (thiếu thư viện WS). Scan chạy xong (`DB status=done`) nhưng dashboard hiển thị `queued` mãi + "Mất kết nối" vì UI chỉ cập nhật status khi nhận event WS `done`, không poll REST.

**Phần 1 — bật WebSocket cho uvicorn (bắt buộc):**
- Thêm `websockets` (hoặc `wsproto`) vào `requirements.txt`, HOẶC đổi `uvicorn==0.38.0` → `uvicorn[standard]==0.38.0`.
- Đảm bảo image Docker cài lại dep này (rebuild). Xác nhận: WS handshake tới `/ws/scan/{id}` trả **`101 Switching Protocols`**, không phải 404.

**Phần 2 — UI có fallback không phụ thuộc WS (bắt buộc, robustness):**
- Trong `frontend/src/App.tsx` (vùng ScanView ~419-480): ngoài WS, **poll `GET /api/scans/{id}` định kỳ** (vd mỗi 2–3s) cho tới khi status ∈ {done, done_partial, failed, cancelled}; cập nhật badge status từ REST, không chỉ từ event WS `done`. WS vẫn dùng cho log realtime; status completion KHÔNG được phụ thuộc duy nhất vào WS.
- Khi WS không khả dụng, UI vẫn phải tới được trạng thái cuối (badge "done") nhờ poll.

**Test (bổ sung):**
- Integration (có uvicorn thật): assert WS `/ws/scan/{id}` handshake = 101 (không 404). Có thể test bằng `httpx`/`websockets` client tới app chạy bằng uvicorn thật (không phải TestClient — vì TestClient xử lý WS in-process nên không bắt được lỗi này).
- Frontend unit (Vitest): mô phỏng WS lỗi/đóng → component vẫn poll REST và hiển thị status "done".
- Ghi chú vì sao unit cũ không bắt (Starlette TestClient bỏ qua tầng protocol uvicorn).

**Acceptance:** trên Kali/Docker, chạy lại browser E2E (sau FIX-B2) → scan passive `127.0.0.1` → UI chuyển `queued → done`, Brief hiện ra.

## 🟠 FIX-B2 (MED, test TC-FE-6) — locator `get_by_label("Depth", exact=True)` = 0 match

**Bằng chứng:** `<label>Depth<select><option>passive…</option></select></label>` → accessible name không đúng hệt "Depth"; `exact=True` trượt (count=0). `get_by_label("Depth")` và `get_by_role("combobox", name="Depth")` đều khớp.

**Chọn 1 trong 2 (nên làm cả cho chắc):**
- Sửa test `backend/tests/test_browser_integration.py`: đổi `page.get_by_label("Depth", exact=True)` → `page.get_by_role("combobox", name="Depth")` (hoặc bỏ `exact=True`).
- Và/hoặc cải thiện a11y ở `App.tsx`: gắn `aria-label="Depth"` cho `<select>` hoặc dùng `htmlFor`+`id` để accessible name chính xác là "Depth" (tốt cho accessibility nói chung).

**Acceptance:** `BBASM_E2E_TARGET=<authorized> pytest -m integration backend/tests/test_browser_integration.py` PASS (sau khi B1 xong).

## Definition of done (B1+B2)
- [ ] WS `/ws/scan/{id}` trả 101 trên uvicorn thật (lib WS có trong requirements + image).
- [ ] UI đạt trạng thái cuối (done) kể cả khi WS hỏng (poll REST fallback).
- [ ] `test_browser_integration.py` PASS với locator đúng.
- [ ] `pytest -m "not integration"` vẫn xanh; thêm test chặn regression (WS handshake 101; UI poll khi WS lỗi).
- [ ] Không vi phạm ràng buộc; LF giữ nguyên.

## Mục P8 CÒN LẠI — cần MÔI TRƯỜNG/authorization của người dùng (Codex không tự chạy được)
1. **Windows/WSL2:** build + `docker compose up` trên Docker Desktop/WSL2; kiểm dashboard, `/api/health`, và volume DB/targets persist. `.gitattributes` đã ép LF. Codex: rà soát Dockerfile/entrypoint/compose cho tương thích WSL2 (bind mount path, line endings) nhưng việc chạy thật do người dùng.
2. **H1 program thật:** chạy luồng resolve (H1 handle/URL/policy_scopes được phép) → review IN/OUT/category/policy → launch → brief; kiểm phân loại web/wildcard/ip/cidr/source_code/mobile đúng. Cần người dùng cung cấp program được phép + (tùy chọn) `H1_USER/H1_TOKEN`.

Khi B1+B2 xong và push, báo để Kali chạy lại browser E2E xác nhận.
