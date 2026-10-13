# advance_asm (BBASM)

Bug Bounty **Attack Surface Management** dashboard — tăng tốc & khử-token bước setup recon cho bug bounty / pentest.

Web dashboard (FastAPI + React, đóng Docker) ngồi trên framework recon (`claude-bug-bounty`, vendored submodule). Nhập **HackerOne handle/URL** hoặc **raw scope** → **review config** → recon (depth tùy chỉnh) → ranked attack surface + diff theo thời gian → sinh `PROGRAM.md` + `AGENT_BRIEF.md` để Claude agent `cd` vào hunt với ~0 token setup.

> **Trạng thái:** backend, dashboard và cấu hình Docker đã triển khai. P2 đã được xác nhận trên Kali; các phase sau có unit test. **Docker build và acceptance với recon thật chưa chạy trong môi trường triển khai này.** Nguồn chuẩn: [`BUILD_SPEC.md`](./BUILD_SPEC.md); kết quả/giới hạn: [`NOTES.md`](./NOTES.md). Nhánh mới nhất: `build/p8-acceptance`; hướng dẫn pull và checklist Kali: [`ACCEPTANCE.md`](./ACCEPTANCE.md).

---

## Kiến trúc chốt

| | |
|---|---|
| Hình thức | Web dashboard ASM |
| Stack | FastAPI + WebSocket + React/Vite + SQLite |
| Input | HackerOne (handle/URL + policy_scopes) + raw scope (domain/IP/CIDR/`repo:`/`app:`) |
| Luồng | **resolve → REVIEW CONFIG → launch** (recon không chạy khi submit) |
| Recon depth | `passive` / `light` / `strong` (tùy chỉnh; gọi lại `recon_engine.sh`) |
| Scope | Cross-platform: web/wildcard/ip/cidr/**source_code**/**mobile**/other |
| ASM | multi-program portfolio · continuous re-scan + diff · ranked surface · JS/secret + takeover monitor |
| Output | `targets/<slug>/` (PROGRAM.md + AGENT_BRIEF.md + recon…) + **Export ZIP** |
| Agent bridge | Dashboard chuẩn bị folder; user tự `cd targets/<slug> && claude` |
| Đóng gói | Docker (Linux / macOS / Windows-WSL2) |

---

## Quickstart Docker (cần validation trên máy chủ)

```bash
# 1. Clone KÈM submodule (bắt buộc)
git clone --recurse-submodules https://github.com/gloryy2k/advance_asm.git
cd advance_asm
git switch build/p8-acceptance
git submodule update --init --recursive

# 2. Cấu hình
cp .env.example .env        # điền API key nếu có (optional)

# 3. Build & chạy  (lần đầu ~10–30 phút: compile Go tools + nuclei templates)
docker compose up -d --build

# 4. Mở dashboard
#    http://127.0.0.1:8000
```

Hunt một target sau khi scan xong:
```bash
cd targets/<slug>        # vd targets/acme
claude                   # agent đọc PROGRAM.md + AGENT_BRIEF.md → hunt ngay
```

---

## Yêu cầu môi trường (tóm tắt — chi tiết §24 BUILD_SPEC.md)

- **Docker + Docker Compose v2** (Linux: cài `docker-compose-plugin`; Docker Desktop đã kèm).
- Clone **`--recurse-submodules`** — thiếu submodule → build fail.
- **RAM ≥ 8GB** khuyến nghị (4GB chỉ đủ passive/light), **disk ≥ 10GB**, **internet lúc build**.
- **Claude Code** trên host (cho giai đoạn hunt).
- **Windows:** Docker Desktop + **WSL2 backend**; clone repo vào filesystem WSL (không để `/mnt/c`); `.gitattributes` đã ép LF nên script không vỡ vì CRLF.

---

## Phát triển (dev, không Docker)

```bash
# Chạy từ root repo, Python >= 3.11
python -m venv .venv
source .venv/bin/activate  # PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m backend.main
# GET http://127.0.0.1:8000/api/health
# Dashboard: build frontend trước, hoặc chạy Vite dev server bên dưới.
```

Dev local có thể bỏ `.env`: mặc định dùng framework trong `vendor/`, cùng `data/`
và `targets/` tại root repo. `.env.example` dùng đường dẫn dành cho container;
nếu copy sang `.env` để dev local, sửa `BBASM_BBROOT`, `BBASM_DATA`, `BBASM_TARGETS`
cho đúng máy. ENV của process ưu tiên hơn `.env`. `python -m backend.main` đọc
`BBASM_BIND`/`BBASM_PORT` (mặc định `127.0.0.1:8000`).

Health trả `ok: true` khi API hoạt động, kể cả khi thiếu tool; xem từng boolean
trong `tools`. Đây là kiểm tra executable trong PATH và file framework tồn tại,
không chạy tool hay xác minh phiên bản (đặc biệt tên `httpx` có thể trùng CLI Python).

Frontend yêu cầu Node **>=22.12**:

```bash
cd frontend
npm ci
npm run dev     # http://127.0.0.1:5173; proxy API/WS tới backend :8000
# hoặc npm run build, rồi restart backend để serve frontend/dist
npm test
```

UI: New scan → nhập raw scope/H1 → Resolve & review → sửa config, chọn category,
bỏ host → Launch. Target có Surface/Assets/Diff/Findings/Brief/Program; phần
Program chỉ lưu vùng user-editable. Export ZIP có checkbox Include raw recon.
Monitoring dùng config đã lưu và tự launch theo lịch; lịch sống qua restart.
Chạy **một backend process**, không bật nhiều uvicorn workers cùng database.

