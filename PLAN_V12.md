# PLAN v1.2 — An toàn tốc độ, độ tin cậy dữ liệu, giá trị recon và khả năng tuỳ chỉnh

Ngày 2026-10-14 · Soạn bởi Claude (cloud) sau khi đọc `V11_HOST_RESULTS.md`, `V11_FOLLOWUP_NOTES.md`, `V11_PRODUCT_REVIEW.md` của Codex.
Nhánh làm việc: `claude/upbeat-thompson-b7bb23` (đã fast-forward tới `caf55d0`). **Tài liệu này chỉ là kế hoạch — chưa có code nào được viết. Chờ bạn duyệt (mục 8).**
Không đổi §1 kiến trúc và non-goals v1 (không spawn agent, không multi-user, không BC/IT/YWH/IMF).

---

## 1. Kết quả Codex và cách chúng ánh xạ vào kế hoạch

QA trên Docker (Windows host): 22 PASS · 3 FAIL · 1 SKIP, cộng các thử nghiệm active thủ công trên `vuihoc.vn`. Phần lõi chạy được (resolve/preview/launch/cancel/export/persist/scheduler tick/secret-free log). Lỗi và thiếu sót:

| ID | Phát hiện (nguồn) | Mức | Xử lý ở |
|---|---|---|---|
| **R1** | `katana -c 50 -p 20` bị hard-code **sau** các tham số của BBASM nên ghi đè; JS downloader/secrets monitor gọi `curl` không giới hạn; scan #10/#11 phải huỷ | **P1** | V3 |
| **R2** | H1 không token → `public_dump`: scope chưa xác minh, không có policy; UI chưa nói rõ "CHƯA XÁC MINH" xuyên suốt Review → Program → Brief | **P1** | V4 |
| **R3** | Passive thu 8.836 URL nhưng UI/Brief chỉ cho thấy 1 host + số đếm; không có phễu raw/hợp lệ/ngoài scope | **P1** | V5 |
| **F1** | Lệnh hunt trên Windows: `C:\\Users\\…` (json.dumps nhân đôi `\`); test unit FAIL trên Windows | **P1** | V0 |
| **R4** | Diff Passive→Light báo 0 thay đổi dù status null→200 | P2 | V6 (điều tra) |
| **R5** | ZIP `include_recon=true` chứa dữ liệu thô ngoài scope (223 dòng thuộc 3 host ngoài) không nhãn | P2 | V7 |
| **F2** | Review trên 390px dài 3.408px; nút Launch ở cuối | P2 | V8 |
| **R6** | Brief cắt giữa chuỗi JSON ở cột Tech | P2 | V7 |
| **R7** | Native Windows backend: runner từ chối recon (đúng thiết kế) nhưng UI để scan chờ 6 phút rồi "lỗi" | P2 | V0 |
| **R8** | CI không chạy cho commit (`ci.yml` chỉ lọc `main`, `build/**`; nhánh `claude/**`, `test/**` bị bỏ qua) | P2 | V0 |
| **F3** | `test_recon_integration` giả định vendor ở `/app/vendor` và có race `psutil.NoSuchProcess` | P3 | V0 |
| **R9** | 7 tab Program, Overview lẫn lộn, Run chưa phân biệt chạy/bỏ qua/lỗi, thuật ngữ trộn Anh–Việt | P2 | V8 |
| **U1** | **Yêu cầu mới:** mọi chức năng phải tuỳ chỉnh được (ngoài default/preset) | — | mục 4, V2/V8 |

Đã tự kiểm thêm trong cloud (không cần target):
- `recon_engine.sh` đã có chỗ cắm `BBASM_KATANA_ARGS`, `BBASM_NUCLEI_ARGS`, `BBASM_NMAP_ARGS` nhưng chúng đứng **trước** `-c 50 -p 20` nên không ghi đè được → phải chặn ở tầng ngoài (V3).
- Chạy chuỗi giả lập Passive→Light bằng chính `DiffEngine` + `Ingester`: ra `changed=1` đúng. Vậy engine đúng ở ca sạch; R4 nhiều khả năng do kịch bản (scan huỷ xen giữa/baseline) → cần dữ liệu thật để tái hiện (V6 bước 1).

### Ma trận tuân thủ rate limit hiện tại (đọc từ `recon_engine.sh`, `secrets_hunter.sh`, `takeover_scanner.sh`)

| Công cụ | Chạm target? | Giới hạn người dùng áp được? | Bằng chứng |
|---|---|---|---|
| httpx | có | **Có** (`-threads`, `-rate-limit`) | recon_engine.sh:376-377 |
| ffuf | có (strong) | **Có** (`-t`, `-rate`) | :550-551 |
| nuclei | có | **Có** (`-rl`, `-c`) | :692-702 |
| katana | có | **Không** (`-c 50 -p 20` cứng) | :446-450 |
| curl tải JS | có | **Không** | :491, :502; secrets_hunter.sh:113 |
| curl dò file cấu hình | có | **Không** | :597 |
| subjack (takeover) | có | **Không** (`-t 20`) | takeover_scanner.sh:60 |
| nmap (strong) | có | **Không** (`-T4`, không `--max-rate`) | :418 |
| subfinder/amass/gau/crt.sh/wayback | không (nguồn thứ ba) | n/a (nhưng cần hiển thị "không chạm target") | |

---

## 2. Nguyên tắc thiết kế

1. **An toàn trước tiện lợi:** không hứa giới hạn toàn scan nếu bước nào không tuân được; bước không bảo đảm được thì **tự tắt và nói rõ** hoặc chặn Launch.
2. **Ba tầng điều khiển:** *Preset có sẵn* → *Profile của bạn (lưu, đặt tên)* → *Tuỳ chỉnh cho lần quét này*. Mọi giá trị đều thấy được, đặt lại được ("Đặt lại về preset"), và UI luôn hiển thị **khác preset ở đâu**.
3. **Có cấu trúc, không tự do:** người dùng chỉnh bằng trường có kiểu/khoảng/allowlist. **Không** nhận cờ CLI thô, đường dẫn template, biến môi trường hay lệnh shell. Server validate lại toàn bộ (UI không phải biên an toàn).
4. **Trần cứng vẫn là của hệ thống:** threads ≤200, rate ≤500, timeout ≤ trần theo depth, số URL/JS có trần. Người dùng hạ được, không nâng quá trần (trần đổi qua `.env`, không qua UI).
5. **Quy tắc theo program thắng profile:** nếu bạn ghi "program này tối đa 5 req/s" hoặc "cấm scanner", mọi profile bị kẹp/chặn theo đó.
6. **Trung thực dữ liệu:** mỗi mục dữ liệu có nhãn nguồn + mức xác minh (`historical` / `observed` / `live` / `finding`); URL lịch sử không bao giờ gắn "live".
7. **Không phụ thuộc vendor để vá:** submodule do repo khác sở hữu và phiên cloud không có quyền push vào đó → mọi enforcement làm ở `advance_asm` (shim PATH, lọc ingest). Vá upstream là việc tuỳ chọn của bạn sau này.

---

## 3. Chi tiết các hạng mục sửa lỗi / tính năng nền

### 3.1 V0 — Sửa nhanh & hạ tầng test (≈0,5 ngày)
- **F1:** `Settings.hunt_target` quote theo shell đích: POSIX → `"…"` thoát `\ " $ \``; Windows path (`^[A-Za-z]:\` hoặc `\\`) → `"C:\Users\x"` giữ nguyên `\`. Thêm test cho cả hai + chọn `shell` (posix|powershell|cmd) làm tuỳ chọn người dùng (mặc định tự đoán từ đường dẫn).
- **R7:** `/api/health` thêm `runtime: {os, recon_supported, reason}`. Native Windows/macOS: UI hiện banner "Máy chủ này không chạy được recon thật — dùng Docker/WSL2" và **khoá Light/Strong** (Passive cũng cần process group → khoá luôn nếu runner không hỗ trợ); `Launch` trả 422 sớm thay vì để scan chờ rồi lỗi.
- **R8:** `ci.yml` thêm `claude/**`, `test/**` vào `push.branches`; thêm job chạy `test_ui_e2e_mock_h1.py` (Chromium trên ubuntu-latest, tuỳ chọn `continue-on-error: false`).
- **F3:** `test_recon_integration` lấy tool path từ `Settings.tool_path()`; `dead()` coi `psutil.NoSuchProcess` là đã chết.
- **Done:** `pytest -m "not integration"` xanh trên Windows + Linux (Codex xác nhận); CI chạy được trên nhánh làm việc.

### 3.2 V1 — Khung migration DB (≈1 ngày) — *điều kiện cho mọi thay đổi schema*
Hiện `Database.migrate()` **từ chối** mọi version ≠ 1. Cần:
- `SCHEMA_VERSION = 2`; bảng `schema_meta` giữ version; danh sách migration tuần tự `001→002…` mỗi bước một transaction; **backup tự động** `bbasm.db.bak-v1-<ts>` trước khi nâng; từ chối hạ cấp.
- Schema v2 (thêm, không xoá): bảng `profile`, bảng `program_rules`, bảng `wordlist`; cột `url.tags_json`, `url.score`, `url.verification`, `url.status_code`; cột `scan_config.options_json`; cột `scan_run.baseline_scan_id`; `schedule.window_json`.
- **Test:** nâng cấp từ DB P8 thật (fixture sinh từ schema v1 + dữ liệu mẫu, và file DB do Codex/bạn cung cấp); mất điện giữa chừng không để DB nửa vời; chạy 2 lần idempotent.

### 3.3 V3 — Giới hạn tốc độ toàn pipeline (≈2 ngày) — *P1*
Cơ chế: thư mục **shim** do BBASM sinh mỗi scan, đặt **đầu PATH** của mọi tiến trình recon; shim chuyển tiếp tới binary thật sau khi áp giới hạn.
- `katana` shim: bỏ mọi `-c/-concurrency/-p/-parallelism/-rl/-rate-limit/-rld` do script cấp, thêm giá trị theo cấu hình (và `-d` tối đa theo tuỳ chọn người dùng); ghi `argv` cuối vào `audit.jsonl` để kiểm chứng.
- `curl` shim: chỉ **giới hạn khi URL thuộc host trong scope** (đọc `BBASM_SCOPE_HOSTS_FILE`); dùng token-bucket chia sẻ giữa các tiến trình bằng `flock` trên file trạng thái của scan; request tới crt.sh/archive/… không bị làm chậm.
- `nmap` shim: thêm `--max-rate`, `--max-parallelism` từ cấu hình; `subjack`/`ffuf`/`httpx`/`nuclei`: bảo đảm cờ `-t/-rate` không bị vượt (shim kẹp về ≤ cấu hình).
- **Bảng "áp dụng theo công cụ"** do backend trả (`enforcement: native|shim|none`) và UI hiển thị ở Review. Công cụ `none` mà người dùng đặt rate thấp → **bước đó tự tắt** + giải thích; không có chế độ "âm thầm bỏ qua giới hạn".
- Tuỳ chỉnh: rate/threads **toàn cục** + **override theo công cụ** (chỉ được ≤ toàn cục); `request_delay_ms` tối thiểu giữa 2 request; tắt riêng từng monitor (JS downloader, takeover).
- **Kiểm chứng (bắt buộc đo, không suy luận):**
  - Cloud: unit test shim (viết lại argv, token-bucket đúng tốc độ với binary giả, `flock` nhiều tiến trình, chỉ throttle host trong scope).
  - Host (Codex): HTTP fixture trên `127.0.0.1` đếm request/giây với `rate_limit=1` cho **từng** công cụ thật (katana, curl JS, httpx, ffuf, nuclei, subjack) trong Docker; cancel giữa monitor; kết quả ≤ giới hạn + dung sai.
- **Done:** scan Light trên fixture với `rate=1` có tốc độ đo được ≤ ~1 req/s ở mọi bước chạm target; test cancel xong không còn tiến trình.

### 3.4 V4 — Độ tin cậy scope/policy H1 (≈1 ngày) — *P1*
- Trạng thái xác minh lưu theo program/scan: `scope_verification = api_verified | public_unverified | manual | raw`; `policy_verification = official_api | user_pasted | missing`; `fetched_at`; danh sách "thiếu".
- Review/Program/Brief/`PROGRAM.md` hiện **nhãn cố định** (vd "SCOPE CHƯA XÁC MINH — dữ liệu công khai, đối chiếu tại <URL program>"), kèm checklist 3 bước đối chiếu và liên kết chính thức.
- **Quy tắc cổng:** `public_unverified` + depth ≠ passive → cần thêm xác nhận riêng "Tôi đã tự đối chiếu scope và policy trên HackerOne" (tách khỏi xác nhận automation).
- Người dùng có thể **đánh dấu đã xác minh** từng asset (ghi vào `scope_rule.verified_by_user`), dán policy, hoặc nhập scope tay bổ sung.
- **Test:** public dump thiếu policy; API trả policy + structured scope; chuyển nguồn; brief/PROGRAM.md mang nhãn.

### 3.5 V5 — URL inventory có giá trị hành động (≈2 ngày) — *P1*
- **Ingest:** đếm **phễu** `raw → trong scope → ngoài scope → trùng`, lưu vào `stats.url_funnel` (+ top host ngoài scope, chỉ đếm, không lưu nội dung); phân loại mỗi URL bằng hàm thuần `classify_url`: tags `api, graphql, auth, admin, upload, redirect-param, id-param, js, config/backup (.env,.git,.bak,.sql), docs, static`, có tham số, đuôi file; `score` 0–10 và `verification=historical|observed|live` (URL từ gau/wayback luôn `historical`).
- **API:** `GET /api/programs/{slug}/urls` lọc `q, host, tag, source, verification, has_params, ext, min_score`, phân trang + `X-Total-Count`, sắp theo score; `GET …/urls/summary` (phễu + đếm theo tag).
- **UI:** tab **Dữ liệu** gộp Assets + URLs + Surface (3 chế độ xem, một bộ lọc); chip tag; nhãn "lịch sử — chưa kiểm chứng".
- **Brief:** mục "ENDPOINT ĐÁNG XEM" tối đa N (người dùng chỉnh) kèm lý do + đường dẫn artifact; vẫn <12.000 byte.
- **Tuỳ chỉnh:** loại bỏ extension tĩnh, **path-exclusion** (vd H1 ghi "Do not test /internal": pattern `/internal/*` lọc khỏi inventory/brief và truyền cho katana `-cos`), tag quan tâm, N hiển thị.
- **Test:** fixture 10k URL gồm host ngoài scope; phễu khớp artifact; không URL lịch sử nào thành finding/live; hiệu năng phân trang.

### 3.6 V6 — Diff đáng tin & báo cáo scan trung thực (≈1 ngày)
1. **Tái hiện R4** với dữ liệu thật: yêu cầu Codex/bạn cung cấp `scan_run` + lịch sử `asset` của scan #9–#12 (đã bỏ nhạy cảm). Thêm test chuỗi: Passive → (Light bị huỷ ở katana) → (Light bị huỷ ở monitor) → Light hoàn tất, và chuỗi có scan `done_partial` xen giữa.
2. Lưu `scan_run.baseline_scan_id`; baseline là **scan hoàn tất gần nhất cùng program** (không phải trạng thái asset mutable); API/UI hiển thị "so với scan #N". Nếu bỏ qua một so sánh vì partial/cancel thì nói rõ lý do.
3. **Báo cáo từng pha** (chạy/bỏ qua/lỗi/không có dữ liệu + số kết quả sau lọc scope + giới hạn thực áp) lưu trong `stats.phases`; trang Run và Program hiển thị; Brief ghi đúng "0 findings ≠ an toàn" và danh sách bước bị bỏ.
- **Done:** chuỗi test ở bước 1 xanh; một scan Light bỏ katana/nuclei hiển thị rõ các bước đó "bị bỏ" trong UI và brief.

### 3.7 V7 — Brief & Export tuỳ chỉnh (≈1 ngày)
- Brief: render `tech` thành tối đa 3 nhãn + `+N` (hết cắt giữa JSON); người dùng chọn **ngân sách** (4/8/12 KB — không vượt 12), số asset/URL/finding hiển thị, bật/tắt từng mục, thứ tự ưu tiên tag.
- Export: 3 chế độ — **Chỉ brief**, **Đã lọc scope** (recon chỉ gồm dòng trong scope; ghi tóm tắt phần bị loại), **Thô** (có nhãn cảnh báo ngay trong ZIP + `MANIFEST.json.raw_includes_out_of_scope=true`). Mặc định: *Đã lọc scope*.
- **Test:** ZIP đã lọc không chứa host ngoài scope (kiểm bằng dữ liệu #9 mô phỏng); manifest ghi đúng chế độ.

---

## 4. KIẾN TRÚC TUỲ CHỈNH NGƯỜI DÙNG (trọng tâm yêu cầu mới)

### 4.1 Các tầng cấu hình
```
Preset dựng sẵn (Passive/Light/Strong — chỉ đọc)
   └─► Profile của người dùng (CRUD; tạo từ preset: "based_on")
          └─► Mặc định theo program (tuỳ chọn)
                 └─► Tuỳ chỉnh cho lần quét này (draft)  ──► ScanConfig v2 (đóng băng lúc Launch)
Quy tắc theo program (rate tối đa, cấm automation, …) KẸP/CHẶN mọi tầng ở trên
Trần hệ thống (.env) KẸP tất cả
```
Scan lưu **bản chụp config đầy đủ** (không tham chiếu profile) nên sửa profile sau đó không làm đổi lịch sử/diff. Lịch giám sát lưu tham chiếu profile **hoặc** bản chụp (người dùng chọn).

### 4.2 `ScanConfig v2` — các trường người dùng điều chỉnh
Giá trị mặc định theo preset (P = Passive, L = Light, S = Strong). Mọi trường đều có khoảng/allowlist; ngoài khoảng → 422 nêu rõ.

| Nhóm | Trường | Kiểu / khoảng | P | L | S |
|---|---|---|---|---|---|
| Tốc độ & an toàn | `threads` | 1–200 (≤ rules) | 50 | 50 | 50 |
| | `rate_limit` (req/s toàn cục) | 1–500 (≤ rules) | 150 | 150 | 150 |
| | `rate_per_tool{tool}` | ≤ toàn cục | — | — | — |
| | `request_delay_ms` | 0–10000 | 0 | 0 | 0 |
| | `scan_timeout` | ≤ trần depth | 300 | 900 | 2700 |
| | `jitter` (ngẫu nhiên hoá nhịp) | bật/tắt | tắt | tắt | tắt |
| Pha chạy (bật/tắt từng pha) | `phases.{subdomain_enum, live_probe, port_scan, url_collect, crawl, js_analysis, dir_fuzz, config_expose, param_discover, nuclei, takeover, secrets_monitor}` | bool | theo preset | theo preset | theo preset |
| Nguồn lịch sử (không chạm target) | `historical.{gau, wayback, crtsh}` + `historical_timeout` | bool; 1–300 s | bật | bật | bật |
| Crawl | `crawl.depth` 1–5, `crawl.max_hosts` 1–200, `crawl.js_parse` | — | — | 2/20 | 3/50 |
| JS monitor | `js.max_files` 0–100, `js.download` | — | — | 20 | 100 |
| Cổng (strong) | `ports.mode` top-100 / top-1000 / list; `ports.list` ≤100 cổng; `ports.connect_scan` | — | — | — | top-1000 |
| Fuzz thư mục | `ffuf.wordlist_id`, `ffuf.extensions` (≤10), `ffuf.max_hosts` | wordlist đã duyệt | — | — | built-in |
| Nuclei | `nuclei.severity` (set), `nuclei.tags` / `exclude_tags` (allowlist), `nuclei.timeout` | — | — | low,medium | low→critical |
| Nhận diện request | `identify.user_agent`, `identify.headers[]` (≤5, tên/giá trị validate; cấm `Authorization/Cookie`) | — | | | |
| Loại trừ đường dẫn | `exclude_paths[]` glob/regex an toàn (≤100) | — | | | |
| Đầu ra | `brief.budget_kb` 4–12; `brief.top_assets/top_urls/top_findings`; `brief.sections{…}`; `export.default_mode` | — | | | |

Quy ước: pha tắt ⇒ công cụ tương ứng không chạy; công cụ nằm ngoài ma trận enforcement (mục 1) bị khoá khi người dùng đặt rate thấp.

### 4.3 Quy tắc theo program (`program_rules`) — ràng buộc cứng
Người dùng ghi từ policy (có gợi ý trích từ policy, **người dùng bấm xác nhận mới áp**):
- `automation`: `unknown` (mặc định) | `allowed` | `forbidden` — `forbidden` ⇒ **chỉ Passive** (UI + server chặn Light/Strong và lịch giám sát khác Passive).
- `max_rate`, `max_threads` — kẹp mọi profile; Review hiển thị "đã kẹp từ 150 xuống 5 theo quy tắc program".
- `identify` bắt buộc (nhiều program yêu cầu header/UA riêng khi test) — tự gắn vào mọi request qua shim/tham số công cụ.
- `allowed_hours` (cửa sổ giờ được quét) — scan/giám sát ngoài cửa sổ bị hoãn/từ chối.
- `exclude_paths` mặc định, `notes` (vào `PROGRAM.md`).
- Chip gợi ý: policy chứa "5 req/s" → đề xuất `max_rate=5`; policy nhắc "scanner/automated/LLM" → hỏi `automation`.

### 4.4 Profile (preset của người dùng)
- API: `GET/POST/PUT/DELETE /api/profiles`, `POST /api/profiles/{id}/duplicate`; trường `name`, `description`, `based_on`, `config` (một phần — chỉ ghi phần khác preset), `built_in` (chỉ đọc).
- Gắn profile mặc định cho program; lịch giám sát chọn profile; xuất/nhập profile JSON (kiểm schema, không chạy gì).

### 4.5 Wordlist
- Built-in (nhỏ/vừa/lớn do BBASM cung cấp, có checksum); người dùng tải lên `.txt` ≤5 MB, ≤100k dòng, UTF-8, bỏ dòng chứa ký tự điều khiển; lưu `data/wordlists/<id>`; chỉ tham chiếu bằng id.

### 4.6 UX tuỳ chỉnh (không làm rối đường mặc định)
Review giữ đường chính: **chọn preset → xem tác động → xác nhận**. Có thêm:
- Thẻ thứ tư **"Tuỳ chỉnh…"** và danh sách "Profile của tôi" cạnh 3 preset.
- Mở "Tuỳ chỉnh" hiện 5 nhóm gập: **Tốc độ & an toàn · Pha & công cụ · Nguồn dữ liệu · Nhận diện & loại trừ · Đầu ra**. Mỗi trường: giá trị preset (mờ), giá trị hiện tại, nút ↺ đặt lại, lỗi inline, lý do khi bị kẹp.
- Thanh tóm tắt cố định: "Khác preset Light: 4 thay đổi" → bấm xem diff; nút **Lưu thành profile**.
- Bảng "Giới hạn áp dụng theo công cụ" (native/shim/không) cập nhật theo lựa chọn.
- Quy tắc program là một trang riêng trong Program → **Quy tắc & Policy**.
- Trên mobile: các nhóm là accordion; thanh hành động cố định (Launch + lý do khoá).

### 4.7 Không nằm trong phạm vi (cố ý)
Cờ CLI tự do, template nuclei tuỳ ý theo đường dẫn, biến môi trường tuỳ ý, thông tin xác thực/cookie phiên (bề mặt rủi ro cao; nếu cần sau này sẽ là một thiết kế riêng có mã hoá + cảnh báo).

---

## 5. UI/UX — tái cấu trúc thông tin (V8, ≈3 ngày)
- **Program:** 7 tab → 5 khu vực: **Tổng quan · Dữ liệu (Assets/URLs/Surface) · Phát hiện · Lịch sử (scan + Diff + trạng thái pha) · Scope & Hướng dẫn (IN/OUT, Quy tắc & Policy, Brief, Export, lệnh hunt, giám sát)**. Tab trong URL, có chỉ báo cuộn ngang trên mobile.
- **Tổng quan:** độ tin cậy scope/policy, 3 thay đổi quan trọng, 3 việc tiếp theo, liên kết chứng cứ; lệnh hunt thu gọn thành hành động phụ.
- **Review:** trang quyết định ngắn (nguồn & độ tin cậy · mức quét & tác động · IN/OUT · giới hạn request thực áp · xác nhận); chi tiết asset/tuỳ chọn nâng cao mở khi cần; gộp cảnh báo policy lặp; **thanh hành động cố định** trên mobile (khắc phục F2).
- **Run:** mỗi pha có trạng thái *chạy / bỏ qua (vì sao) / lỗi / không có dữ liệu*; hiện giới hạn thực áp; log thu gọn.
- **Brief:** xem raw + bản "đọc dễ" (bảng thu gọn trên mobile).
- Thuật ngữ tiếng Việt thống nhất (một file `strings.ts`): Portfolio→"Danh mục", Review→"Xem lại", Launch→"Bắt đầu quét"… (giữ `aria-label` cũ cần cho E2E hoặc cập nhật test cùng commit).
- Kiểm 320/390/1366px, bàn phím, tương phản AA, dữ liệu >1000 dòng.

---

## 6. Thứ tự triển khai, ước lượng và cổng

| Pha | Nội dung | Phụ thuộc | Ước lượng | Cổng (phải xanh mới sang pha sau) |
|---|---|---|---|---|
| **V0** | F1, R7, R8, F3 | — | 0,5 ngày | unit xanh Windows+Linux; CI chạy trên nhánh |
| **V1** | Migration DB v1→v2 | V0 | 1 ngày | nâng cấp DB P8 + idempotent + backup |
| **V2** | Config v2, profile, program_rules, wordlist, kẹp & validate (backend) | V1 | 1,5 ngày | validate đủ biên; profile/rules CRUD; kẹp đúng |
| **V3** | Rate-limit shim + ma trận enforcement | V2 | 2 ngày | unit shim (cloud) + **đo fixture rate=1 trên Codex** |
| **V4** | Xác minh scope/policy H1 | V2 | 1 ngày | nhãn xuyên suốt + cổng xác nhận |
| **V5** | URL inventory + phễu + API | V1 | 2 ngày | phễu khớp artifact; không "live" giả |
| **V6** | Diff baseline + báo cáo pha | V1 | 1 ngày | chuỗi Passive→Light xen scan huỷ |
| **V7** | Brief & Export tuỳ chỉnh | V5, V6 | 1 ngày | ZIP lọc scope; brief ≤ ngân sách |
| **V8** | UI: Review tuỳ chỉnh, profile, quy tắc, Dữ liệu, tái cấu trúc IA, mobile bar | V2–V7 | 3 ngày | Vitest + E2E mock + 320/390/1366 |
| **V9** | Giám sát tuỳ chỉnh (`every N giờ ≥6`, giờ trong ngày, ngày trong tuần, cửa sổ giờ, chọn profile) + nghiệm thu + tài liệu + spec v2.6 | V8 | 1 ngày | tick thật, TC-* đầy đủ |

Tổng ≈ 14 ngày công. Có thể song song V4/V5/V6 sau V2. Commit nhỏ theo pha, đẩy lên nhánh `claude/upbeat-thompson-b7bb23`; mỗi pha cập nhật `NOTES.md`.

## 7. Kiểm chứng: ai làm gì

| Việc | Cloud (tôi) | Codex/host | Bạn (tay) |
|---|---|---|---|
| Unit/Vitest/migration/shim/ingest/validate | ✔ | chạy lại trên Windows | |
| E2E mock H1 + Playwright 320/390/1366 | ✔ | chạy lại | |
| Đo rate thực từng công cụ trên fixture localhost (Docker) | — | ✔ (V3 gate) | |
| Chuỗi scan Passive→Light→huỷ để tái hiện R4 | viết test | chạy với DB thật | cung cấp dữ liệu #9–#12 đã bỏ nhạy cảm |
| H1 thật + API token; đối chiếu scope/policy | — | — | ✔ |
| Lighthouse/axe, >1000 dòng, điện thoại thật | — | một phần | ✔ |
| Agent `claude` thật đọc PROGRAM/BRIEF | — | — | ✔ |

Test mới (ID): TC-MIG-1..4, TC-CFG-1..8 (validate/kẹp/profile), TC-RL-1..8 (shim, đo rate), TC-H1V-1..4, TC-URL-1..6, TC-DF-5..7, TC-EXP-7..9, TC-PR-1..4 (program rules), TC-UX-11..16 (customize UI, mobile bar, thuật ngữ).

---

## 8. Điểm cần bạn quyết định (mặc định của tôi in đậm — nếu bạn đồng ý thì không cần trả lời)

1. **Vá giới hạn ở shim trong `advance_asm`** thay vì sửa vendor? → **Shim.** (Vá upstream `claude-bug-bounty` cần quyền push của bạn; có thể làm sau.)
2. `automation = forbidden` có **chặn cứng** (server từ chối Light/Strong) không? → **Có.**
3. Cho phép **tải wordlist lên** (≤5 MB)? → **Có.**
4. Cho phép **header/User-Agent nhận diện** tuỳ chỉnh (cấm Authorization/Cookie)? → **Có.**
5. Bước **không bảo đảm được rate limit** khi người dùng đặt rate thấp: → **tự tắt bước đó + giải thích** (thay vì chặn toàn bộ Launch).
6. Tái cấu trúc Program 7 tab → 5 khu vực và đổi thuật ngữ sang tiếng Việt thống nhất? → **Có.**
7. Export mặc định → **"Đã lọc scope"** (thô vẫn chọn được, có nhãn cảnh báo).
8. Giờ lịch giám sát lưu theo **UTC + hiển thị theo múi giờ trình duyệt**; bạn cần múi giờ cố định khác không? → **Không.**
9. Có thể bạn muốn thêm tuỳ chỉnh nào chưa có trong bảng 4.2 (ví dụ nguồn lịch sử khác, ngôn ngữ giao diện, giới hạn dung lượng recon) → nêu ra, tôi bổ sung vào V2 trước khi code.

## 9. Rủi ro chính
- **Shim làm hỏng công cụ** (khác phiên bản cờ): mỗi shim có test argv theo phiên bản đang ghim + chế độ `BBASM_SHIM_DISABLE=1` chỉ dùng khi debug (UI hiện "giới hạn không được bảo đảm").
- **Migration trên DB thật của bạn:** luôn backup tự động; Codex thử trên bản sao DB trước.
- **Phạm vi lớn:** làm theo cổng; nếu cần cắt, giữ V0→V3 + V4 + V5 (an toàn + dữ liệu) trước, hoãn V7/V9 và các tuỳ chỉnh nhóm "Đầu ra".
- **Policy-extraction gợi ý sai:** chỉ là chip gợi ý, người dùng xác nhận mới áp.
