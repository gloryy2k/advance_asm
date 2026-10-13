# P8 — Hồ sơ nghiệm thu

Nhánh bàn giao: `build/p8-acceptance` (bao gồm P3–P7b); vendor giữ `7acb66a`.
Ngày cập nhật: 2026-10-13. **P8 chưa hoàn tất**: cần chạy các mục thực tế trên
Kali/Docker. Không có scan thật hay Docker build trong môi trường triển khai.

## Bằng chứng hiện có

| Hạng mục | Kết quả / giới hạn |
|---|---|
| Backend unit | Sau handoff fixes: `pytest -m "not integration"`: 177 passed, 7 deselected; Windows Python 3.13.2 |
| Frontend | 6 Vitest tests và production build đã pass ở P6 |
| Coverage lõi | 93% tổng các module ASM, brief/export, runner, scope_gate; không phải coverage toàn repo |
| Docker | Compose parse và shell syntax pass; chưa build image hay kiểm CLI của các tool đã pin |
| P2 thực tế | Người dùng xác nhận tại parent `695ef2d`, vendor `7acb66a`: 124 unit + 3 integration; localhost light ~7s; health đúng |
| P3–P7 | Kali đã kiểm localhost tại 4882a9d; xem P3_P8_REVIEW_RESULTS.md. HIGH-1 teardown vừa sửa, chưa được revalidate thực tế |
| CI remote | Có workflow unit/frontend/shell; chưa xác nhận kết quả GitHub Actions của nhánh bàn giao |
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

Chạy backend bằng `python -m backend.main` sau khi kiểm ENV local (không dùng
đường dẫn container trong `.env` cho dev). Hoặc copy `.env.example` sang `.env`
nếu chưa có, rồi `docker compose up -d --build`.

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

Ưu tiên sau khi pull bản fix: chạy
`pytest -m integration backend/tests/test_recon_integration.py` (có 3 trường hợp
teardown GNU timeout: cancel, hard timeout, parent đã thoát). Sau đó lặp light
scan localhost có nuclei và cancel/timeout; xác nhận toàn bộ process của scan
đã chết. **Chưa gỡ trạng thái chặn merge HIGH-1 cho đến khi Kali xác nhận lại.**
Thử DB mới với targets cũ trên dữ liệu test: output được giữ trong `.orphan-*`,
scan mới chạy được. Thử web localhost 200 → tắt server → scan hoàn tất:
diff status 200 → null; passive/partial không tạo sự kiện offline giả.

1. Docker build/start trên máy chỉ có Docker; health báo tool, dashboard tải được.
   Kiểm cả Windows/WSL2 và Linux; kiểm volume DB/target còn sau restart.
2. H1 light: review IN/OUT/category/policy đúng, chỉ launch sau review; raw domain,
   wildcard, IP/CIDR và mobile/source scope đúng luồng. Lưu scan ID và audit.
3. Hai scan cùng program: portfolio NEW, surface/rank/reasons, diff NEW/GONE/CHANGED;
   partial không đánh gone sai. Đối chiếu output thực với dữ liệu dashboard.
4. Monitoring persist qua restart và scan theo lịch; không chạy chồng program.
   Kiểm monitor JS/secret/takeover bằng fixture được phép có finding, không chỉ exit 0.
5. Brief dưới 12000 byte, đủ scope/số liệu; PROGRAM giữ sửa tay; ZIP giải nén và
   manifest đúng, cả hai chế độ include_recon. Tự mở folder bằng agent để đánh giá handoff.
6. Cancel thật dọn process con; WS reconnect replay; điện thoại/narrow viewport.
7. Xem CI của commit bàn giao; bổ sung kết quả, commit, host, scan ID, thời gian vào file này.
8. Đo token fixture bằng `python -m pip install tiktoken` rồi
   `python scripts/measure_tokens.py`; tokenizer có thể tải encoding lần đầu.
   Ghi JSON vào README, phân biệt fixture với phép đo hunt thực tế.

## Quyết định cần review

- TC-RK-1 đã sửa thành >=6 theo handoff; công thức và trọng số giữ nguyên.
- Scope bắt buộc quá lớn cho brief sẽ báo lỗi, không lược bỏ quy tắc scope.
- Audit hiện ghi scope và subprocess spawn, **không ghi/chặn mọi request nội bộ
  của tool**. Đây là giới hạn đã ghi từ P2; không chứng minh network containment.
- Tool Docker được pin nhưng chưa compile/scan kiểm tương thích CLI; Node >=22.12.
- Schedule khi không gửi config lấy defaults của depth chọn, không tự sao chép
  mọi lựa chọn của scan trước. Backend chạy một process để tránh lịch trùng.

Nếu lỗi: ghi command, commit, OS, traceback đã bỏ secrets và scan ID; không ghi
credential/raw secret vào Git. Các báo cáo P0–P2 cũ trong NOTES là lịch sử.
