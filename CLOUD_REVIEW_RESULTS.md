# CLOUD REVIEW RESULTS — build/p8-acceptance (review độc lập, sandbox cloud)

Ngày: 2026-10-14 · Reviewer: Claude (cloud, độc lập, không dùng hội thoại trước)
Commit được review: `430bca5` (đầu `build/p8-acceptance`), submodule `7acb66a`.
Môi trường: Linux sandbox, Python 3.13.16, Node 22.22.0, Chromium preinstalled (`/opt/pw-browsers/chromium-1194`),
**không có** Docker daemon, **không có** tool recon (chỉ có `bash`, `git`; xem F8).
Không merge main. Không scan target thật. Không sửa code sản phẩm (chỉ thêm `review_tools/` + file này).

> **Kết luận ngắn:** B1 và B2 **đã đóng và xác nhận bằng chạy thật**. Phần backend đúng spec và ổn định.
> **P8 chưa đóng** (còn các mục cần host có tool/Docker/H1 thật — mục 6). Đánh giá của người dùng về UI/UX **đúng**:
> review xác nhận 5 lỗi thật ảnh hưởng trực tiếp tới luồng H1/raw scope (F1–F5) và ~15 vấn đề UX (mục 4).
> Mục 5 là **kế hoạch chi tiết cho phiên bản mới (v1.1 "UX")**, không đổi kiến trúc §1 và non-goals.

---

## 1. Lệnh đã chạy và kết quả

| # | Lệnh / hành động | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | `git switch build/p8-acceptance`, `git submodule update --init --recursive` | PASS | submodule checkout `7acb66a` |
| 2 | `pip install -r requirements.txt` ; `python -m pytest -m "not integration" -q` | **PASS 197 passed, 8 deselected, 6.46s** (kỳ vọng ≥195) | |
| 3 | `cd frontend && npm ci && npm test && npm run build` | **PASS** 11/11 Vitest; `tsc -b && vite build` OK (353 kB JS / 108.8 kB gzip) | |
| 4 | `pytest -m integration backend/tests/test_websocket_runtime.py` | **PASS** (uvicorn thật, HTTP 101 + replay) | 1 passed |
| 5 | Chạy **uvicorn thật** `python -m backend.main` (port 18765, data tạm), client `websockets` ngoài process | **PASS B1** — handshake `/ws/scan/1?after=0` → `response.status_code == 101`; nhận `log`/`phase` realtime; scan `passive` tới `done` | log 40+ event, `GET /api/scans/1` → `done` |
| 6 | `BBASM_E2E_TARGET=127.0.0.1 … pytest -m integration backend/tests/test_browser_integration.py` | **PASS B2** — 1 passed 2.62s (resolve → review → Launch → badge `done` → Brief) | cần `pip install playwright==1.56.0` (bản mới hơn đòi chromium-1248, sandbox chỉ có 1194) |
| 7 | Luồng H1 đầy đủ qua `review_tools/mock_h1_server.py` (API H1 mock + policy + 7 loại asset), passive scan, đọc PROGRAM.md/AGENT_BRIEF.md | Chạy được; **phát hiện F1, F5** | mục 3 |
| 8 | Fuzz parser raw scope + H1 URL (25 + 14 ca) | **Phát hiện F2, F3, F4** | mục 3 |
| 9 | Screenshot 1366×850 và 390×800 cho mọi trang (`review_tools/ui_screenshots.py`) | Chạy; vấn đề UX mục 4 | |
| 10 | `docker …` / `test_docker_integration` | **SKIP** — có binary `docker` nhưng `Cannot connect to the Docker daemon` | |
| 11 | `test_recon_integration`, recon thật | **SKIP** — không có subfinder/nuclei/katana/gau/amass/ffuf/nmap | |

Lưu ý môi trường (đưa vào REVIEW_GUIDE nếu muốn): lệnh `pytest` trần trong sandbox này dùng môi trường `uv` không có deps → dùng `python -m pytest`.

### Xác nhận B1 / B2 (yêu cầu mục 4–5)
- **B1 đóng.** `requirements.txt` có `websockets==15.0.1`; `test_websocket_runtime.py` kiểm protocol auto + handshake thật; tôi tự xác nhận 101 bằng process uvicorn riêng.
  Frontend: `useData(path, revision, 3000)` poll `/api/scans/{id}` mỗi 3s tới trạng thái cuối (`done/done_partial/failed/cancelled`), `ScanLog` reconnect WS với `after=<last id>` và dừng khi `finished`. Test Vitest bao phủ WS hỏng.
- **B2 đóng.** `get_by_label("Depth", exact=True)` đã bỏ; test dùng `get_by_role("combobox", name="Depth", exact=True)` + `aria-label="Depth"` (App.tsx:285) và assert badge `role=status name="Scan status"`. Chạy thật trên Chromium: pass.

