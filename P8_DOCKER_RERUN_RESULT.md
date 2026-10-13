# P8 — Docker acceptance RERUN sau fix binary-release (578c489)

> **Ngày:** 2026-10-13. **Nhánh:** `build/p8-acceptance` **commit `578c489`**, submodule `7acb66a`. **Host:** Kali, RAM 11GB, Docker 26.1.5 + compose v2.30.3, docker chạy qua sudo.

## ✅ KẾT QUẢ: Docker acceptance PASS

```
BBASM_DOCKER_TESTS=1 pytest -s -m integration backend/tests/test_docker_integration.py
-> 1 passed in 960.66s (0:16:00)
```
- `docker build` (binary-release, **không compile Go**) + `docker run` + kiểm `/api/health` + static dashboard: **PASS**.
- Test assert (đều đạt): `health.ok`, tất cả tool `bash, subfinder, httpx, nuclei, gau, nmap` = true trong container, static dashboard trả HTML chứa `root`.
- Thời gian **~16 phút** (gồm pull base image node/debian + tải binary + export layer; cache trống do đã prune trước đó). So với lần trước **>60 phút → timeout**. Build-perf finding ở `P8_DOCKER_RESULT.md` đã được xử lý hiệu quả.
- Stage `RUN test -f /opt/claude-bug-bounty/tools/recon_engine.sh` DONE → vendored framework có mặt trong image.
- Test tự dọn image sau khi xong (`Untagged/Deleted`).

## Unit tests
`pytest -m "not integration"` = **193 passed, 7 deselected** (khớp claim Codex) — **với điều kiện KHÔNG có `.env` chứa path container** (xem finding dưới).

## 🟠 FINDING mới (MED) — quickstart `cp .env.example .env` làm HỎNG dev/test
**Hiện tượng:** làm theo README quickstart (`cp .env.example .env`) tạo `.env` với `BBASM_BBROOT=/opt/claude-bug-bounty`, `BBASM_DATA=/app/data`, `BBASM_TARGETS=/app/targets` (path **container**). Khi chạy local, pydantic-settings đọc `.env` → `BBASM_BBROOT=/opt/...` → **13 unit test FAIL** (`FileNotFoundError: /opt/claude-bug-bounty/tools/recon_engine.sh`), và backend dev cũng trỏ sai thư mục.
**Bằng chứng:** có `.env` (từ example) → 13 failed / 180 passed; bỏ `.env` → 193 passed.
**Mâu thuẫn:** `NOTES.md` nói dev dựa vào default repo (`vendor/`, `data/`, `targets/`) và KHÔNG nên có `.env` container; nhưng README quickstart lại bảo `cp .env.example .env`. Hai chỉ dẫn xung đột.
**Hướng sửa (cho Codex):** tách path dev vs container. Ví dụ:
- `.env.example` để trống/hoặc comment các path (`BBASM_BBROOT/DATA/TARGETS`) để dev dùng default repo; path container `/opt`,`/app` chỉ set trong Dockerfile/`docker-compose.yml` (ENV), KHÔNG trong `.env.example`.
- Hoặc cung cấp 2 file: `.env.example` (dev, path repo) và `.env.docker.example` (container).
- Và/hoặc test ép `BBASM_BBROOT` qua fixture/monkeypatch để không bị `.env` ở CWD ảnh hưởng (test không hermetic).
**Lưu ý:** đây là lý do con số 193-vs-"13 fail" khác nhau giữa môi trường, không phải lỗi logic P3–P8.

## Tổng kết trạng thái nghiệm thu Docker
- compose config: ✅ · image build (binary-release): ✅ ~16' · container health đủ tool + static: ✅
- Còn lại P8 (chưa chạy, môi trường): browser E2E, Windows/WSL2, H1 program thật, CI remote.

## Phản hồi triển khai sau 336e271

- Đã sửa `.env.example`: comment cả bốn path BBROOT/DATA/TARGETS/STATIC; dev dùng
  defaults theo repo. Compose đặt path container riêng theo volume mounts.
- Shell unit helper dùng `_env_file=None`; regression xác nhận dotenv container
  không ảnh hưởng. **195 unit pass, 7 deselected**, cả lần chạy mô phỏng dotenv cũ.
- Compose parse xác nhận path container đúng. Chưa chạy lại container sau thay đổi
  config này; hướng dẫn giữ API key khi chỉnh `.env` cũ có trong README/ACCEPTANCE.
- Đính chính mô tả build ở trên: 9 tool dùng release binary, **subjack vẫn compile**
  tại commit cũ trong stage riêng; 960.66s là tổng thời gian bài test acceptance.
