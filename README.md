# advance_asm (BBASM)

Bug Bounty **Attack Surface Management** dashboard — tăng tốc & khử-token bước setup recon cho bug bounty / pentest.

Web dashboard (FastAPI + React, đóng Docker) ngồi trên framework [`claude-bug-bounty`](https://github.com/). Nhập HackerOne handle hoặc raw scope → recon (depth tùy chỉnh) → ranked attack surface + diff theo thời gian → sinh `AGENT_BRIEF.md` để Claude agent `cd` vào hunt với ~0 token setup.

## Trạng thái

🚧 **Đang ở giai đoạn spec.** Bản thiết kế thi công đầy đủ (kiến trúc, schema, API, build phases, ~50 test case) nằm ở **[`BUILD_SPEC.md`](./BUILD_SPEC.md)**.

## Quyết định kiến trúc đã chốt

- **Hình thức:** web dashboard ASM
- **Stack:** FastAPI + WebSocket + React/Vite + SQLite
- **Input:** HackerOne (handle/URL) + raw scope (domain/IP/CIDR/file)
- **Recon depth:** tùy chỉnh — `passive` / `light` / `strong` (gọi lại `recon_engine.sh`)
- **Portability:** Docker image
- **Agent bridge:** dashboard sinh `targets/<slug>/AGENT_BRIEF.md` + folder; user tự `cd && claude` (không spawn agent, không full-auto)
- **ASM features:** multi-program portfolio · continuous re-scan + diff · ranked surface · JS/secret + takeover monitor

Xem chi tiết & test cases trong [`BUILD_SPEC.md`](./BUILD_SPEC.md).
