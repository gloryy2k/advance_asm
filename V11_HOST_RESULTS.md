# BBASM v1.1 — kết quả QA trên host

Ngày 2026-10-14 (Asia/Saigon). Nhánh nguồn `claude/upbeat-thompson-b7bb23` tại `fabd1c7`; nhánh kết quả `test/v11-host-results`. Không merge `main`, không gọi HackerOne thật và không scan host ngoài. Mọi scan API chỉ nhắm `127.0.0.1`; UI HackerOne dùng mock. Docker chạy trong worktree `../advance_asm-v11test`, project `bbasm-v11`, port `127.0.0.1:18765`. Ảnh UI nằm ở thư mục tạm `bbasm-v11-ui/shots`, không commit. Không ghi token thật.

## Lệnh, kết quả, bằng chứng

| Mã | Lệnh/Hành động | PASS/FAIL/SKIP | Bằng chứng ngắn |
|---|---|---|---|
| T0-1 | `git fetch origin`; `git switch claude/upbeat-thompson-b7bb23 && git pull`; `git submodule update --init --recursive`; `git switch -c test/v11-host-results` | PASS | `fabd1c7`; submodule `7acb66a`. Fetch/pull cần quyền mạng ngoài sandbox; sau đó `Already up to date`. |
| T0-2 | OS, `python --version`, `node --version`, `docker --version`, `docker compose version`, `git log -1`, `git submodule status` | PASS | Windows NT 10.0.26300.0; Python 3.13.2; Node 22.16.0 (≥22.12); Docker 28.3.2; Compose 2.38.2. |
| T1-PY | `python -m venv .venv`; `.venv/Scripts/python -m pip install -r requirements.txt`; `.venv/Scripts/python -m pytest -m "not integration" -q` | **FAIL** | `258 passed, 1 failed, 15 deselected` trong 21.55s. `test_hunt_command_uses_the_users_path_not_the_containers`: command nhận `C:\\Users...` thay vì `C:\Users...` (F1). Venv/pip và pytest cần quyền ngoài sandbox. |
| T1-FE | `cd frontend && npm ci && npm test && npm run build` | PASS | 33/33 Vitest; `tsc -b && vite build` thành công. `npm ci` cần quyền ngoài sandbox sau lỗi npm `Exit handler never called`. |
| T2-SETUP | `.venv/Scripts/python -m pip install playwright`; `.venv/Scripts/python -m playwright install chromium` | PASS | Playwright 1.64.0, Chromium sẵn để chạy headless. |
| T2-WS | `python -m pytest -m integration backend/tests/test_websocket_runtime.py -q` | PASS | 1 passed; handshake/replay uvicorn thật. |
| T2-MOCK | `python -m pytest -m integration backend/tests/test_ui_e2e_mock_h1.py -q` | PASS | 7 passed; gồm 5 route ở 390px với `document.scrollWidth <= innerWidth`. Hai suite T2-WS + T2-MOCK chạy chung: `8 passed, 1 deselected`. |
| T2-WIN | `python -m backend.main` trên `127.0.0.1:18767`, data/targets tạm, `BBASM_E2E_TARGET=127.0.0.1 BBASM_E2E_URL=http://127.0.0.1:18767 python -m pytest -m integration backend/tests/test_browser_integration.py -q` | **FAIL** | Sau 362.64s: badge `lỗi`, không phải `hoàn tất`. DB scan_run: `RuntimeError: Real recon requires Linux/WSL2/container process groups`. Backend Windows native không hỗ trợ recon thật; process tạm đã dừng. |
| T2-DOCKER | Cùng browser test, `BBASM_E2E_URL=http://127.0.0.1:18765` (backend Linux trong Docker) | PASS | 1 passed trong 5.11s, target `127.0.0.1`. |
| T3-BUILD | Worktree riêng: `.env` tạm chỉ `BBASM_PORT=18765`, `BBASM_UPDATE_TEMPLATES=0`; `docker compose -p bbasm-v11 up -d --build` | PASS | Build 15.8s, phần lớn layer cached. Port ban đầu bị container cũ chiếm; theo chỉ dẫn người dùng đã dừng đúng `bbasm-p8-windows-bbasm-1`, rồi stack QA khởi động. Không tạo `.env` chứa `/opt` hay `/app`. |
| T3-RUNTIME | `GET /api/health`, `GET /`, WebSocket `ws://127.0.0.1:18765/ws/scan/<draft>` qua `websockets`; `find ... '*.sh' | xargs bash -n`; kiểm byte CRLF | PASS | Health `ok=true`, mọi `missing_by_depth=[]`, `h1_api=false`; tools chính true, riêng `bbscope=false`; `/` 200; WS 101; `bash -n` exit 0; 0 shell script CRLF. |
| T3-TEST | `BBASM_DOCKER_TESTS=1 python -m pytest -m integration backend/tests/test_docker_integration.py -q -s` | PASS | 1 passed; build riêng 3.36s (cached), container/image do test tạo được test tự dọn. |
| T4-A | `python scripts/v11_host_probe.py` → `POST /api/scope/preview` 9 chuỗi raw + 4 dạng H1 | PASS | `#OUT`/`OUT:` là header OUT và không tạo IN; `# OUTT`, CIDR non-strict, `bad host!!` bị lỗi; `a.com, b.com` tách 2; range IP ra 6 CIDR/IP; wildcard có scheme và host:port có cảnh báo; cả 4 dạng H1 nhận `acme`. Phù hợp `test_scope_parse.py`. |
| T4-B | Resolve raw `127.0.0.1` → launch passive `automation_ack=false` → poll done; đọc summary/brief/program/scaffold/audit | PASS | scan #2 `done`; `AGENT_BRIEF.md` 688 byte (<12000), `PROGRAM.md` có `## Policy`; `.scope`, `audit.jsonl` tồn tại; audit chứa `scope_resolved`, `scan_finished`; summary có `new=1`. |
| T4-C | `GET /api/programs/v11-local/export?include_recon=true/false`; mở ZIP và parse `MANIFEST.json` | PASS | True: 23 entry có `recon/`; false: 10 entry, không có `recon/`. Cả hai có `.scope`, `PROGRAM.md`, `AGENT_BRIEF.md`, `CLAUDE.md`, `audit.jsonl`, `findings/`, `notes/`, `reports/`, `MANIFEST.json` đúng §10. |
| T4-D | Resolve draft → `DELETE /api/scans/<id>`; kiểm `/api/drafts`, `/api/programs?include_drafts=true`; DELETE scan đã chạy | PASS | Draft biến mất cả hai danh sách; scan #2 trả 422 `invalid_state`. |
| T4-E | `POST /api/programs/v11-local/rescan` → passive lần 2; `GET /diff?limit=1&offset=0`, `/assets?limit=1&offset=0&q=127&category=ip` | PASS | Lần 2 `done`; diff `X-Total-Count=0`; assets `X-Total-Count=1`; pagination/filter phản hồi. |
| T4-F | Raw `127.0.0.0/30` passive; đọc assets và brief | PASS | Chỉ một asset `127.0.0.0/30`, category `cidr`, không có 4 IP rời; brief 778 byte, mục `ASSET MỚI` 0 dòng (≤30). |
| T4-G | Launch light trên `127.0.0.1`; đợi 3s rồi POST cancel; `docker compose -p bbasm-v11 top` | PASS | Scan `cancelled`; process list chỉ còn `/sbin/docker-init` và `python -m backend.main`, không còn nuclei/httpx/subfinder/katana/nmap/recon_engine. `ps` không có trong image; dùng `docker compose top`. |
| T4-H | SHA256 37 file trong worktree targets + dump bảng `program/scan_run/schedule`; `docker compose -p bbasm-v11 restart`; so lại | PASS | 3 program, 5 scan_run, 0 schedule lúc snapshot; SHA256 tất cả file giữ nguyên; bảng DB giống hệt sau chuẩn hóa tuple/list JSON. |
| T4-I | POST schedule enabled passive; stop container; SQLite `UPDATE schedule SET next_run_at='2026-01-01T00:00:00+00:00'`; start; poll; POST disable | PASS | `scan_run` #6 tự xuất hiện `trigger='scheduled'`, trạng thái `running` lúc quan sát; schedule đã tắt sau đó. |
| T4-J | Grep container logs + mọi `audit.jsonl` trong worktree cho `H1_TOKEN`, `H1_USER`, `GITHUB_TOKEN`, `CHAOS_KEY` | PASS | 0 marker trong logs, 0 trong audit; không có token thật trong môi trường thử nghiệm. |
| T5 | Trong image Linux: `python -m pytest -m integration backend/tests/test_recon_integration.py -q` | PASS | Sau symlink tạm `/app/vendor/claude-bug-bounty` → `/opt/claude-bug-bounty`, 4 passed. Lần đầu 1 fail vì test giả định vendor ở `/app/vendor`; lần kế có race `psutil.NoSuchProcess` ở ca hard_timeout, lần chạy lại 4 passed. Đây là test sentinel/process cleanup, chưa chứng minh scan recon đầy đủ trên host ngoài localhost. |
| T6-IMG | `review_tools/mock_h1_server.py` + `review_tools/ui_screenshots.py` với `SCR` ở thư mục tạm; Playwright headless | PASS | 24 ảnh: 12 desktop 1366px, 12 mobile 390px. Không lưu vào git. |
| T6-LAYOUT | Xem ảnh `m4_review.png`, `m5_run_done.png`, `m7_assets.png`, `d6_program_overview.png` | **FAIL** | Mobile Review cao 3408px (>4 viewport 800px), nút Launch ở cuối trang và không luôn truy cập được. Mobile Assets giữ bảng trong vùng cuộn ngang nội bộ; 5 route không làm trang cuộn ngang. Lệnh hunt có dấu `\` gấp đôi (F1). |
| T7 | `gh run list -R gloryy2k/advance_asm --commit fabd1c7 --limit 10 --json databaseId,name,status,conclusion,headSha,url` | SKIP | CLI trả `[]`: không có GitHub Actions run gắn với `fabd1c7` để đánh giá PASS/FAIL. |

**Tổng: 22 PASS, 3 FAIL, 1 SKIP** (26 dòng). PASS T5 chỉ xác nhận bài test có sẵn với path điều chỉnh tạm, như mô tả. Không xem lỗi Windows native T2 là lỗi UI: runner chủ động từ chối recon ngoài Linux/WSL2/container.

**Dọn tài nguyên:** `docker compose -p bbasm-v11 down` đã xóa container/network QA; `docker image rm bbasm-v11-bbasm:latest` đã xóa image QA. Theo yêu cầu bổ sung của người dùng, đã xóa riêng container `bbasm-p8-windows-bbasm-1` và image `bbasm-p8-windows-bbasm:latest`. `docker ps -a` và `docker image ls` không còn hai bản BBASM này. Compose không tạo named volume; giữ nguyên các thư mục bind-mount chứa dữ liệu trên host. Không chạy prune toàn cục.

## Finding mới

### F1 — P1: lệnh hunt sai trên Windows

- **Tái hiện:** Windows 10/11, chạy `python -m pytest -m "not integration" -q`; `backend/tests/test_scope_parse.py::test_hunt_command_uses_the_users_path_not_the_containers` fail. Trong ảnh UI mobile/desktop, lệnh copy hiển thị `cd "C:\\Users\\...\\targets\\acme" && claude`. Giá trị kỳ vọng là đường dẫn có một dấu `\` mỗi separator.
- **Tác động:** nút “Sao chép lệnh” có thể không vào đúng thư mục khi dùng Windows native; luồng bắt đầu hunt bị chặn. Không có token hay đường dẫn cá nhân đầy đủ trong báo cáo.
- **Hướng sửa:** ở `Settings.hunt_target` (`backend/config.py`), quote đường dẫn cho shell đích mà không JSON-escape backslash; giữ test Windows và thêm kiểm clipboard/browser. Không sửa code trong phiên QA này.

### F2 — P2: CTA Launch trên mobile nằm sau trang Review rất dài

- **Tái hiện:** chạy `review_tools/mock_h1_server.py`, `review_tools/ui_screenshots.py`; xem ảnh 390×3408 `m4_review.png`. Ở viewport 390×800, phải cuộn hơn bốn màn hình mới tới khối “Xác nhận & chạy”.
- **Tác động:** TC-UX-8 yêu cầu Launch luôn truy cập được chưa đạt về khả năng tiếp cận, dù `document.scrollWidth <= innerWidth` đạt.
- **Hướng sửa:** sticky action bar cho Review với trạng thái disabled/lý do, hoặc điều hướng cố định tới xác nhận; kiểm bàn phím và viewport 390px. Không sửa UI trong phiên QA này.

### F3 — P3: recon integration không chạy nguyên trạng trong image và có race ở assertion cleanup

- **Tái hiện:** `docker compose -p bbasm-v11 exec -T bbasm python -m pytest -m integration backend/tests/test_recon_integration.py -q`: 1 fail vì tìm `/app/vendor/claude-bug-bounty/tools/recon_engine.sh`, trong khi image đặt vendor ở `/opt/claude-bug-bounty`. Tạo symlink tạm trong container rồi chạy: có lần fail `psutil.NoSuchProcess` khi child vừa thoát giữa `is_running()` và `status()`; chạy lại 4 passed.
- **Tác động:** kết quả T5 không ổn định khi chạy trực tiếp trong image; không thấy bằng chứng process tồn dư sau cancel thực tế.
- **Hướng sửa:** test lấy tool path từ `Settings.tool_path()` hoặc chạy từ checkout Linux có vendor; assertion `dead()` bắt `psutil.NoSuchProcess` như trạng thái thành công. Không sửa test/product trong phiên QA này.

## Chưa chạy hoặc giới hạn bằng chứng

- H1 thật, Live Nation, token thật, agent thật và hunt ngoài localhost: chủ ý không chạy theo ràng buộc; xem checklist test tay.
- Full recon trên domain thực: chủ ý không chạy. Health image báo đủ tool theo depth (trừ `bbscope=false`), nhưng T5 chỉ kiểm sentinel và process cleanup. Light cancel trên `127.0.0.1` đã chạy.
- Browser E2E bằng backend native Windows thất bại do runner yêu cầu Linux/WSL2/container; cùng bài test pass qua Docker. Trạng thái lỗi scan ở DB: `RuntimeError: Real recon requires Linux/WSL2/container process groups`.
- Tương phản AA/Lighthouse/axe, hiệu năng Diff/Assets >1000 dòng, thiết bị điện thoại thật và ngắt mạng thật: không thay người dùng đo; xem M5/M7.
- GitHub Actions: `gh run list` trả mảng rỗng cho commit nguồn nên chưa có run để kết luận.

## HƯỚNG DẪN TEST TAY

Chỉ dùng program và target mà bạn được phép kiểm thử. Ghi `☐ PASS / ☐ FAIL` cho từng mục; nếu FAIL, lưu bước và ảnh/log đã che dữ liệu nhạy cảm.

- **M1 — H1 thật: ☐ PASS / ☐ FAIL.** Đọc policy của một program **cho phép scan tự động** trước. Trong checkout riêng, điền `H1_USER`/`H1_TOKEN` vào `.env` local (không commit). Mở tab HackerOne, dán URL program, bấm Resolve. So IN/OUT/wildcard/CIDR/mobile/source với scope chính thức; policy phải hiện ở Review và tab Program. Trong “Nâng cao”, đặt rate limit không vượt policy. Chạy Passive trước; khi đã được phép, chọn Light và tick xác nhận. Xem Surface, Findings, Brief (<12KB). Bấm “Scan lại” lần hai, xem Diff; Portfolio phải hiện số NEW đúng.
- **M2 — Lệnh hunt Docker: ☐ PASS / ☐ FAIL.** Trong `.env` Docker đặt `BBASM_HOST_TARGETS` thành đường dẫn tuyệt đối tới `./targets` **trên máy bạn** (WSL2: đường dẫn Linux trong filesystem WSL2), restart compose. Ở Program bấm “Sao chép lệnh”, dán vào terminal thích hợp; `pwd`/`Get-Location` phải trỏ đúng `targets/<slug>`. Trên Windows native lưu ý F1 trước khi dùng nút copy.
- **M3 — Agent thật: ☐ PASS / ☐ FAIL.** `cd targets/<slug> && claude`; hỏi `tóm tắt scope, mục OUT, 3 việc nên làm`. Câu trả lời phải khớp `PROGRAM.md` và `AGENT_BRIEF.md`, không cần đọc lại toàn bộ recon.
- **M4 — Trải nghiệm: ☐ PASS / ☐ FAIL.** Ở 1366px và DevTools/điện thoại 390px, đi luồng “Thêm program → Review → Run → Program”. Ghi rõ màn hình, vị trí và lý do khó hiểu/khó bấm; kiểm nút Launch/CTA khi cuộn Review (F2).
- **M5 — WebSocket thật: ☐ PASS / ☐ FAIL.** Trong scan được phép và đủ lâu, refresh giữa lúc chạy: log cũ phải phát lại. Ngắt mạng ngắn rồi nối lại: trạng thái cuối vẫn tới “hoàn tất”, không kẹt ở “đang chờ”.
- **M6 — Windows/WSL2 (nếu dùng): ☐ PASS / ☐ FAIL / ☐ N/A.** Clone repo trong filesystem WSL2, `docker compose up`, mở UI từ Windows; lệnh hunt copy phải chạy trong WSL2 và vào đúng `targets/<slug>`.
- **M7 — Thiết bị/cảm quan: ☐ PASS / ☐ FAIL.** Dùng Lighthouse/axe kiểm tương phản AA ở dark/light; tạo dữ liệu kiểm thử >1000 dòng Diff/Assets trong môi trường được phép, đo độ mượt/phân trang và chiều cao trang (mục tiêu không quá 3 màn hình cho danh sách).