Docker dùng nmap connect-scan `-sT`, mặc định không thêm capabilities. Nếu cần cấp
capabilities cho công cụ khác, dùng override `docker-compose.capabilities.yml`.
Subfinder config là mount optional: đặt `SUBFINDER_CONFIG_DIR` tới thư mục host có
sẵn và thêm `-f docker-compose.subfinder.yml`. Không cần mount để chạy mặc định.
`BBASM_UPDATE_TEMPLATES=0` bỏ refresh templates lúc khởi động. Không sửa bind
localhost của published port nếu chưa chủ động muốn expose dashboard không có auth.

P1: `POST /api/scope/resolve` nhận `{"input":"raw","scope":["*.example.com"]}`
hoặc `{"input":"h1:<handle>"}` / URL HackerOne `/policy_scopes`. Kết quả có
`scan_id`, `slug`, `config`, `assets_by_category`; scan luôn ở `draft`, chưa chạy recon.
Raw có thể dùng dòng `# IN` / `# OUT` để phân biệt phạm vi. Mobile/other giữ ở
chế độ manual. SQLite tự migrate lần resolve đầu; health không tạo DB.

Scope gate: `*.example.com` chỉ cho subdomain, không cho `example.com`; OOS luôn
ưu tiên. CIDR chứa một IP/subnet OOS bị chặn toàn bộ, không tự chia dải. Domain/URL
được kiểm theo hostname; `repo:https://github.com/org/repo` giữ ranh giới repository.
Mọi quyết định ghi trong `targets/<slug>/audit.jsonl`.

H1 cần Bash và Python 3 của framework (Linux/WSL2/Docker). Adapter lấy metadata có
IN/OUT qua kết nối được audit, sau đó gọi aggregator với cache cô lập và tắt transport
trong subprocess. Không tin danh sách host phẳng của bản pin vì mất thông tin OOS.
API H1 lỗi/thiếu token thì fallback public dump; metadata không rõ scope thì trả 422.

P2 bổ sung `GET/PUT /api/scans/{id}/config`, `POST /api/scans/{id}/launch` (body `{}`
để dùng config đã lưu hoặc `{"config":...}`), `GET /api/scans/{id}`,
`POST /api/scans/{id}/cancel` và `/ws/scan/{id}?after=<event-id>`.
Config chỉ sửa được ở draft. Launch mặc định ghi `allow/audited_spawn` trước khi
chạy subprocess; `BBASM_RECON_DISABLED=1` chặn launch. Runtime cần Linux/WSL2
và bộ tool đã cài; unit test trên Windows dùng process giả.
Các ENV `BBASM_NO_INTERACTSH`, `BBASM_NO_REDIRECT`, `BBASM_SCOPE_CRAWL`,
`BBASM_NO_VERIFY` mặc định `1`; chỉnh `.env` và restart backend để đổi.
Historical bỏ qua IP/CIDR (kể cả IP trong list hỗn hợp). Domain có budget
`BBASM_HISTORICAL_TIMEOUT=60` giây; `BBASM_SKIP_HISTORICAL=1` tắt toàn bộ bước này.
Health và runner cùng tìm tool trong `~/go/bin`, PATH hiện tại và các thư mục
Homebrew/local của Linux/macOS; health vẫn chỉ kiểm tra executable, không chạy tool.
Audit ghi quyết định scope và khởi chạy, **không ghi từng request nội bộ của tool**
và không phải network isolation. Output nằm ở
`targets/<slug>/recon/scans/<scan_id>/<step>/` để tránh trộn scan/ingest dữ liệu cũ.

Chạy test (unit — không cần tool recon thật):
```bash
pytest -m "not integration"
```
Integration/e2e (cần subfinder/nuclei/httpx… + Docker) chạy trên Kali/Linux:
```bash
pytest -m integration
```

---

## Kết quả kiểm tra và token benchmark

Backend sau P8 fixes: **177 passed, 7 integration deselected**.
Frontend P6: **6 tests pass**, production build pass. CI remote và Docker/recon
thật của các phase mới còn chờ xác nhận; xem ACCEPTANCE.md.

`python scripts/measure_tokens.py` so sánh corpus fixture 30 host/2000 URL với
CLAUDE.md + PROGRAM.md + AGENT_BRIEF.md bằng cl100k_base (cần cài `tiktoken`).
Kali đo tại `4882a9d`: **32004 → 994 input tokens (giảm 96.89%)**, brief 2638 byte.
Đây là phép đo fixture, không phải chi phí hay mức tiết kiệm của hunt thật;
xem `P3_P8_REVIEW_RESULTS.md`. Scope bắt buộc vượt budget brief sẽ báo lỗi.

## Cấu trúc repo

```
advance_asm/
├── BUILD_SPEC.md              # spec thi công đầy đủ (nguồn chuẩn)
├── .env.example  .gitattributes
├── docker-compose.yml  Dockerfile  entrypoint.sh   # Docker runtime
├── backend/                   # API, runner, scope, ASM, brief/export
├── frontend/                  # React/Vite dashboard
├── vendor/claude-bug-bounty/  # submodule @7acb66a (toggle patch trên nền @32131c1)
├── targets/                   # output per-target (gitignore)
└── data/bbasm.db              # SQLite (gitignore)
```

---

## An toàn & phạm vi

Chỉ scan target **trong scope** bạn cung cấp — dashboard lọc seed/discovery qua scope gate (wildcard + IP/CIDR), audit scope và khởi chạy tool. Các request nội bộ của tool không được audit/chặn từng request. Không tự khai thác / submit / spray. `strong` depth (nmap/ffuf) chỉ dùng khi scope cho phép active scan.

## License / nguồn

Framework recon vendored từ [`claude-bug-bounty`](https://github.com/gloryy2k/claude-bug-bounty) (fork của Agentic Bug Hunter). BBASM là lớp dashboard/orchestrator trên framework đó.