### Review code đối chiếu spec (mục 1)
Đạt spec, không thấy lỗi chặn trong: `scope_gate.py` (fail-closed, OOS ưu tiên, CIDR overlap cho deny, repo scope), `asm/diff_engine.py` (baseline bền, partial không đánh `gone`), `asm/ranking.py` (đúng §12.3, mỗi feature một lần), `asm/scheduler.py` (persist, coalesce, không chồng program), `brief/export.py` (đĩa, không symlink), `jobs/runner.py` (psutil cây tiến trình + `start_new_session` + `killpg` cuối; đã được Kali xác nhận bằng nuclei thật ở P8_FIX_VERIFICATION), `jobs/recon_orch.py` (gate trước mọi lệnh; env bị whitelist, skip toggle đúng bảng §8.2), `h1_scope.py` (không redirect, không proxy, không rò token, phân trang cố định).
Mức độ đọc: scope_gate/resolver/h1/recon_orch/ranking/diff/scheduler/generator/export/api/frontend đọc kỹ từng dòng; runner/ingest/monitors đọc ở mức cấu trúc + dựa trên test và bằng chứng Kali (không đọc từng dòng).

---

## 2. Danh sách phát hiện (ưu tiên)

| ID | Mức | Tóm tắt | Ảnh hưởng tới yêu cầu của người dùng |
|---|---|---|---|
| **F1** | **HIGH** | Policy H1 **không bao giờ** vào `PROGRAM.md` | "instruction H1 phải cẩn thận" |
| **F2** | **HIGH (an toàn)** | Raw scope: `#OUT`, `OUT:`… làm host OUT thành IN | "raw scope phải cẩn thận" |
| **F3** | MED | Parser raw scope quá cứng + phân loại sai im lặng; 1 dòng lỗi làm hỏng cả batch, không báo dòng nào | dễ dùng |
| **F4** | MED | URL H1 hợp lệ bị từ chối (`?type=team`, `www.`, không scheme, `/policy`) | dễ dùng |
| **F5** | MED | CIDR /24 → 254 "asset", brief/diff/portfolio ngập nhiễu | tối ưu chức năng |
| **F6** | MED | Resolve thay đổi DB ngay (program, scope_rule) + draft rác không xoá được; Brief/Program chỉ dùng được sau scan xong | dễ dùng |
| **F7** | MED | Review **không hiện policy**/cảnh báo automation (case Live Nation: policy cấm scanner nhưng UI không nói) | an toàn + H1 |
| **F8** | MED | `/api/health` báo `httpx:true` khi chỉ có `httpx` của Python (không phải ProjectDiscovery) | đúng nhiệm vụ |
| F9 | LOW | Monitoring lấy depth từ scan mới nhất (kể cả draft/cancelled), config mặc định không phải của scan đã duyệt | |
| F10 | LOW | Brief: không có rank reasons/instruction per-asset, "HƯỚNG TEST" là câu chung; ASSET MỚI không giới hạn số dòng | giá trị brief |

### Bằng chứng
**F1.** `h1_scope.resolve()` trả `policy={"program": {…,"policy": "<text>"}, "assets": […]}`; `brief/generator.py:81-82` đọc `policy.get("policy") or policy.get("description")` ở **cấp trên** → luôn rỗng.
Chạy thật (mock API trả `policy: "## Acme policy\nNo DoS…5 req/s…"`): `PROGRAM.md` ra `## Policy\nKhông có policy công khai; bổ sung quy định trước khi hunt.` Unit test hiện tại dùng policy phẳng nên không bắt được.
**Hướng sửa:** provider lưu `policy_text` (+ `policy_source: api|public_dump|none`, `fetched_at`); generator đọc `policy_text` và fallback `program.policy`; test dùng đúng shape provider; hiển thị ở Review (F7).

**F2.** Chạy `raw_entries([...])`:
- `["a.example.com","#OUT","b.example.com"]` → `b.example.com` là **IN** (dòng `#OUT` bị coi là comment).
- `["a.example.com","OUT:","b.example.com"]` → `OUT:` thành entry `other`, `b.example.com` vẫn **IN**.
- `# out` (chữ thường) thì đúng; chỉ khớp chính xác `# IN`/`# OUT` (hoa) sau `strip()`+`upper()`.
Placeholder ở ScanNew khuyến khích cú pháp `# OUT` trong một textarea → rất dễ gõ sai ở đúng chỗ an toàn nhất. Gate sau đó cho phép scan host mà người dùng muốn loại.
**Hướng sửa:** bỏ cú pháp ẩn: UI hai ô riêng **IN** / **OUT**; server vẫn chấp nhận header nhưng mọi dòng `#…` mà không phải header chuẩn → trả cảnh báo "dòng bị bỏ qua" và nếu trông như header (`/^#?\s*(out|oos|out[- ]of[- ]scope|exclude)/i`) → **lỗi 422**, không đoán.

