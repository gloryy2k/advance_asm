# P8 — Hồ sơ nghiệm thu

Nhánh bàn giao: `build/p8-acceptance` (bao gồm P3–P7b); vendor giữ `7acb66a`.
Ngày cập nhật: 2026-10-13. **P8 chưa hoàn tất**: cần chạy các mục thực tế trên
Kali/Docker. Không có scan thật hay Docker build trong môi trường triển khai.

## Bằng chứng hiện có

| Hạng mục | Kết quả / giới hạn |
|---|---|
| Backend unit | Sau dotenv fix: 195 passed, 7 deselected trên Windows và Kali tại 262b254; cũng pass với dotenv giả lập path container cũ |
| Frontend | 6 Vitest tests và production build đã pass ở P6 |
| Coverage lõi | 93% tổng các module ASM, brief/export, runner, scope_gate; không phải coverage toàn repo |
| Docker | Cold-cache build/run/health/static PASS tại 578c489 (960.66s tổng test); Compose path fix + cached build + health/static PASS tại 262b254, xem P8_DOCKER_PERSIST_RESULT.md |
| Persistence | Kali tại 262b254: DB/portfolio, target files, schedule/next_run giữ nguyên qua Compose restart; scheduler reload job thành công |
| P2 thực tế | Người dùng xác nhận tại parent `695ef2d`, vendor `7acb66a`: 124 unit + 3 integration; localhost light ~7s; health đúng |
| P3–P7 | Kali xác nhận 4/4 fixes tại 101b0ef, gồm cancel nuclei thật; HIGH-1 đã gỡ chặn, xem P8_FIX_VERIFICATION.md |
| CI remote | SUCCESS tại d011a0c và 262b254; [run d011a0c](https://github.com/gloryy2k/advance_asm/actions/runs/38384155496) kiểm tra trực tiếp qua GitHub API |
| Token benchmark | Kali tại 4882a9d: 32004 → 994 tokens, giảm 96.89%, brief 2638B; fixture-only, không phải hunt thật |

## Cập nhật và kiểm tra trên Kali

Giữ thay đổi local của bạn trước khi đổi nhánh; không dùng reset/clean.

```bash
git fetch origin
git switch build/p8-acceptance
git pull --ff-only origin build/p8-acceptance
git submodule update --init --recursive
git log -1 --oneline
git submodule status
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest -m "not integration"
# Node >=22.12
cd frontend
npm ci
npm test
npm run build
cd ..
```

`.env.example` mới dùng chung dev/Docker: path local dùng mặc định repo, Compose
đặt path container. Với `.env` từ mẫu cũ, comment/xóa chỉ BBASM_BBROOT/DATA/TARGETS/
STATIC đang trỏ `/opt` hoặc `/app` trước khi chạy dev; giữ API key và config khác.
Chạy backend bằng `python -m backend.main`. Với Docker, copy `.env.example` sang
`.env` nếu chưa có, rồi `docker compose up -d --build`.

```bash
# Integration hiện có; hai bài Docker/browser mới mặc định skip khi chưa opt in.
pytest -m integration
# Build image riêng, kiểm health/static rồi dọn đúng container/image vừa tạo:
BBASM_DOCKER_TESTS=1 pytest -m integration backend/tests/test_docker_integration.py
# Browser E2E: backend đang chạy + công cụ recon + domain bạn được phép kiểm tra.
python -m pip install playwright
python -m playwright install chromium
BBASM_E2E_TARGET=YOUR_AUTHORIZED_DOMAIN pytest -m integration backend/tests/test_browser_integration.py
# API smoke chạy recon thật và tải ZIP; thay target trước khi chạy:
make smoke TARGET=YOUR_AUTHORIZED_DOMAIN DEPTH=light
```

## Các mục còn cần xác nhận (§17, §22, §24)

HIGH-1 đã được Kali xác nhận lại bằng nuclei thật và 4 integration tests; xem
P8_FIX_VERIFICATION.md. Docker build/health/static đã pass tại 578c489; Compose
config/runtime và DB/targets/schedule qua restart đã pass tại 262b254. CI remote
cũng xanh tại d011a0c. Không cần lặp các bài đã đạt chỉ vì cập nhật tài liệu.
Lệnh Docker dưới đây giữ làm tham chiếu khi có thay đổi code/runtime cần regression:

```bash
BBASM_DOCKER_TESTS=1 pytest -s -m integration backend/tests/test_docker_integration.py
# Nếu host cần sudo, chỉ cấp quyền cho lần chạy test được chọn:
sudo env BBASM_DOCKER_TESTS=1 .venv/bin/python -m pytest -s -m integration backend/tests/test_docker_integration.py
```

Chạy một trong hai lệnh phù hợp với quyền Docker trên host. Ghi commit, elapsed
build time, kiến trúc, cold/warm cache, kết quả health/static vào báo cáo. Test vẫn
giới hạn 3600s. Kết quả 960.66s là tổng test, không tách riêng thời gian compile/download.

### Cập nhật Windows/browser ngày 2026-10-14

Xem P8_WINDOWS_BROWSER_RESULT.md (B1/B2 và lỗi CRLF trong image đã sửa).

1. Browser resolve → review → launch passive localhost → Brief: official pytest
   PASS (7.35s). WS thật trả 101; fallback khi WS lỗi có regression tests.
   Reconnect/narrow viewport thực tế vẫn cần đối chiếu checklist chi tiết.
2. Windows/WSL2: Docker Desktop build/run/health/dashboard và DB/schedule/target
   persistence PASS trên máy Windows của người dùng.
3. H1 Live Nation: resolve metadata 22 web + 3 mobile PASS; full policy không có
   trong public fallback. Policy chính thức cấm scanner/LLM discovery nên không
   launch. H1 light scan/handoff cần program khác cho phép automation.

### Đối chiếu chi tiết trước khi đóng P8

Các mục có bằng chứng đã đạt không cần chạy lại; chỉ bổ sung phần chưa có bằng
chứng thực tế trong các báo cáo được liên kết.

1. Docker Linux và Windows/WSL2 build/runtime/persistence đã đạt; xem báo cáo tương ứng.
2. H1 light: review IN/OUT/category/policy đúng, chỉ launch sau review; raw domain,
   wildcard, IP/CIDR và mobile/source scope đúng luồng. Lưu scan ID và audit.
3. Hai scan cùng program: portfolio NEW, surface/rank/reasons, diff NEW/GONE/CHANGED;
   partial không đánh gone sai. Đối chiếu output thực với dữ liệu dashboard.
4. Monitoring persist/reload qua restart đã đạt; bổ sung bằng chứng tick thực tế
   chạy scan theo lịch nếu chưa có (khác với chỉ reload job); không chạy chồng program.
   Kiểm monitor JS/secret/takeover bằng fixture được phép có finding, không chỉ exit 0.
5. Brief dưới 12000 byte, đủ scope/số liệu; PROGRAM giữ sửa tay; ZIP giải nén và
   manifest đúng, cả hai chế độ include_recon. Tự mở folder bằng agent để đánh giá handoff.
6. Cancel thật dọn process con; WS reconnect replay; điện thoại/narrow viewport.
7. CI đã xanh tại d011a0c; kiểm lại khi có thay đổi code sau đó.
8. Token fixture đã đo và ghi README: 32004 → 994. Không cần đo lại nếu generator
   không đổi; đây không phải phép đo chi phí hunt thực tế.

## Quyết định cần review

- TC-RK-1 đã sửa thành >=6 theo handoff; công thức và trọng số giữ nguyên.
- Scope bắt buộc quá lớn cho brief sẽ báo lỗi, không lược bỏ quy tắc scope.
- Audit hiện ghi scope và subprocess spawn, **không ghi/chặn mọi request nội bộ
  của tool**. Đây là giới hạn đã ghi từ P2; không chứng minh network containment.
- Image release-binary đã build + health/static pass; test này chưa chứng minh
  mọi CLI recon chạy đúng. Subjack vẫn compile source pin riêng; Node >=22.12.
- Schedule khi không gửi config lấy defaults của depth chọn, không tự sao chép
  mọi lựa chọn của scan trước. Backend chạy một process để tránh lịch trùng.

Nếu lỗi: ghi command, commit, OS, traceback đã bỏ secrets và scan ID; không ghi
credential/raw secret vào Git. Các báo cáo P0–P2 cũ trong NOTES là lịch sử.

## v1.1 Guided UX — bổ sung nghiệm thu (TC-UX-*)

Đã có bằng chứng trong cloud sandbox (mock H1, Chromium): xem `backend/tests/test_ui_e2e_mock_h1.py`, `frontend/src/App.test.tsx`.

| TC | Nội dung | Trạng thái |
|---|---|---|
| UX-1 | Portfolio trống → có brief bằng raw `127.0.0.1` passive ≤5 click | E2E `test_browser_integration` PASS (sandbox) |
| UX-2 | URL H1 có `?type=team`, handle trần | Vitest + unit PASS |
| UX-3 | `#OUT`/`# OUTT`/`OUT:` không thể làm host OUT thành IN | unit + E2E PASS |
| UX-4 | Policy H1 hiện ở Review, có trong PROGRAM.md; depth ≠ passive cần xác nhận | E2E mock PASS — **H1 thật chưa** |
| UX-5 | CIDR /24 = 1 dòng; brief ≤12KB, ASSET MỚI ≤30 | unit PASS |
| UX-6 | Refresh giữ tab Program | E2E PASS |
| UX-7 | Scan xong hiện lệnh `cd … && claude` | Vitest + E2E PASS; **đường dẫn Docker/host cần xác nhận trên máy bạn** |
| UX-8 | 390px không cuộn ngang (5 route) | E2E PASS; tương phản AA chưa đo bằng công cụ |
| UX-9 | Lỗi API hiển thị câu tiếng Việt + gợi ý | Vitest PASS |
| UX-10 | Diff/Findings/Assets phân trang | unit + Vitest PASS (1000+ dòng chưa đo hiệu năng) |

Vẫn cần máy của bạn: Docker (kiểm `BBASM_HOST_TARGETS` và `cd targets/<slug>`), recon thật, H1 program được phép
(nên thử tab HackerOne với `H1_USER/H1_TOKEN` để xác nhận policy API thật), Windows/WSL2, tick scheduler thật.

## v1.2 — bổ sung nghiệm thu

Đã có bằng chứng trong cloud (mock H1 + dữ liệu mẫu `demo-shop`): 301 unit · 46 Vitest · 17 browser E2E (`test_ui_e2e_mock_h1.py`) · E2E gốc + WS pass.

| Mục | Bằng chứng | Còn cần trên máy bạn |
|---|---|---|
| Mỗi bước nói rõ: làm gì, chạm target?, đã chạy/bỏ qua/0 kết quả, xem ở đâu | E2E `test_results_are_explained_step_by_step_and_openable` | xem trên scan thật |
| URL inventory + phễu + lọc + export .txt | unit + E2E | chạy lại Passive #9 trên máy thật để xem 8.8k URL |
| Diff Passive→Light | TC-DF-5 | **chạy lại chuỗi Passive→Light trên máy thật** (R4) |
| Tuỳ chỉnh: bật/tắt bước, giá trị, profile, mặc định theo program | Vitest + E2E | dùng thử với program thật |
| Nhãn "CHƯA XÁC MINH" cho H1 công khai | unit + E2E | H1 thật có/không có token |
| Export `filtered` loại dòng ngoài scope | unit | kiểm ZIP với scan thật |
| Điện thoại: 10 route không cuộn ngang, nút Launch luôn thấy | E2E | thiết bị thật |
| Migration DB v1→v2 | TC-MIG-1..4 | **thử trên bản sao `data/bbasm.db` thật** (có backup tự động) |
