# P8 — Docker acceptance (chạy thật trên Kali)

> **Ngày:** 2026-10-13. **Nhánh:** `build/p8-acceptance` (sau `101b0ef`/`926d10c`), submodule `7acb66a`.
> **Môi trường:** Kali Linux, **RAM 11GB** (đã nâng sau lần treo trước), disk 42GB free, Docker 26.1.5, compose plugin v2.30.3 (cài tay system-wide).

## Kết quả: ❌ FAILED — `docker build` TIMEOUT (không phải lỗi runtime của image)

```
pytest -m integration backend/tests/test_docker_integration.py  (BBASM_DOCKER_TESTS=1, qua sudo)
-> subprocess.TimeoutExpired: Command ['docker','build','-t','bbasm-acceptance-…','.'] timed out after 3600 seconds
1 failed in 3602.27s (1:00:02)
```
Khi timeout, build mới compile tới **~6/11 tool Go** (đang tải dep của `gau`); **nuclei và amass chưa tới**. Vì vậy phần kiểm `/api/health` + static dashboard trong container **CHƯA chạy được** → **Docker runtime chưa được xác minh** (bị chặn bởi build-perf, không phải chứng minh image hỏng).

## ✅ Phần Docker đã xác minh được
- `docker compose version` v2.30.3; **`docker compose config` parse OK** (service `bbasm`) — sau khi tạo `.env` từ `.env.example`.
- `bash -n` entrypoint.sh / install_container_tools.sh: OK (các lần trước).
- Build chạy đúng tới stage compile Go, không OOM (RAM 11GB đủ) — vấn đề thuần là **thời gian**.

## 🔴 FINDING build-perf (CHẶN Docker acceptance) — cho Codex tối ưu

**Vấn đề:** `scripts/install_container_tools.sh` + Dockerfile **compile 11 tool Go từ source** (`go install …@ver`: subfinder, httpx, nuclei, dnsx, katana, gau, amass, ffuf, …) trong **một bước RUN**, tuần tự, build lại toàn bộ dependency. Trên host này **>60 phút**, vượt mốc `timeout=3600` trong `test_docker_integration.py` → test fail trước khi image hoàn tất. nuclei/amass là nặng nhất và còn chưa chạy tới.

**Hướng sửa (ưu tiên):** đổi sang **tải binary release dựng sẵn** cho `linux/amd64` từ GitHub releases thay vì compile:
- projectdiscovery: subfinder, httpx, nuclei, dnsx, katana (mỗi repo có asset `*_linux_amd64.zip`).
- gau (`github.com/lc/gau`), ffuf (`github.com/ffuf/ffuf`), amass (`github.com/owasp-amass/amass`) — đều có binary release.
- Pin version + verify checksum; `curl -sSL <release> | tar/unzip` vào `/usr/local/bin`. Giảm build từ ~60 phút xuống **vài phút**.
- (Phụ) nếu vẫn muốn giữ `go install` cho tool không có binary, tách thành nhiều layer để cache từng phần; và/hoặc nâng `timeout` trong test. Nhưng **binary release là fix đúng**.

**Sau khi tối ưu:** chạy lại `BBASM_DOCKER_TESTS=1 pytest … test_docker_integration.py` để xác minh image build nhanh + `/api/health` báo đủ tool (`bash,subfinder,httpx,nuclei,gau,nmap`) + static dashboard trả HTML (`b"root"`).

## Findings phụ (nhỏ)
- `docker compose` cần `.env` tồn tại (compose.yml có `env_file: .env`). Nên: thêm `.env` vào quickstart (`cp .env.example .env`) hoặc để `env_file` optional. Đã tạo `.env` local để parse.
- Docker ở host này cần `sudo` (user không trong docker group) — chỉ là ghi chú môi trường, không phải lỗi sản phẩm.

## Trạng thái nghiệm thu Docker
- Compose config: ✅
- Image build + container health/static: ❌ **chưa xác minh** — chặn bởi build-perf; làm lại sau khi Codex đổi sang prebuilt binaries.
- Các mục P8 khác (browser E2E, Windows/WSL2, H1 thật, CI remote): vẫn chưa chạy (xem `ACCEPTANCE.md`/`P3_P8_REVIEW_RESULTS.md`).

## Phản hồi triển khai sau d77a2c3 — chờ Kali retest

- Đổi 9 tool sang release binary cùng phiên bản cũ, cho amd64/arm64; SHA-256 pin
  trực tiếp trong `scripts/tool-releases.json`. Verify trước khi cài; không dùng latest.
- subjack compile riêng để giữ commit b53899ce6230 (release v3.1.0 khác commit).
  Mỗi release có layer cache riêng; build lỗi ở tool sau không tải lại tool trước.
- Test Docker giữ timeout 3600s, thêm số giây build và kiểm health đủ 9 release tools.
- Unit offline: **193 passed, 7 deselected**; shell syntax pass. **Không chạy Docker
  build tại máy triển khai; chưa có số đo thời gian hay xác nhận runtime mới.**
- Quickstart đã có `cp .env.example .env`; giữ cấu hình này. Hướng dẫn retest có
  lựa chọn sudo cho host cần quyền, xem ACCEPTANCE.md.