**F3.** (kết quả fuzz) lỗi toàn batch, không nêu số dòng: `a.com, b.com` · `a.com b.com` · `a.com # note` · `- a.com` · `https://*.x.com` · `api.*.x.com` · `10.0.0.5/24` (CIDR không strict) · `github.com/acme/repo`.
Phân loại **sai nhưng chấp nhận im lặng**: `10.0.0.1-10.0.0.20` → `web/domain`; `https://github.com/acme` (không `repo:`) → `web`; `com.acme.app` → `web`; `localhost`/từ trần → `other`; `host:port`, đường dẫn URL bị nuốt (scope URL `https://app.x.com/login` mở rộng thành cả host `app.x.com` khi recon).
**Hướng sửa:** endpoint `POST /api/scope/preview` (không ghi DB) trả từng dòng `{line, status: ok|warn|error, kind, category, normalized, note}`; tách token theo `,`/khoảng trắng/`;`; bỏ bullet `-*•`, comment cuối dòng; hỗ trợ range `a-b` (mở rộng sang CIDR tối giản hoặc từ chối rõ); GitHub URL tự gợi ý `repo:`; `app id` dạng `com.x.y` → gợi ý `app:`; luôn hiển thị lý do; **có lỗi → không cho Resolve nhưng cho sửa tại chỗ**.

**F4.** Parser chặn: `https://hackerone.com/live_nation?type=team` (chính URL người dùng đã thử, phải gõ lại `h1:live_nation`), `https://www.hackerone.com/x`, `hackerone.com/x`, `…/x/policy`, `…#scope`, `@x`, `h1: x`.
**Hướng sửa:** chuẩn hoá phía client + server: bỏ query/fragment, `www.`, scheme thiếu, các hậu tố `/policy|/policy_scopes|/thanks|/hacktivity|/reports`; hiển thị "Nhận diện: handle = `live_nation`" trước khi gửi.

**F5.** Mock H1 có `198.51.100.0/24`; scan **passive** (không chạm target) → 255 asset (254 IP + 1), Portfolio "255 NEW", Surface toàn IP rank 1.5 "fresh", tab Diff 255 dòng không phân trang (**trang cao 44 835 px**), brief có 255 dòng `ASSET MỚI`. Với /16 sẽ là 65 534 dòng DB.
**Hướng sửa:** CIDR/IP là **range asset** (1 dòng, `host_count`); chỉ tạo asset IP khi quan sát được (httpx live/port open) và depth ≠ passive; phân trang mọi danh sách; brief giới hạn ASSET MỚI ≤30 + "…và N asset khác"; "fresh" không cộng cho asset không có tín hiệu thật.

**F6.** `ScopeResolver.resolve` tạo `program`, **xoá + ghi lại `scope_rule`** và ghi `.scope` ngay ở Pha 1, trước khi người dùng xác nhận → ảnh hưởng schedule của program đã tồn tại (dispatch đọc `scope_rule`). Draft bị bỏ lại hiển thị trong Portfolio ("draft") và tab Scans mãi mãi, không có nút xoá. `read()` trong `api/brief.py` gọi `snapshot()` yêu cầu scan hoàn tất ⇒ tab **Brief/Program báo lỗi cho tới khi có scan đầu tiên xong**, không sửa được PROGRAM.md trước khi scan.
**Hướng sửa:** giữ two-phase (§22.1) nhưng: scope snapshot nằm trong `scan_run.stats_json` (đã có) và chỉ ghi `scope_rule` ở **launch**; `DELETE /api/scans/{id}` cho draft + tự dọn draft >7 ngày; ẩn program chỉ-có-draft khỏi Portfolio (hiện mục "Bản nháp"); sinh `PROGRAM.md` ở resolve (an toàn: file bền, không ghi đè).

**F7.** Review chỉ hiển thị config kỹ thuật + scope. Không có policy, `warnings` (API trả nhưng UI không render), nguồn dữ liệu (`API` hay `public dump` — dump công khai có thể cũ, không có policy đầy đủ, đúng như P8_WINDOWS_BROWSER_RESULT ghi cho Live Nation), cũng không có xác nhận "program cho phép scan tự động".
**Hướng sửa:** panel **Policy & Automation** ở Review (mục 5.U4) + checkbox bắt buộc cho depth ≠ passive. Chỉ **cảnh báo** theo từ khoá, không tự quyết định thay người dùng.

