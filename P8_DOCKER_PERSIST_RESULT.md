# P8 — Docker compose + persistence acceptance (commit 262b254)

> **Ngày:** 2026-10-13. **Nhánh:** `build/p8-acceptance` **commit `262b254`**, submodule `7acb66a`. **Host:** Kali, RAM 11GB, Docker 26.1.5 + compose v2.30.3 (docker qua sudo).

## ✅ 3/3 task PASS

### 1. Unit tests — **195 passed, 7 deselected** ✅
`pytest -m "not integration"` = 195 pass (khớp kỳ vọng). Tests giờ **hermetic**: helper dùng `_env_file=None` nên `.env` ở CWD không còn ảnh hưởng (fix finding `.env` trước đó). `.env.example` đã comment các path `BBASM_BBROOT/DATA/TARGETS/STATIC` → `cp .env.example .env` không còn phá dev.

### 2. `docker compose` build + runtime ✅
- `docker compose config` OK: container env `BBASM_BBROOT=/opt/claude-bug-bounty`, `BBASM_DATA=/app/data`, `BBASM_TARGETS=/app/targets`; volumes `./data→/app/data`, `./targets→/app/targets`; port `127.0.0.1:8000`.
- `docker compose up -d --build` (binary-release, giữ cache): container `bbasm-bbasm-1` **Up**, healthcheck pass.
- **`/api/health`**: `ok:true`, tool đủ — `subfinder, httpx, dnsx, nuclei, katana, gau, amass, ffuf, nmap, git, trufflehog` = true + mọi script framework = true (chỉ `bbscope=false`, không pin — không ảnh hưởng).
- **Dashboard static**: `GET /` trả HTML chứa `<div id="root">` ✅.

### 3. Persist DB / targets / monitoring qua restart ✅
State trước restart (volume host mount vào container): program `127.0.0.1`, schedule `daily/light/enabled`, `targets/127.0.0.1/` (PROGRAM.md, AGENT_BRIEF.md, recon, findings, notes, reports, audit.jsonl).
Sau `docker compose restart`:
- Container healthy lại.
- **Portfolio**: program `127.0.0.1` (asset_count 1) — còn nguyên.
- **Schedule**: `(program 1, daily, light, enabled, next_run 2026-10-14T04:37:16)` — còn nguyên.
- **Targets**: đủ file như trước — còn nguyên.
- **Scheduler reload**: log container `Added job "ScanScheduler.dispatch" to job store "default"` → `Scheduler started`, **không lỗi** → lịch monitoring sống lại sau restart.

## Trạng thái nghiệm thu Docker (Linux) — ĐẠT
compose config ✅ · build binary-release (~16' lần đầu, cache lần sau) ✅ · health đủ tool ✅ · dashboard static ✅ · DB/targets/schedule persist + scheduler reload qua restart ✅.

## Còn lại để đóng P8 (môi trường, chưa chạy)
- Browser E2E (cần domain được phép), Windows/WSL2, H1 program thật, CI GitHub Actions remote.
