# REVIEW GUIDE — cho session review (gồm Claude cloud nối thẳng repo)

> Mục đích: một reviewer MỚI (không có transcript/memory của các session trước) đọc file này là nắm trạng thái + biết cái gì verify được ở đâu. **Mọi quyết định & finding đều đã nằm trong repo** (các doc dưới) — transcript hội thoại KHÔNG cần thiết.

## 1. Lấy code
```
git clone --recurse-submodules https://github.com/gloryy2k/advance_asm.git
cd advance_asm && git switch build/p8-acceptance
git submodule update --init --recursive     # vendor/claude-bug-bounty (framework, pin 7acb66a)
```
Toàn bộ P0–P8 nằm trên chuỗi branch `build/p0 → p1 → … → build/p8-acceptance`, **chưa merge `main`**.

## 2. Đọc theo thứ tự (nguồn chuẩn + lịch sử nghiệm thu)
- `BUILD_SPEC.md` — spec (§1 kiến trúc, §6 schema, §8 orchestration/scope/runner, §12 ASM, §22 two-phase/category, §24 system req). Đầu file có CHANGELOG v1→v2.4.
- `NOTES.md` — quyết định triển khai P0–P8 + giới hạn đã ghi.
- `ACCEPTANCE.md` — checklist nghiệm thu + các mục chưa có bằng chứng thực tế.
- `P8_WINDOWS_BROWSER_RESULT.md` — kết quả mới nhất ngày 2026-10-14: B1/B2,
  Windows CRLF fix, browser E2E/persistence đã pass và giới hạn H1 Live Nation.
- Báo cáo nghiệm thu thật (chạy trên Kali): `P2_T6_RESULTS.md`, `P3_P8_REVIEW_RESULTS.md`, `P8_FIX_VERIFICATION.md`, `P8_DOCKER_RESULT.md`, `P8_DOCKER_RERUN_RESULT.md`, `P8_DOCKER_PERSIST_RESULT.md`, `P8_BROWSER_E2E_RESULT.md`, `P8_FIX_HANDOFF.md`, `P8_BROWSER_FIX_HANDOFF.md`.

## 3. Reviewer nào verify được gì

### A. Review-only / Cloud (chỉ Python + Node, KHÔNG recon tool / Docker / target thật)
Làm được:
- **Code review** đối chiếu spec: `backend/asm/` (diff/ranking/scheduler/monitors), `backend/jobs/` (runner teardown, recon_orch, scope_resolver, h1_scope, ingest), `backend/brief/` (generator/export), `backend/scope_gate.py`, `backend/api/`, `frontend/src/`.
- **Unit tests:** `pip install -r requirements.txt && pytest -m "not integration"` → **kỳ vọng 197 passed** (tests hermetic; xem `P8_DOCKER_RERUN_RESULT.md` về cấu hình dotenv).
- **Frontend:** `cd frontend && npm ci && npm test && npm run build` (11 tests + build).
- **Docker build/compose**: CHỈ nếu sandbox có Docker. Không có thì skip.

KHÔNG làm được (cần host có tool/target): recon thật, `test_recon_integration`, `test_docker_integration`, browser E2E với recon thật, H1 thật.

### B. Host có tool (Kali/Linux + Docker, như máy đã dùng)
Chạy được toàn bộ integration/acceptance:
- `pytest -m integration` (một số cần tool recon trong PATH, gồm `~/go/bin`).
- `BBASM_DOCKER_TESTS=1 pytest -m integration backend/tests/test_docker_integration.py` (docker qua sudo nếu user không ở docker group).
- `docker compose up -d --build` → `/api/health` + static + restart-persist.
- Browser E2E: `pip install playwright && playwright install chromium`, backend chạy, `BBASM_E2E_TARGET=<authorized> pytest -m integration backend/tests/test_browser_integration.py`. Dùng `127.0.0.1` depth passive để test luồng mà không chạm bên thứ ba.

## 4. Trạng thái P8 (sau bản sửa `3b68189`)

✅ B1/B2 đã sửa và kiểm chứng: WS thật 101, REST fallback khi WS lỗi,
browser pytest resolve → review → launch passive localhost → Brief PASS (7.35s).
✅ Windows Docker Desktop/WSL2 build/runtime/DB/targets/schedule persistence PASS.
Image chuẩn hóa shell scripts của submodule sang LF, giữ nguyên vendor pin.
⬜ H1 Live Nation resolve 25 asset PASS nhưng chưa scan: policy chính thức cấm
scanner/LLM discovery, public fallback không có full policy. Cần program khác
cho phép automation để nghiệm thu H1 light → handoff. Không launch Live Nation.
Các mục chi tiết chưa có bằng chứng vẫn nằm trong ACCEPTANCE.md; chưa chốt P8.
CI của commit mới cần kiểm tra riêng.

### Lịch sử trước bản sửa (`f79c9fb`)
✅ Đã verify thật trên Kali: unit 195 · HIGH-1 teardown (nuclei) · FIX-1→4 · Docker build (binary-release) + health + static · persist DB/targets/schedule qua restart · CI remote.
⏳ **Browser E2E CHƯA đạt** — 2 bug (xem `P8_BROWSER_E2E_RESULT.md` + handoff `P8_BROWSER_FIX_HANDOFF.md`):
- **B1 (HIGH, sản phẩm):** `/ws/scan/{id}` trả **404** do thiếu lib WS cho uvicorn (`requirements.txt` chỉ có `uvicorn` trần) → dashboard kẹt "queued" dù backend `done`; không có fallback poll REST. Fix: thêm `websockets`/`uvicorn[standard]` + UI poll `/api/scans/{id}`.
- **B2 (MED, test):** E2E `get_by_label("Depth", exact=True)` = 0 match → dùng `get_by_role("combobox", name="Depth")` / thêm aria-label.
⬜ **Cần môi trường user:** Windows/WSL2 (Docker Desktop), H1 program thật (program được phép + optional `H1_USER/H1_TOKEN`).

## 5. Sau khi P8 pass hết
**Merge `build/p8-acceptance → main`** (kèm bump con trỏ submodule) mới là ship v1. Non-goals v1 (ngoài phạm vi, không phải thiếu sót): không spawn agent hunt/full-auto, chưa hỗ trợ BC/IT/YWH/Immunefi ở UI, không multi-user/auth.

## 6. v1.1 Guided UX (nhánh `claude/upbeat-thompson-b7bb23`)
Đọc `CLOUD_REVIEW_RESULTS.md` (lỗi F1–F10 + kế hoạch), rồi `NOTES.md` mục "v1.1". Kiểm trong cloud:
`python -m pytest -m "not integration"` (≥259) · `cd frontend && npm ci && npm test && npm run build` (33 test) ·
`pip install playwright==1.56.0` rồi `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python -m pytest -m integration backend/tests/test_ui_e2e_mock_h1.py backend/tests/test_websocket_runtime.py`.
Ảnh chụp UI: `review_tools/mock_h1_server.py` + `review_tools/ui_screenshots.py`. Lưu ý: dùng `python -m pytest`, không dùng `pytest` trần.