**F8.** Health trong sandbox: `httpx:true`, nhưng log scan: `[!] WARNING: ProjectDiscovery httpx not found on PATH` (binary là CLI Python tại `/usr/local/bin/httpx`). Health chỉ dùng `shutil.which`. **Sửa:** kiểm `httpx -version` chứa "projectdiscovery" (tương tự nuclei/subfinder `-version`), và UI Review hiển thị tool thiếu **theo depth đã chọn** ("light cần httpx, nuclei; đang thiếu: nuclei → bước này sẽ bị bỏ qua").

**F9/F10.** Xem mã `App.tsx` (monitoring `detail.data.scans[0].depth`, toggle `enabled: !enabled` dùng chung nút với interval) và `generator.py` (TOP SURFACE chỉ Host/Rank/Status/Tech; không `reasons`; HƯỚNG TEST cố định).

### Kiểm tra mặt tốt (đã đúng, giữ nguyên)
`excluded_hosts` sai → 422 rõ ràng (PUT và launch); only-OUT → 422 `scope_empty`; scope chứa wildcard OUT/IN xử lý đúng; mobile/other không auto-recon; H1 resolve giữ wildcard + OUT + instruction từng asset; launch lại một scan đã chạy bị chặn bởi `output_claim` (đọc từ mã `recon_orch._claim_output`, chưa chạy thật).

---

## 3. UI/UX hiện tại — đánh giá có bằng chứng (screenshot desktop + mobile)

Tái hiện: `cd frontend && npm run build`, `SCR=/tmp/bbasm-mock python review_tools/mock_h1_server.py`, rồi `SCR=… PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python review_tools/ui_screenshots.py` (cần `pip install playwright==1.56.0`).

1. **Màn Review là một bảng điều khiển kỹ thuật thô**: nhãn `threads`, `rate_limit`, `skip_nmap`, `skip_active_crawl`, "Nuclei severity" nhập tay chuỗi `low,medium` (gõ sai → 422 sau khi bấm Launch). Không giải thích depth làm gì, chạy bao lâu, chạm target hay không. Đổi depth ghi đè thầm lặng nhiều field.
2. **Không có policy, warnings, nguồn dữ liệu, tool thiếu** ở Review (F7/F8).
3. **Excluded hosts** là textarea tự do trong khi đã có checkbox từng asset — hai cơ chế trùng nhau, dễ lệch.
4. **Checkbox `mobile` bị `disabled` không giải thích**; không thấy IN/OUT đếm tổng; OUT không có checkbox nên trông như "thiếu".
5. **Raw scope là một textarea với cú pháp ẩn `# OUT`** (F2/F3); lỗi trả về là `Invalid scope entry: …` không nêu dòng.
6. **H1: ô nhập trống không hướng dẫn** định dạng chấp nhận; lỗi `Expected h1:<handle>…` (F4).
7. **Trang Scan**: log là danh sách `type message` thô; không có thanh phase (backend đã gửi `phase` events), không ETA/timeout, sau `done` **không dẫn tới bước tiếp theo** (người dùng phải tự quay Portfolio → Target → Brief).
8. **Target page**: không có hành động chính ("Bắt đầu hunt": lệnh `cd … && claude`); "Copy target path" nằm sâu trong tab Brief và **gọi POST regenerate brief** chỉ để lấy path; Export ZIP ở header nhưng checkbox "Include raw recon" đứng ngoài ngữ cảnh.
9. **Tab không nằm trong URL** → F5/refresh/back mất tab; lỗi 422 "No completed scan available" hiện như lỗi cho Brief/Program khi chưa có scan (F6).
10. **Diff/Findings** hiện `JSON.stringify(detail)` trong `<pre>`; không nhóm NEW/CHANGED/GONE, không phân trang (44 835 px), không lọc severity/type.
11. **Surface/Assets** cùng một bảng, không lọc/tìm kiếm/sắp xếp, không hiển thị category (cidr/wildcard…), rank chỉ là số; "Lý do" là key kỹ thuật (`nuclei_medium_plus`).
12. **Portfolio**: số "255 NEW" gây hiểu nhầm (F5); không có "cần chú ý" (scan lỗi, chưa review, monitoring tắt); program chỉ-draft vẫn hiện.
13. **Monitoring**: một nút "Enable/Disable monitoring" + select interval; không hiển thị depth/config sẽ dùng, `Next: —` khi chưa bật.
14. **Ngôn ngữ trộn** Anh/Việt ("Resolve & review", "Scope đã resolve", "Mất kết nối — đang thử lại"); lỗi dùng text server thô.
15. **Kiến trúc frontend**: toàn bộ 783 dòng ở một `App.tsx` (spec §5 dự kiến `pages/ components/ api/`, hiện chỉ là `.gitkeep`); trạng thái dùng `any`; khó test từng màn hình (11 test hiện chỉ bao phủ vài luồng).
16. Mobile 390px: layout xếp dọc đúng, không vỡ ngang (tốt), nhưng Review dài ~2000px, nút Launch ở cuối, bảng Surface cuộn ngang.

