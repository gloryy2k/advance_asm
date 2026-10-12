# advance_asm (BBASM)

Bug Bounty **Attack Surface Management** dashboard — tăng tốc & khử-token bước setup recon cho bug bounty / pentest.

Web dashboard (FastAPI + React, đóng Docker) ngồi trên framework recon (`claude-bug-bounty`, vendored submodule). Nhập **HackerOne handle/URL** hoặc **raw scope** → **review config** → recon (depth tùy chỉnh) → ranked attack surface + diff theo thời gian → sinh `PROGRAM.md` + `AGENT_BRIEF.md` để Claude agent `cd` vào hunt với ~0 token setup.

> 🚧 **Trạng thái: GIAI ĐOẠN SPEC** — chưa có code backend/frontend. Bản thiết kế thi công đầy đủ (kiến trúc, schema, API, build phases, ~70 test case) ở **[`BUILD_SPEC.md`](./BUILD_SPEC.md)**. README này mô tả sản phẩm *khi đã build xong*.

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

## Quickstart (sau khi code xong)

```bash
# 1. Clone KÈM submodule (bắt buộc)
git clone --recurse-submodules https://github.com/gloryy2k/advance_asm.git
cd advance_asm
# (nếu lỡ clone thiếu:  git submodule update --init)

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
# backend
cd backend && pip install -r requirements.txt && uvicorn main:app --reload
# frontend
cd frontend && npm install && npm run dev
```

Chạy test (unit — không cần tool recon thật):
```bash
cd backend && pytest -m "not integration"
```
Integration/e2e (cần subfinder/nuclei/httpx… + Docker) chạy trên Kali/Linux:
```bash
pytest -m integration
```

---

## Cấu trúc repo

```
advance_asm/
├── BUILD_SPEC.md              # spec thi công đầy đủ (nguồn chuẩn)
├── .env.example  .gitattributes
├── docker-compose.yml  Dockerfile  entrypoint.sh   # (sẽ tạo khi build)
├── backend/                   # FastAPI (sẽ tạo)
├── frontend/                  # React/Vite (sẽ tạo)
├── vendor/claude-bug-bounty/  # submodule framework (pin @32131c1)
├── targets/                   # output per-target (gitignore)
└── data/bbasm.db              # SQLite (gitignore)
```

---

## An toàn & phạm vi

Chỉ scan target **trong scope** bạn cung cấp — dashboard có scope gate chặn cứng (wildcard + IP/CIDR), audit mọi outbound. Không tự khai thác / submit / spray. `strong` depth (nmap/ffuf) chỉ dùng khi scope cho phép active scan.

## License / nguồn

Framework recon vendored từ [`claude-bug-bounty`](https://github.com/gloryy2k/claude-bug-bounty) (fork của Agentic Bug Hunter). BBASM là lớp dashboard/orchestrator trên framework đó.
