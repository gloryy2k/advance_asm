# BBASM v1.2 — kết quả QA trên host

Ngày 2026-10-14 (Asia/Saigon). Nguồn `claude/upbeat-thompson-b7bb23` tại `d3d813a`; kết quả trên `test/v12-host-results`. Không merge `main`, không gọi HackerOne thật và không scan host ngoài `127.0.0.1`. Docker v1.2 chạy trong `../advance_asm-v12test`, project `bbasm-v12`, tại `http://127.0.0.1:18765`. Theo yêu cầu mới nhất của người dùng, **giữ container v1.2 chạy để kiểm tra giao diện**; không thực hiện bước `down`/xóa image v1.2 trong prompt cũ. Container và image v1.1 đã được gỡ, dữ liệu v1.1 giữ lại để đối chiếu migration.

## Lệnh, kết quả, bằng chứng

| Mã | Lệnh/Hành động | PASS/FAIL/SKIP | Bằng chứng ngắn |
|---|---|---|---|
| T0 | `git fetch origin`; switch/pull nhánh nguồn; `git submodule update --init --recursive`; tạo `test/v12-host-results`; kiểm version | PASS | Windows 10.0.26300; Python 3.13.2; Node 22.16.0; npm 10.9.2; Docker 28.3.2; Compose 2.38.2; commit `d3d813a`, submodule `7acb66a`. Một lần `git submodule status` bị MSYS permission, lần sau thành công. |
| T0-OLD | `docker compose -p bbasm-v11 down`; xóa riêng image `bbasm-v11-bbasm:latest` | PASS | Đã dừng/xóa container, network, image bản QA cũ theo yêu cầu người dùng; không prune toàn cục, không xóa `advance_asm-v11test/data` hay `targets`. |
| T1-PY | `python -m venv .venv`; `pip install -r requirements.txt`; `python -m pytest -m "not integration" -q` | **FAIL** | **293 passed, 8 failed, 25 deselected** so với kỳ vọng 301. Hai test hunt command lỗi phân cách path POSIX trên Windows; sáu test khác cố enqueue recon native Windows và nhận `platform_unsupported`/422. Xem F5. |
| T1-FE | `cd frontend && npm ci && npm test && npm run build` | PASS | 46/46 Vitest; TypeScript/Vite build thành công. |
| T1-PLAY | `pip install playwright`; `python -m playwright install chromium` | PASS | Playwright/Chromium dùng cho browser headless. |
| T1-WSUI | `pytest -m integration backend/tests/test_websocket_runtime.py backend/tests/test_ui_e2e_mock_h1.py -q` | **FAIL** | 17 passed, 1 failed, 1 deselected. Ca H1 mock policy/Launch thất bại trên backend Windows native: lần đầu nút tắt khi plan cập nhật; chạy lại nút bấm được nhưng backend hiện cảnh báo Windows không chạy recon và không tới Run/done. Các ca UI khác và WebSocket pass. |
| T1-BUILD | `docker compose -p bbasm-v12 up -d --build` trong worktree riêng, `.env` tạm có `BBASM_PORT=18765`, `BBASM_UPDATE_TEMPLATES=0` | PASS | Build 11,5 giây, phần lớn cached; `bbasm-v12-bbasm-1` healthy, bind `127.0.0.1:18765`. Không dùng `.env` gốc hay path container trong `.env`. |
| T1-DOCKER | `BBASM_DOCKER_TESTS=1 pytest -m integration backend/tests/test_docker_integration.py -q -s` | PASS | 1 passed. |
| T1-BROWSER | `BBASM_E2E_TARGET=127.0.0.1 BBASM_E2E_URL=http://127.0.0.1:18765 pytest -m integration backend/tests/test_browser_integration.py -q` | PASS | 1 passed trên backend Linux trong Docker. |
| T1-RECON | Trong image: `pytest -m integration backend/tests/test_recon_integration.py -q` | **FAIL** | 3 passed, 1 failed: test hardcode `/app/vendor/...`, image đặt vendor ở `/opt/claude-bug-bounty` (lỗi F3 đã biết từ v1.1). Chạy unit suite trong image cũng không collect được vì image thiếu package `scripts`; kết quả unit chính là Windows host ở trên. |
| T1-CI | `gh run list --repo gloryy2k/advance_asm --commit d3d813a --limit 10` | SKIP | CLI trả rỗng, không có Actions run gắn với commit nguồn để kết luận PASS/FAIL. |
| T2-A | `POST /api/scope/preview` với 11 dạng raw, ô OUT riêng, so danh sách program trước/sau | **FAIL** | Parser nhận header OUT, gộp `bad host!!` thành một lỗi, range lớn thành ≤32 CIDR; preview thuần, không tạo draft. Nhưng `scope=["a.com"]`, `scope_out=["a.com"]` trả `ok=true`, `IN=1`, `OUT=1`, vẫn hiển thị host ở IN (F4). |
| T2-B | Preview 6 dạng H1 handle/URL, gồm `?type=team`, `www.`, fragment | PASS | Cả 6 chuẩn hóa thành handle `acme`; chỉ kiểm parser, không gọi H1 thật. |
| T2-C | Resolve draft raw `127.0.0.1`; GET drafts/programs; DELETE draft; DELETE scan đã chạy | PASS | Draft #2 xuất hiện trong drafts, không ở portfolio; DELETE xóa sạch; scan đã chạy trả 422 `invalid_state`. |
| T2-D | `GET /api/meta/phases`; `POST /api/meta/plan` passive/light; `GET /review` | PASS | Đủ 12 phase với key/title/what/touches/tools/view; trạng thái, forced và lý do; review có scope/policy/path. |
| T2-E | Launch Passive trên `127.0.0.1`; poll; `GET /phases`, `/artifact`, `/artifact/download`; traversal và symlink | PASS | Scan #2 done; 12 phase có ran/skipped/no_output; file pagination trả 200; traversal, absolute, encoded traversal và symlink `/etc/passwd` đều 422 `artifact_unavailable`. |
| T2-E-SECRET | File QA chứa marker secret giả; đọc `/artifact` mặc định, `reveal=true`, `/artifact/download` | **FAIL** | API trả `redacted=true` nhưng nội dung mặc định **vẫn chứa marker giả**; download trả raw. File QA đã xóa. Xem F1. |
| T2-F | Light `automation_ack=false`; kiểm UI acknowledgement | **FAIL** | API launch trả 200 dù chưa ack; scan thử được cancel ngay. UI có checkbox gate, backend chưa cưỡng chế (F6). Không quét host ngoài localhost. |
| T2-G | Passive #4 → Light #5 → Light #6 trên `127.0.0.1`; HTTP fixture nội bộ cổng 80; cancel #8 → Light #9 | PASS | #5 so #4: **changed=1**, HTTP status `null→200`, tech thêm; #6 so #5: 0; #9 bỏ qua cancelled #8, baseline #6: 0. [Dữ liệu diff](review_evidence/v12_diff_chain.json) không có raw URL/token. |
| T2-H | `/urls`, `/urls/summary`, `/urls/export` và các filter trên scan localhost; mock H1 demo qua UI E2E | PASS | Endpoint/filter/pagination phản hồi 200; scan IP Passive có 0 URL nên không chứng minh nội dung inventory thực bằng scan này. E2E mock bao phủ funnel/tag/export; dữ liệu 8.8k URL được kiểm ở T3. |
| T2-I | Profiles POST/PUT/duplicate/default/delete, field lạ 422, resolve dùng default | **FAIL** | CRUD và seed default hoạt động; PUT một profile `based_on=passive` với config từng phần nhưng không có `depth` đổi ngầm thành `light` (F7). |
| T2-J | Export ZIP `brief`, `filtered`, `full`, mặc định; kiểm MANIFEST và bơm một dòng URL ngoài scope giả | PASS | Brief 0 file `recon/`; filtered/full 13 file `recon/`; mặc định filtered. Filtered bỏ 1 dòng ngoài scope, full giữ; original bytes được khôi phục. Brief <12KB. |
| T2-K | Hunt command với `BBASM_HOST_TARGETS` Windows có dấu cách, rồi bỏ biến | PASS | Docker summary sinh `cd "E:\...\QA Targets\<slug>" && claude` với một dấu `\` mỗi separator; fallback dùng `targets/<slug>`. Test Windows unit với path POSIX còn fail (F5). |
| T2-L | `/api/health`; `docker compose exec bbasm httpx -version` | PASS | Health ok, `h1_api=false`, `runtime.os=Linux`, `recon_supported=true`, mọi `missing_by_depth=[]`; httpx là binary ProjectDiscovery v1.12.0. |
| T2-M | Light cancel sau 3 giây; `docker compose -p bbasm-v12 top` | PASS | Scan #8 cancelled; không còn nuclei/httpx/subfinder/katana/nmap/recon_engine trong process list. |
| T2-N | SHA256 66 file `targets/` + bảng program/scan_run/schedule → compose restart → so; ép schedule quá hạn lúc container dừng | PASS | 66/66 hash, row counts và schedule rows không đổi sau restart. Tick tạo scan #10 `trigger=scheduled`, `done`; schedule được tắt. |
| T2-O | Quét log container và audit JSONL cho tên biến/marker secret | PASS | 0 chuỗi `H1_TOKEN`, `H1_USER`, `GITHUB_TOKEN`, `CHAOS_KEY` và marker giả sau khi dọn file thử. Giới hạn: không chứng minh mọi mẫu secret sẽ bị che. |
| T3-AUTO | Copy DB v1.1; chạy backend v1.2 với `BBASM_DATA` bản sao ở cổng 18767 | **FAIL** | Startup giữ `schema_meta=1`, không tạo backup; `/api/programs` 200 nhưng `/urls` và `/urls/summary` 500 `OperationalError`. Xem F2. |
| T3-MANUAL | Trên bản sao: `Database(...).migrate()`; so bảng/backup; mô phỏng migration SQL lỗi rồi kiểm rollback | PASS | Migrate thủ công 96,6ms lên `schema_meta=2`, tạo `bbasm.db.bak-v1-20261014T123304Z`; 6 program, 12 scan, 8836 URL giữ nguyên. Lỗi giả rollback về v1, không có cột v2. SHA256 DB gốc trước/sau đều `a8913f3c…5e735e`. [Dữ liệu migration](review_evidence/v12_migration.json). |
| T3-URL | API trên DB bản sao đã migrate: URL funnel, filters/pagination, diff scan #12; đo phản hồi | **FAIL** | 8721 URL của scan mới nhất, `/urls?limit=50` 16,1ms, offset 1000 29,2ms, summary 25,2ms. **8836/8836 URL cũ không được backfill tag/shape/verification**, funnel null; UI lọc mặc định `min_score>=1` nên 0 dòng hiện ra. Scan #12 không re-ingest, baseline/diff vẫn null/0. Xem F3. |
| T4-IMG | `SEED_DEMO=1 python review_tools/mock_h1_server.py`; `SCR=<tmp> python review_tools/ui_screenshots.py` | PASS | 30 ảnh 1366/390px ở thư mục tạm, không commit; xem trực quan Review, Run, Program, URLs. |
| T4-MOBILE | Playwright headless 12 route ở 390×800; kiểm overflow, console, HTTP, Launch | PASS | 12/12 `document.scrollWidth<=innerWidth`; không console error/HTTP bất thường; Launch trên Review có ancestor `position:fixed`, bottom 0; Review 10 checkbox. |
| T4-AXE | Nạp axe-core headless trên 8 route | **FAIL** | 3 serious violation: Review/Run `link-in-text-block` (link khó phân biệt bằng màu, không underline), Help `scrollable-region-focusable` (vùng cuộn không focus được). Xem F8. |
| T4-PERF | Mở URL/Hosts trên bản sao DB có >1000 URL bằng Playwright | **FAIL** | Hosts hiển thị trong 281,8ms; URL không hiển thị hàng trong 10,7s quan sát vì filter mặc định loại toàn bộ dữ liệu cũ, không xác nhận được mục tiêu <2s cho hàng đầu. Không có JS error. Cùng nguyên nhân F3. |
| T5-LOG | `docker compose -p bbasm-v12 logs --no-color --tail 300` | PASS | Sau compose recreate/restart, log hiện tại chỉ có startup và health 200; không thấy 500/unhandled. Lỗi 500 migration xảy ra ở backend bản sao và đã ghi tại T3-AUTO. |
| T5-WS | Restart container giữa scan và xem WebSocket tự nối lại | SKIP | Không tạo ca scan dài chỉ để ép restart; các scan localhost hoàn tất quá nhanh. Unit WebSocket replay pass ở T1-WSUI; reconnect UI khi restart vẫn cần kiểm riêng. |
| T5-TIME | Đọc thời gian scan localhost | PASS | Passive khoảng 1,5 giây; Light probe khoảng 8–9 giây trên fixture nội bộ. Đây không phải ước lượng thời gian cho host thật. |

**Tổng: 24 PASS, 11 FAIL, 2 SKIP (37 dòng).** FAIL là kết quả kiểm không đạt hoặc hành vi cần sửa/giải thích; không có sửa code sản phẩm hay test trong phiên này.

## Finding mới và vấn đề còn tồn tại

### F1 — P1: artifact mặc định làm lộ nội dung giống secret

- **Tái hiện:** trong thư mục output của scan localhost, tạo file thử chứa marker kiểu token giả; gọi `GET /api/scans/2/artifact?path=...` không có `reveal`. Phản hồi 200, `redacted=true`, nhưng marker vẫn còn trong `lines`; `/artifact/download` cũng trả raw.
- **Tác động:** người xem file có thể thấy secret trong UI dù trạng thái báo đã che. Marker thử không phải credential thật và đã được xóa.
- **Hướng sửa:** áp dụng redaction lên chính nội dung trước khi trả API, kiểm cả download/ZIP theo chính sách rõ ràng; thêm test marker tổng hợp và xác nhận `reveal` chỉ có hiệu lực khi chủ động bật.

### F2 — P1: backend không tự migrate DB v1 khi khởi động

- **Tái hiện:** copy DB v1.1 vào `BBASM_DATA` riêng, chạy `python -m backend.main` v1.2; `schema_meta` vẫn 1, thiếu backup, `/api/programs/<slug>/urls` và `/urls/summary` trả 500. Gọi `Database.migrate()` thủ công thì migration thành công.
- **Tác động:** nâng cấp stack dùng DB hiện có làm hỏng chức năng URL và không có bản backup tự động như hướng dẫn.
- **Hướng sửa:** gọi migration có backup trước khi phục vụ request, xử lý lỗi startup rõ ràng; integration test mở bản sao DB v1 rồi gọi các API v2.

### F3 — P1: URL cũ không được phân loại khi migrate

- **Tái hiện:** sau khi migrate thủ công bản sao DB v1.1, 8836/8836 hàng URL có `tags_json`, `shape`, `verification` null. `/urls/summary` cho scan #12 có 8721 URL nhưng funnel null; tab URL mặc định (score ≥1) hiển thị 0 hàng.
- **Tác động:** người dùng thấy tab URL trống sau nâng cấp dù dữ liệu cũ vẫn tồn tại; không triage được 8,8k URL.
- **Hướng sửa:** backfill idempotent các cột phân loại/score trong migration hoặc có trạng thái “dữ liệu cũ chưa phân loại” và nút reclassify; test với DB v1 nhiều URL. Diff scan lịch sử #12 không tự tính lại, cần mô tả giới hạn hoặc cơ chế rebuild riêng.

### F4 — P2: preview scope không thể hiện OUT thắng IN khi cùng host

- **Tái hiện:** `POST /api/scope/preview` với `input=raw`, `scope=["a.com"]`, `scope_out=["a.com"]`; trả `ok=true`, `summary.in=1`, `summary.out=1`, host vẫn trong dòng IN.
- **Tác động:** người dùng dễ hiểu nhầm host OUT vẫn có thể scan; preview chưa thể hiện effective scope.
- **Hướng sửa:** tính effective IN sau loại OUT và báo xung đột rõ theo ô/dòng; chặn Launch nếu effective IN rỗng. Đối chiếu cả resolver và scan target.

### F5 — P2: bộ test Windows và path hunt command chưa nhất quán

- **Tái hiện:** `python -m pytest -m "not integration" -q` trên Windows: 8 fail. Path POSIX cấu hình qua `BBASM_HOST_TARGETS` bị chuyển dấu `/` thành `\` trong 2 test; 6 ca khác cố chạy recon native dù runtime báo `platform_unsupported`. E2E H1 mock tương tự không tới Run/done trên Windows.
- **Tác động:** gate 301 unit / 17 E2E không xanh trên host Windows dù Docker browser integration pass; lệnh hunt với path kiểu WSL cần kiểm thật.
- **Hướng sửa:** phân biệt test runner Linux và Windows, hoặc chạy suite recon trong container; giữ test path Windows và WSL đúng shell đích. Mock H1 E2E có thể dừng tại Review trên Windows hoặc dùng backend Linux.

### F6 — P2: API nhận Light scan thiếu xác nhận policy

- **Tái hiện:** resolve raw localhost, `POST /api/scans/<id>/launch` với `depth=light`, `automation_ack=false`; trả 200 và bắt đầu scan. UI checkbox thì chặn.
- **Tác động:** client gọi API trực tiếp bỏ qua bước xác nhận mà UI đặt ra.
- **Hướng sửa:** kiểm ack phía backend cho depth chạm target, lưu audit; bảo đảm Passive vẫn cho phép ack=false.

### F7 — P2: sửa profile từng phần làm đổi depth ngầm

- **Tái hiện:** POST profile `based_on=passive` với config không có depth; PUT cùng profile `based_on=passive`, config partial `threads=1, rate_limit=1`; phản hồi `config.depth=light` dù `based_on=passive`.
- **Tác động:** lần scan sau có thể chạm target nhiều hơn preset người dùng nghĩ đã lưu.
- **Hướng sửa:** khi PUT, merge config hiện tại trước normalize, dùng `based_on` nhất quán với POST; test partial update giữ depth.

### F8 — P2: 3 lỗi accessibility serious và nội dung mobile dài

- **Tái hiện:** axe-core ở viewport 390px: Review/Run `link-in-text-block`, Help `scrollable-region-focusable`. Ảnh Review mobile cao ~4,9k px, Run ~3,8k px; bảng URL có vùng cuộn ngang nội bộ dù trang không overflow.
- **Tác động:** liên kết khó nhận biết, vùng bảng không truy cập được bằng bàn phím; luồng mobile vẫn cần cuộn nhiều để hiểu đủ thông tin.
- **Hướng sửa:** underline hoặc thêm biểu đạt khác ngoài màu cho link trong text; `tabindex=0` và nhãn cho vùng cuộn; nhóm/thu gọn bước Review, giữ tóm tắt và Launch dễ thấy; kiểm bằng bàn phím và axe.

## Chưa chạy hoặc giới hạn bằng chứng

- Không thử HackerOne thật, token thật, host thật, thiết bị thật hay quét ngoài `127.0.0.1`; chỉ có mock H1 và dữ liệu DB cũ đọc trên bản sao.
- CI không có run cho `d3d813a`; WebSocket reconnect qua restart trong khi scan chạy chưa thử. URL inventory trên scan localhost không sinh URL, nên filter nội dung được đánh giá bằng E2E mock và DB v1.1 đã migrate thủ công.
- Hiệu năng UI URL >1000 dòng chưa đo được thời gian render hàng đầu vì F3 làm view trống. Không thể khẳng định target <2 giây đạt.
- Scan #9–#12 là dữ liệu lịch sử; không re-ingest và không quét lại target thật. Diff cũ ở #12 vẫn 0/null, còn chuỗi localhost mới chứng minh logic diff v1.2 hoạt động trên dữ liệu mới.
- Screenshot và script probe tạm không commit. Báo cáo JSON chỉ lưu số liệu đã loại raw URL/token.

## Dọn tài nguyên và trạng thái bàn giao

- Đã dừng/xóa stack và image `bbasm-v11` cũ theo yêu cầu bổ sung; không xóa dữ liệu bind mount v1.1. SHA256 DB gốc v1.1 trước/sau: `a8913f3c5db77f67600511032fa2035740df5d5d8daa737f26266d5f195e735e`.
- Backend migration bản sao và mock H1 được dừng. Thư mục tạm và ảnh QA ngoài repo được dọn sau khi trích số liệu; dữ liệu bằng chứng đã đưa vào `review_evidence/`.
- **Giữ `bbasm-v12-bbasm-1` và image `bbasm-v12-bbasm:latest`**, container healthy, cổng `127.0.0.1:18765`, để người dùng kiểm tra. Dữ liệu QA v1.2 nằm trong worktree `../advance_asm-v12test`, tách dữ liệu người dùng.

## HƯỚNG TEST TAY

- ☐ **PASS/FAIL — Diff thật:** chỉ chọn program bạn có quyền scan và đọc policy trước. Trên `http://127.0.0.1:18765`, chạy Passive → Light (HTTP probe bật, nmap/nuclei/active crawl tắt) → Light lần hai. Program → Lịch sử → Diff phải ghi baseline đúng và host có status/tech mới vào `changed`. Ghi scan ID, new/changed/gone; nếu 0 sai thực tế, lưu ảnh Diff/Hosts/Run.
- ☐ **PASS/FAIL — Dễ dùng:** xem Tổng quan, Review, Run, Program, Help, Profiles. Ghi rõ bước nào khó hiểu, công tắc có lý do tắt không, file kết quả mở/tìm được không, URL cần tìm có ra trong 30 giây không.
- ☐ **PASS/FAIL — Scope/H1 thật:** ở raw scope thử wildcard, bullet, chú thích, IP range, ô OUT, `# OUTT`, CIDR sai và `bad host!!`; preview phải chỉ ô/dòng lỗi. Với H1 có/không token trên máy bạn, so policy/scope với trang chính thức trước khi tick xác nhận; không tự động scan program không cho phép. Token chỉ để trong `.env` cá nhân, không commit.
- ☐ **PASS/FAIL — Mobile thật:** trên điện thoại cùng mạng tin cậy, nếu cần truy cập từ máy khác thì tạm đặt `BBASM_BIND=0.0.0.0` rồi tắt sau kiểm. Review/Run/URL không cuộn ngang trang, Launch luôn thấy/bấm được, chữ đọc được ngoài sáng.
- ☐ **PASS/FAIL — Hunt command:** cấu hình `BBASM_HOST_TARGETS` là path host đúng, bấm “Sao chép lệnh hunt” và dán vào terminal; phải vào đúng `targets/<slug>` rồi mở Claude. Thử path có khoảng trắng và WSL2 nếu dùng.
- ☐ **PASS/FAIL — Migration thật:** hiện **chưa nên thay DB thật** khi F2/F3 còn tồn tại. Sau khi có bản sửa, dừng stack, copy DB dự phòng riêng, nâng cấp, kiểm đủ program/scan/URL, backup `bbasm.db.bak-v1-<thời gian>`, URL funnel và rollback; giữ bản dự phòng ít nhất một tuần.
- ☐ **PASS/FAIL — Cảm quan/vận hành:** dùng bàn phím và Lighthouse/axe trên trình duyệt thật, xem URL/Assets >1000 hàng; thử refresh/ngắt mạng ngắn khi scan hợp lệ đang chạy để kiểm log phát lại và trạng thái cuối; scheduler tick qua ngày nếu cần.