---

## 4. Danh sách mục CHƯA chạy / cần môi trường người dùng (không đánh dấu hoàn tất)

- Docker build/compose, `test_docker_integration` — **SKIP** (không có Docker daemon trong sandbox).
- Recon integration thật + browser E2E với recon đầy đủ — cần host có subfinder/httpx(PD)/nuclei/katana/gau/amass/ffuf/nmap.
- Windows/WSL2 Docker Desktop (đã có kết quả Windows từ P8_WINDOWS_BROWSER_RESULT, tôi không tái kiểm).
- H1 thật: cần program **cho phép automation** + (tuỳ chọn) `H1_USER/H1_TOKEN`. Không dùng Live Nation. Review này chỉ kiểm H1 bằng API **mock** (cấu trúc theo test hiện có) — không chứng minh hành vi API H1 thật.
- Tick scheduler thực tế, monitor fixture có finding, cancel nuclei thật trên sandbox này — dựa vào bằng chứng Kali đã có.
- Reconnect WS giữa scan dài và phone thật — chỉ kiểm viewport 390px bằng Chromium.
- CI remote cho commit mới nhất — chưa kiểm (không có quyền chạy Actions ở đây).

**P8 vẫn chưa đóng.** Không đề xuất merge main cho tới khi (a) F1, F2 sửa (an toàn/đúng dữ liệu) và (b) các mục trên có bằng chứng.

---

## 5. KẾ HOẠCH PHIÊN BẢN MỚI — v1.1 "Guided UX"

### 5.0 Nguyên tắc (xếp theo ưu tiên của người dùng)
1. **Dễ dùng nhất có thể**: một đường chính "Thêm program → Xem lại → Chạy → Hunt"; mọi thứ khác nằm sau "Nâng cao".
2. **An toàn không phụ thuộc người dùng nhớ cú pháp**: ô IN/OUT tách riêng, preview từng dòng, không đoán khi mơ hồ.
3. **Policy/instruction H1 luôn thấy trước khi Launch** và đi vào `PROGRAM.md`; người dùng có thể dán policy tay khi nguồn công khai không đủ.
4. **Không đổi kiến trúc §1, non-goals §19, two-phase §22.1, schema §6 (chỉ thêm cột/endpoint nhỏ có migration)**.
5. **Kiểm chứng được trong cloud**: mọi thay đổi có unit/Vitest/Playwright chạy với mock H1 (`review_tools/mock_h1_server.py`), không cần tool recon.

### 5.1 Quyết định thiết kế (mặc định của tôi — đổi nếu bạn muốn)
| # | Quyết định | Lý do |
|---|---|---|
| D1 | Giữ React + Vite + hash router, **không thêm framework UI**; thêm `@testing-library/react` (dev) | rủi ro thấp, build/test nhanh trong cloud |
| D2 | **Tab và bước nằm trong URL**: `#/program/:slug/:tab`, `#/new`, `#/scan/:id/review|run` | refresh/back/chia sẻ link đúng chỗ |
| D3 | **Preset thay cho field kỹ thuật**: Passive / **Light (khuyến nghị)** / Strong; field thô nằm trong "Nâng cao" | phần lớn người dùng không cần chỉnh |
| D4 | UI **tiếng Việt thống nhất**, thuật ngữ kỹ thuật giữ tiếng Anh; chuỗi gom `frontend/src/strings.ts` | hết trộn ngôn ngữ, dễ sửa |
| D5 | Review có **cổng xác nhận**: depth ≠ passive cần tick "Tôi đã đọc policy và program cho phép scan tự động"; Strong cần thêm xác nhận | an toàn; chỉ cảnh báo, không tự quyết |
| D6 | Raw scope: **hai ô IN / OUT** + bảng preview từng dòng | loại bỏ F2/F3 tận gốc |
| D7 | CIDR/IP là **range asset**, không bung 254 dòng | F5 |
| D8 | Không thêm auth/multi-user, không spawn agent, không BC/IT/YWH/IMF | non-goals |

### 5.2 Các pha triển khai (mỗi pha có cổng test; làm tuần tự, commit nhỏ)

**U0 — Sửa lỗi dữ liệu/an toàn backend (chặn F1, F2, F8; nền cho UI)** · ~1 ngày
- `jobs/h1_scope.py`: thêm `policy_text`, `policy_source` (`api|public_dump|none`), `fetched_at`, `warnings` rõ ("Nguồn công khai, có thể cũ, không có policy đầy đủ").
- `brief/generator.py`: đọc `policy_text` (fallback `program.policy`); render policy vào `PROGRAM.md` kèm nguồn + thời điểm; thêm mục `## Quy định automation (do người dùng xác nhận)`.
- `jobs/scope_resolver.py`: `raw_entries` hardening (F2: header lạ → 422; `#` comment được báo "đã bỏ qua"), tách token, bỏ bullet/comment cuối dòng, range, `https://*.x`, CIDR non-strict → gợi ý chuẩn hoá hoặc lỗi rõ; `h1_handle` theo F4; URL scope (có path) giữ nguyên là web-url **và** ghi cảnh báo "recon sẽ chạy trên cả host".
- Mới `POST /api/scope/preview` (không ghi DB/không audit scope): `{input, scope_in[], scope_out[]}` → `{lines:[{raw,status,category,normalized,note}], handle?, summary:{in,out,errors,warnings}}`. `ResolveRequest` thêm `scope_out?: list[str]` (tương thích ngược với `# OUT`).
- `api/health.py`: kiểm chữ ký `-version` cho httpx/nuclei/subfinder/katana…; thêm `tools_by_depth`.
- **Test (mới)**: TC-SR-7 `#OUT` → 422; TC-SR-8 `a.com, b.com` tách đúng; TC-SR-9 range; TC-SR-10 handle URL có query/www/no-scheme; TC-PRG-4 H1 policy xuất hiện trong `PROGRAM.md` (dùng đúng shape provider); TC-HLT-2 httpx Python ≠ PD; preview không ghi DB.
- **Done khi**: `pytest -m "not integration"` ≥ 197 + mới, tất cả xanh; fuzz 25+14 ca ở mục 2 cho kết quả mong đợi.

**U1 — Draft & range asset & brief (F5, F6, F10)** · ~1 ngày
- Migration nhỏ (`schema_meta` version+1): `scan_run.draft_expires_at`? (hoặc dùng `started_at IS NULL AND status='draft'` + tuổi); `asset.kind` hoặc `asset.host_count` cho range.
- Resolve không ghi `scope_rule`/`.scope` cho program đã tồn tại tới khi **launch** (snapshot đã ở `stats_json`); `DELETE /api/scans/{id}` (chỉ draft); dọn draft >7 ngày lúc boot; `GET /api/programs` thêm `?include_drafts=false` mặc định.
- Sinh `PROGRAM.md` + `.scope` preview ở resolve; `GET /brief|program` trả khung hợp lệ + `available:false` thay vì 422 khi chưa có scan.
- Ingest: CIDR/IP → 1 range asset; IP con chỉ khi quan sát; rank "fresh" cần tín hiệu thật.
- Brief: thêm `reasons` (ngắn), instruction asset (cắt 120 ký tự), "Bắt đầu" 3 dòng, ASSET MỚI ≤30 + tổng; vẫn <12 000 B; cập nhật `CLAUDE.md` template.
- Phân trang `diff/findings/assets` (đã có `limit/offset` ở assets/findings; thêm cho diff) + trả `total`.
- **Test**: TC-DF-5 phân trang; TC-BR-7 CIDR /24 → brief ≤ 12KB và ≤ 30 dòng mới; TC-LC-5 resolve lần 2 không đổi `scope_rule` đang dùng bởi schedule; TC-LC-6 xoá draft; TC-PRG-5 `PROGRAM.md` sửa được trước scan đầu.

**U2 — Nền tảng frontend** · ~1 ngày
- Tách `App.tsx` → `src/pages/{Portfolio,NewScan,Review,Run,Program}/`, `src/components/{Badge,Stepper,ScopeTable,PolicyPanel,PresetPicker,Pager,EmptyState,ErrorBox,CopyButton}`, `src/api/{client,types}.ts` (bỏ `any`), `strings.ts`, hook `useScan(id)` gộp WS + poll.
- Router hash có tab trong URL; `ErrorBox` map mã lỗi → câu tiếng Việt + gợi ý hành động.
- Thêm Testing Library; giữ 11 test cũ pass (có thể đổi selector, **không** đổi `aria-label` `Depth`/`Scan status`/`Launch scan`/`Resolve & review` trừ khi cập nhật luôn test browser).
- **Done khi**: `npm test` + `npm run build` + browser E2E hiện có vẫn xanh, không đổi hành vi.

**U3 — Màn "Thêm program" (guided input)** · ~1 ngày
- Hai tab: **HackerOne** | **Raw scope**.
- H1: một ô; dán URL/`h1:`/handle đều được; hiện ngay "Nhận diện: `acme` ✓" (dùng cùng chuẩn hoá F4, xác nhận bằng `preview`). Ghi chú nguồn: "Có H1_USER/H1_TOKEN → dùng API đầy đủ; không có → dữ liệu công khai (có thể cũ, không có policy đầy đủ)". Ô tuỳ chọn "Dán policy/hướng dẫn của program" (đi vào `PROGRAM.md`).
- Raw: **hai ô IN và OUT**, ví dụ mẫu bấm để điền, nút "Tải file .txt"; **bảng preview theo dòng** (✓/⚠/✗ + category + chuẩn hoá + lý do) cập nhật khi gõ (debounce 300ms, gọi `/api/scope/preview`); nút Tiếp tục tắt khi còn ✗, nêu rõ dòng nào. Ô "Tên program" (slug an toàn, gợi ý từ domain; thay `raw-<hash>` mờ).
- **Test**: Vitest cho từng trạng thái preview; Playwright (mock H1) "dán URL có `?type=team` → nhận diện đúng"; "gõ `#OUT` → bị chặn".

**U4 — Màn Review (trọng tâm UX + an toàn)** · ~1.5 ngày
Bố cục một cột dọc (mobile-first), 4 khối, nút **Launch** cố định cuối trang kèm lý do khi bị tắt:
1. **Tóm tắt "Sẽ làm gì"** (ngôn ngữ thường): preset đang chọn, công cụ sẽ chạy/bị bỏ (theo `tools_by_depth`), ước lượng thời gian (theo timeout), có chạm target hay không.
2. **Policy & Automation**: nguồn (API/public/paste) + thời điểm; policy rút gọn mở rộng được; **chip cảnh báo từ khoá** (`scanner`, `automated`, `bot`, `AI/LLM`, `rate limit`, `DoS`…) mang tính tham khảo; instruction theo từng asset; checkbox xác nhận (D5).
3. **Scope**: nhóm theo category, đếm IN/OUT, từng entry có công tắc; OUT hiển thị rõ "luôn bị loại"; CIDR hiện số host; mobile/other ghi "làm tay — sẽ vào PROGRAM.md" (không còn checkbox bị khoá khó hiểu); bỏ textarea Excluded hosts khỏi đường chính (còn trong Nâng cao).
4. **Preset + Nâng cao**: 3 thẻ preset (Passive/Light★/Strong, có mô tả + cảnh báo Strong ngay trên thẻ); "Nâng cao" gập: threads/rate/timeout/nuclei severity (select đa chọn thay vì gõ chuỗi)/toggles, nhãn tiếng Việt kèm giải thích; hiển thị giá trị được preset đặt và nút "Đặt lại theo preset".
- Hiển thị `warnings` từ resolve; tool thiếu cho depth đã chọn.
- **Test**: Vitest cổng xác nhận (không tick → Launch disabled + lý do); chọn preset đổi đúng config; Playwright mock H1 resolve → thấy policy → tick → launch passive.

**U5 — Màn Run (tiến độ → bước tiếp theo)** · ~0.5–1 ngày
- Stepper từ `phase` events (subdomain_enum, live_probe, port_scan, url_collect, js_analysis, dir_fuzz, config_expose…) + đồng hồ + timeout còn lại; trạng thái kết nối WS tách biệt trạng thái scan (đã poll REST); log gập, lọc `warning`; nút Huỷ có xác nhận.
- Khi `done|done_partial`: card **"Hoàn tất → Bắt đầu hunt"** (lệnh `cd "…" && claude` + Copy + nút Mở program); `failed|cancelled`: nguyên nhân (`error`) + "Chạy lại với cùng cấu hình".
- **Test**: Vitest phase→stepper; E2E giữ `role=status name="Scan status"`.

**U6 — Màn Program (trang làm việc hằng ngày)** · ~1.5 ngày
- Header: tên, nguồn, trạng thái scan cuối, **CTA chính "Bắt đầu hunt" (copy lệnh)**, Export ZIP (checkbox gộp vào menu), "Scan lại".
- Overview: thẻ "Top 5 surface", "Thay đổi từ scan trước (NEW/CHANGED/GONE)", "Findings theo severity", Monitoring (hiển thị depth/interval/config sẽ dùng, toggle bật/tắt tách khỏi chọn interval — F9, bắt buộc xác nhận như D5 khi bật).
- Surface (top-N, hiển thị lý do bằng nhãn đọc được + tooltip) / Assets (tìm, lọc category/state/rank, sắp xếp, phân trang) tách rõ mục đích.
- Diff: nhóm NEW/CHANGED/GONE, render `before→after` thay vì JSON; Findings: bảng có lọc severity/type.
- Brief: preview + kích thước/12KB + "Tạo lại"; Program: soạn phần user-editable với cảnh báo chưa lưu.
- Tất cả list có empty/loading/error state có hành động gợi ý.
- **Test**: Vitest từng tab; Playwright "scan → Program → tab trong URL giữ khi refresh".

**U7 — Portfolio & điều hướng** · ~0.5 ngày
- Thẻ program: trạng thái, NEW thật (không tính range), "cần chú ý" (scan lỗi/draft chờ review/monitoring tắt), mục "Bản nháp" riêng (xoá được); nút "Thêm program" nổi bật; onboarding khi trống (3 bước + tool health tóm tắt).

**U8 — Nghiệm thu & tài liệu** · ~1 ngày
- Cloud (không cần tool): pytest, Vitest, `npm run build`, Playwright (mock H1 + raw localhost passive) với **ảnh chụp 1366 và 390**; checklist TC-UX-* bên dưới; cập nhật README/REVIEW_GUIDE/ACCEPTANCE/NOTES + CHANGELOG spec **v2.5** (ghi U0–U7).
- Host người dùng (không làm được ở cloud): Docker, recon thật, H1 program được phép, Windows/WSL2.

Tổng ước lượng ~8–9 ngày công. Thứ tự giá trị/rủi ro: **U0 → U1 → U4 → U3 → U5 → U6 → U2/U7** nếu cần cắt phạm vi (nhưng U2 nên đi trước U3–U7 để khỏi sửa hai lần; có thể làm U2 song song U0/U1).

### 5.3 Tiêu chí nghiệm thu UX (TC-UX-*)
- **TC-UX-1** Người mới: từ Portfolio trống → có `AGENT_BRIEF.md` bằng raw `127.0.0.1` passive **≤ 5 click, không đọc tài liệu**.
- **TC-UX-2** Dán `https://hackerone.com/acme?type=team` → nhận `acme`; dán `acme` trần → nhận `acme`.
- **TC-UX-3** Gõ `#OUT`/`OUT:` hoặc dòng không hiểu → bị chặn tại preview, nêu số dòng + lý do; **không** có đường nào host OUT thành IN.
- **TC-UX-4** H1 mock có policy → policy thấy ở Review và có trong `PROGRAM.md`; depth ≠ passive không launch được khi chưa tick xác nhận.
- **TC-UX-5** CIDR /24 → Review hiện "256 địa chỉ" 1 dòng; brief ≤ 12KB, ASSET MỚI ≤ 30 dòng + tổng.
- **TC-UX-6** Refresh ở bất kỳ tab Program nào giữ nguyên tab; Back hoạt động.
- **TC-UX-7** Scan xong → không cần điều hướng tay để lấy lệnh `cd … && claude`.
- **TC-UX-8** Viewport 390px: không cuộn ngang trang; Launch và CTA luôn truy cập được; tương phản ≥ AA ở dark và light.
- **TC-UX-9** Mọi lỗi API hiển thị câu tiếng Việt + gợi ý; không hiển thị `HTTP 500`/JSON thô.
- **TC-UX-10** Diff/Findings ≥ 1000 dòng vẫn mượt (phân trang), trang không cao > 3 màn hình.

### 5.4 Rủi ro & cách giảm
- *Đổi `aria-label`/nhãn làm gãy `test_browser_integration`* → giữ 4 nhãn khoá (Depth, Scan status, Launch scan, Resolve & review) hoặc cập nhật test trong cùng commit.
- *Preview và Resolve phân loại khác nhau* → một hàm `classify` dùng chung; test property "preview ok ⇒ resolve ok".
- *Cảnh báo từ khoá policy gây tin sai* → ghi rõ "tham khảo", không chặn cứng ngoài cổng xác nhận của người dùng.
- *Mock H1 ≠ H1 thật* → bắt buộc một lần nghiệm thu với program được phép (mục 4) trước khi đóng P8.
- *Migration schema* → bump `schema_meta`, test nâng cấp DB cũ (file DB P8) lên mới.

### 5.5 Handoff cho Codex (khi người dùng duyệt kế hoạch)
Thứ tự: U0 → U2 → U1 → U4 → U3 → U5 → U6 → U7 → U8. Mỗi pha: nhánh `build/v11-uN-*` chồng lên `build/p8-acceptance`, commit nhỏ, chạy `python -m pytest -m "not integration"` + `npm test && npm run build` trước mỗi push, và (U3 trở đi) chạy Playwright với `review_tools/mock_h1_server.py`. Không merge main; không scan target thật.

---

## 6. Phụ lục: file thêm trong lần review này
- `review_tools/mock_h1_server.py` — app thật + uvicorn thật + H1 provider mock (không internet), cổng 18766.
- `review_tools/ui_screenshots.py` — chụp mọi trang desktop/mobile (Playwright 1.56.0).
- `CLOUD_REVIEW_RESULTS.md` — file này.
Không sửa code sản phẩm. Không tạo `.env`.
