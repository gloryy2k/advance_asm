# Bàn giao Claude Cloud → Claude Local

> **Cập nhật từ Claude Local (2026-10-17):** tài liệu dưới đây là bản gốc của Claude Cloud, dừng ở `e456029` (v1.6.0) —
> giữ nguyên để tra lịch sử, **không còn phản ánh baseline hiện tại**. Baseline mới nhất: `claude/upbeat-thompson-b7bb23`
> tại `488d910`-submodule / commit code gần nhất trên nhánh đó theo `git log` (xem `COORD_TASKS.md` để biết chính xác,
> file này không tự cập nhật theo từng commit). Việc đã làm sau `e456029`: xem `NOTES.md` mục v1.6.1, v1.6.2. Mục 6 và
> mục 9 dưới đây **đã lỗi thời** — `NUCLEI_COVERAGE_FOLLOWUP.md` mục 9 đã được xử lý một phần (xem `BACKLOG.md` phần
> "Độ phủ nuclei"), không còn là "chưa đọc". Quy trình phối hợp Claude Local ↔ Codex QA hiện tại: `COORD_TASKS.md`.

Tài liệu này đủ để tiếp tục công việc mà không cần lịch sử chat. Mọi khẳng định “đã làm/đã test” đều có commit hoặc tên test để kiểm lại từ repo; chỗ nào chưa kiểm chứng được thì nói rõ ở mục 9.

## 1. Bản đồ repo, nhánh, worktree (đo ngày 2026-10-16)

- Repo: `https://github.com/gloryy2k/advance_asm`. Cloud làm việc tại `/home/user/advance_asm` (một worktree duy nhất, không stash).
- **Nhánh source hiện hành: `claude/upbeat-thompson-b7bb23`.** Commit code cuối trước tài liệu này: **`e456029`** (v1.6.0). `origin/claude/upbeat-thompson-b7bb23` = `e456029` lúc kiểm kê; working tree sạch, không có thay đổi chưa commit, không có commit chưa push.
- `origin/main` không có commit nào mà nhánh source thiếu (nhánh source hơn `main` 108 commit, `main` hơn 0). **Không merge main** theo yêu cầu.
- Submodule: `vendor/claude-bug-bounty` @ `7acb66a` (`fix: skip IP historical queries and bound provider collection`), URL `https://github.com/gloryy2k/claude-bug-bounty.git`. Cloud **không sửa** submodule (không có quyền push repo đó từ phiên này); mọi bù trừ nằm trong BBASM (shim, bộ đọc). Xem mục 8 về `open_ports.txt`.

### Nhánh khác (đối chiếu với `e456029`)

| Nhánh | Tip | Loại | Nội dung | Tích hợp? | Bằng chứng |
| --- | --- | --- | --- | --- | --- |
| `test/arc-bbp-strong-audit` | `f114d17` | **Chỉ tài liệu QA** | `ARC_BBP_STRONG_AUDIT.md`, `FFUF_NMAP_AUDIT.md`, `ASSET_TYPE_HANDLING.md`, `SITEMAP_REDESIGN_PROPOSAL.md` + ảnh/mockup trong `review_evidence/` | Không merge (đúng yêu cầu). Cơ sở nhánh là `42e3a0d`, **không có thay đổi code** nào so với nó | `git diff --name-only 42e3a0d f114d17` chỉ ra file `.md` và `review_evidence/` |
| `test/v154-host-results` | `d5d5ac9` | Chỉ tài liệu QA | Kết quả QA v1.5.4 (14 PASS, 1 FAIL ZIP IP) | Không merge. Lỗi đã sửa ở `42e3a0d`, Codex xác nhận PASS | `V154_HOST_RESULTS.md` |
| `fix/path-out-safe-scan` | `2d540fd` | **CODE (Codex)** | “verify known IN paths without crawling OUT hosts”: thêm `backend/jobs/safe_path_probe.py`, ép host có OUT-path chỉ probe vĩnh viễn, bỏ ô cho phép quét chủ động | **CỐ Ý KHÔNG tích hợp** | Quyết định của chủ dự án ghi tại `BACKLOG.md` dòng ~20: “GET tới endpoint OUT trong domain được chấp nhận, chỉ tránh POST/PUT/PATCH/DELETE; giữ logic hiện tại (probe-only mặc định + ô cho phép); không merge phần hạn chế của `2d540fd`”. Ngoài ra `git merge-tree` cho thấy **xung đột** ở `backend/jobs/recon_orch.py` và `backend/jobs/runner.py` |
| `audit/input-output-flow` | `a5fe600` | Code (chứa `2d540fd`) + tài liệu | 4 commit docs (`INPUT_OUTPUT_FLOW_AUDIT.md`, `PATH_OUT_REAL_TOOLS_RESULTS.md`…) trên nền `2d540fd` | Cùng lý do như trên. `git cherry HEAD origin/audit/input-output-flow` cho 5 commit “+” (chưa có trong source) |
| `test/v134-fixes-host-results` | `d3d8fdd` | Tài liệu + `review_tools/*.py` QA | Kết quả QA v1.3.4 | Không merge (QA). Script nằm trên nhánh đó nếu cần tái dùng | `git diff --name-only` |
| `test/v121-host-results` | `5a32fad` | Chỉ tài liệu QA | `V121_HOST_RESULTS.md` | Không merge | — |
| `build/p0…p8`, `test/*` còn lại | — | Lịch sử cũ | Đã nằm trong lịch sử nhánh source (`git rev-list --count HEAD..<nhánh>` = 0) | Đã tích hợp | `for b in …; git rev-list --count HEAD..origin/$b` |

Kết luận kiểm kê: **không có nhánh code nào cần merge thêm**; nhánh code duy nhất chưa tích hợp là `fix/path-out-safe-scan` (và `audit/input-output-flow` chứa nó), bị loại theo quyết định đã ghi. Nếu chủ dự án đổi ý: `git merge-tree --write-tree --name-only HEAD origin/fix/path-out-safe-scan` để xem xung đột; cách tiếp tục là cherry-pick `2d540fd` trên một nhánh mới, giải quyết xung đột ở `recon_orch.py` (hàm `build`, `_probe_only_host`) và `runner.py`, chạy lại `backend/tests/test_v13_path_rules.py`. Không làm điều đó khi chưa có xác nhận.

Codex dùng worktree ở máy local (ví dụ `E:\code\bbasm\advance_asm_arcqa`, `…\advance_asm_v154qa`); Cloud không thấy chúng.

## 2. Kiến trúc ngắn của flow

1. **Input / Resolve** — `backend/api/scope.py` → `backend/jobs/scope_resolver.py` (+ `h1_scope.py` cho HackerOne, `scope_parse.py` cho raw). Tạo `program` + draft `scan_run` (trạng thái `draft`) với `stats_json.resolved_scope` (mỗi entry: pattern, kind in/out, category, `instruction`), `policy_snapshot`, `launch_gate`.
2. **Review** — `JobRunner.review()` (`backend/jobs/runner.py`) + `frontend/src/pages/Review.tsx`. Cấu hình `ScanConfig` (`backend/models.py`) tự lưu vào `scan_config` khi sửa. Server tính: plan các bước (`POST /api/meta/plan`, `backend/asm/phases.py::plan_for`), **độ phủ theo asset** (`POST /api/scans/{id}/coverage`, `backend/coverage.py`), xác nhận bắt buộc (ack, ffuf, header, apex) ở `backend/api/scans.py::require_*`.
3. **Scope gate** — `backend/scope_gate.py` (IN/OUT host, wildcard, CIDR, URL-path rule) và `backend/scope_selection.py::effective_gate` (một cách duy nhất để dựng gate từ scope + config: dùng ở plan, export, scheduler). Lựa chọn Review (host bỏ tick, OUT gõ tay) lưu theo program (`program.scope_selection_json`).
4. **Plan** — `ReconOrchestrator.build()` (`backend/jobs/recon_orch.py`): sinh `Command` (argv + env từ `recon_env`) cho discovery (wildcard), host nêu trong scope (main), repo (source), kèm `asset_coverage`, `manual_assets`, `path_rules`.
5. **Chạy** — `JobRunner._execute/_pipeline/_stage/_command`: giai đoạn **discovery → main → probe (đợt, probe-only, không nmap) → deep (crawl, nuclei, nmap, ffuf trên host đã trả lời) → monitor (takeover/secret)**. Trần giai đoạn tích lũy 25/45/62/95% của `scan_timeout`; mỗi lệnh có trần theo phần còn lại. Công cụ được bọc bằng shim ở `backend/shims/` (curl, subfinder, katana, nuclei, **nmap, ffuf**).
6. **Ingest** — `backend/jobs/ingest.py` (asset/URL/finding + funnel; mọi URL qua gate), `backend/asm/monitors.py` (takeover/secret, parser ở `backend/asm/takeover.py`), `diff_engine.py`, `ranking.py`, rồi `backend/brief/generator.py` (AGENT_BRIEF.md).
7. **DB** — SQLite `data/bbasm.db`, schema v5 (`backend/migrations.py`; đợt này **không** đổi schema). Lưu số liệu scan ở `scan_run.stats_json` (stages, coverage, asset_coverage, unprobed_hosts, repairs…).
8. **Đọc ra** — Run (`/api/scans/{id}/phases` → `phases.build_report`, đọc kết quả thật qua `backend/asm/results.py`), Data/Findings/Diff (`backend/api/programs.py`), Brief/Export (`backend/brief/`), Tools (`backend/tools.py`, `templates.py`), Charts (`/api/programs/{slug}/charts`).
9. **Rescan / Diff / schedule** — `POST /rescan` tạo draft mới từ lựa chọn đã lưu; `scan_run.baseline_scan_id` + `diff_event`; lịch (`backend/asm/scheduler.py`) kiểm lại gate/header/ffuf/apex lúc dispatch và ghi `schedule.last_error`.
10. **Sửa dữ liệu cũ khi khởi động** — `backend/repair.py` (idempotent, sao lưu DB trước): takeover cũ, nhãn auth cũ.

Ghi chú tên: sau khi đọc “phase” trong code hãy phân biệt `PHASES` (bước hiển thị cho người dùng, `phases.py`) với stage của pipeline (`STAGES`, `runner.py`).

## 3. Việc đã làm trong đợt này (xem `git log 42e3a0d..e456029`)

| Commit | Nội dung | File chính | Vì sao |
| --- | --- | --- | --- |
| `4cdb0a6` | **P1**: parser subjack + sửa dữ liệu #65; bỏ nmap khỏi probe; repo giới hạn bị khóa; shim nmap/ffuf | `backend/asm/takeover.py`, `monitors.py`, `repair.py`, `coverage.py`, `recon_orch.py`, `shims/{nmap,ffuf}` | F1, F2, FN1 |
| `0adf06b` | **P2**: độ phủ theo bằng chứng + trần từng lệnh; đọc kết quả nmap/ffuf; funnel; nhãn auth; log ffuf | `runner.py`, `recon_orch.py`, `asm/results.py`, `phases.py`, `urlintel.py`, `ingest.py`, `log_buffer.py` | F3, F4, F5, FN2–FN4, CDN |
| `4a811f8` | Panel độ phủ asset, apex tường minh, xác nhận repo, ngân sách theo scan, `unprobed_hosts`, “ghi nhận lần đầu” | `CoveragePanel.tsx`, `api/scans.py`, `scope_selection.py`, `models.py`, `Program.tsx` | F6, F7, độ phủ asset, timeout |
| `e456029` | Cây sitemap mới, tab program lưu trữ, độ phủ trong Run/Tổng quan, `ARC_BBP_TRIAGE.md` | `SitemapTree.tsx`, `UrlExplorer.tsx`, `Portfolio.tsx`, `sitemap.py` | Đề xuất UX |

Trước đó trong cùng phiên dài (đã Codex kiểm): v1.5.2 template nuclei (`dcef0e5`), v1.5.3 dọn draft/lưu trữ/xóa vĩnh viễn (`eb4b0d9`), v1.5.4 biểu đồ (`14eb287`), v1.5.5 ZIP IP có path + test Run độc lập đồng hồ (`42e3a0d`, **Codex xác nhận PASS, CI xanh**). Chi tiết ở `NOTES.md` (v1.3.8 → v1.6.0) và `BACKLOG.md`.

**Chưa Codex kiểm:** toàn bộ `4cdb0a6`…`e456029` (v1.6.0).

### Kết quả test tại HEAD (chạy trong phiên này)

| Lệnh | Kết quả |
| --- | --- |
| `python -m pytest -q -m "not integration"` | **445 passed**, 33 deselected |
| `cd frontend && npx vitest run` | **88 passed** (1 file) |
| `cd frontend && npx tsc --noEmit` ; `npm run build` | sạch ; build OK |
| `python -m pytest -q -m integration -k "not phone" backend/tests/test_browser_integration.py backend/tests/test_docker_integration.py backend/tests/test_h1_scope.py backend/tests/test_recon_integration.py backend/tests/test_ui_e2e_mock_h1.py backend/tests/test_v13_pipeline.py backend/tests/test_websocket_runtime.py` | **20 passed, 2 skipped**, 23 deselected, 0 failed (120 s). 2 skip = test cần Docker/điện thoại thật |

Test hay chớp: Vitest `picking a saved profile applies its recipe but keeps this scan's scope choices` từng timeout 4 s một lần khi máy bận; chạy lại thì pass. Không phải lỗi logic.

## 4. Bảng finding — `ARC_BBP_STRONG_AUDIT.md` (F1–F7) và `FFUF_NMAP_AUDIT.md` (FN1–FN4)

Quy ước: báo cáo QA mô tả **bản cũ `42e3a0d`**; cột “Bằng chứng” là bằng chứng trên **mã hiện tại**. Mọi test là fixture/mock/127.0.0.1.

| Mã | Trạng thái | Bằng chứng trong code | Test |
| --- | --- | --- | --- |
| **F1** subjack “Not Vulnerable” → takeover High | **Đã sửa** (mã mới); dữ liệu #65 cũ được sửa khi khởi động | `backend/asm/takeover.py::parse_subjack`; `monitors.py` chỉ lưu `[SERVICE]` thành `subjack:<SERVICE>`, Medium, `verified:false`; `repair.py::repair_takeover` (sao lưu DB, đọc lại `subjack.txt` của chính scan, tạo lại Brief, ghi `stats.repairs`; không có file → hạ `info` + `legacy_unreliable`); UI: ghi chú ở Tổng quan/Phát hiện qua `summary.data_notes` | `test_v160_takeover.py` (5): `test_parser_keeps_only_real_candidates`, `test_scan_ingest_stores_only_candidates…`, `test_stored_results_from_the_old_parser…`, `test_without_the_original_file_nothing_stays_high`. **Chưa chạy trên DB thật của người dùng** |
| **F2** partial scope source code | **Đã sửa ở mức khóa; cưỡng chế thật = cần quyết định** | `coverage.py::entry_coverage`: repo có `instruction` → `manual_confirm`; `ReconOrchestrator.build` bỏ qua, ghi `plan.manual_assets` + cảnh báo; chỉ chạy khi `config.source_full_repo_ok` chứa repo (Review tick) | `test_v160_p1.py::test_a_repo_whose_scope_text_limits_it_is_not_scanned_automatically`, `…the_user_can_confirm_a_whole_repo_scan…`; Vitest “a repo whose scope text limits it stays manual…” |
| **F3** “đã probe 0” khi batch timeout | **Đã sửa** | `ReconOrchestrator.refresh_coverage` (attempted/responded/completed/unreached; `probed`=completed∪responded), `deep_command` dùng `probe_answers` (không đòi batch xong), `runner._stage` trần từng lệnh | tích hợp `test_v13_pipeline.py::test_a_batch_cut_off_mid_way_keeps_its_answers…`; Vitest “Run: partial nmap says so… coverage is split by evidence” |
| **F4** funnel 456 ≠ 489 | **Đã sửa** | `ingest.py`: `in_scope + from_probe == stored` (sau `_collapse_ranges`); UI `UrlExplorer.tsx`, `Run.tsx` | `test_v160_results.py::test_url_funnel_adds_up_to_what_the_table_shows` |
| **F5** nhãn auth bắt “token” | **Đã sửa** | `urlintel.py::_is_auth_path` (theo segment); `repair_url_auth_labels` gỡ nhãn dữ liệu cũ | `test_v160_results.py::test_auth_label_needs_an_endpoint…`, `test_v160_takeover.py::test_stored_urls_lose_a_wrong_auth_label_once` |
| **F6** scan đầu hiện “thay đổi so với scan trước” | **Đã sửa** | `Program.tsx`: `baseline_scan_id == null` → “Ghi nhận lần đầu — dữ liệu khởi tạo” | Vitest “Program: the first scan is initial data…” |
| **F7** `*.arc.io` không gồm `arc.io` | **Đã sửa (tường minh, không mở rộng ngầm)** | Panel “Wildcard và domain gốc” (`CoveragePanel.tsx`); `include_apex` + `apex_confirmed` (`models.py`); `scope_selection.included_apex/effective_gate`; `require_apex` ở launch/auto-scan/lịch/dispatch; chỉ apex của wildcard IN, OUT vẫn thắng; mặc định **không** thêm | `test_v160_p1.py::test_the_apex_is_outside_a_wildcard_unless…`, `…test_launch_refuses_an_unconfirmed_apex…`; Vitest “the apex is a separate, explicit choice…”. **Chưa** đối chiếu policy chính thức H1 (UI chỉ yêu cầu người dùng xác nhận) |
| **FN1** nmap `-sV` 1000 cổng trong probe | **Đã sửa** | `recon_env(probe_only=True)` đặt `BBASM_SKIP_NMAP=1`; shim `backend/shims/nmap` (`--host-timeout`, `--max-retries 1`, tổng thời gian, ghi chú “DỞ DANG”) | `test_v160_p1.py::test_probe_stage_never_runs_nmap_but_the_deep_pass_still_may`, `…path_restricted_hosts…`, `test_nmap_wrapper_*` |
| **FN2** `open_ports.txt` thiếu cổng | **Đã sửa ở BBASM; file của engine vẫn sai** | `asm/results.py::read_nmap_greppable/summarize_ports` (cặp host/cổng/giao thức; “cặp” ≠ “số cổng khác nhau”). `open_ports.txt` do `recon_engine.sh` (submodule) tạo vẫn dùng `sed` tham lam | `test_v160_results.py::test_every_host_and_port_is_read…`, `…unique_ports_and_host_port_pairs…` |
| **FN3** ffuf 403 giống hệt nhau | **Đã sửa** | shim `ffuf` thêm `-ac` + `-maxtime` (trừ khi người dùng đã đặt bộ lọc); `results.py::read_ffuf` gom theo (status,length,words), nhóm ≥5 và ≥60% = nhiễu; 403 không thành finding | `test_identical_block_pages_are_noise_and_403_is_never_a_hit`, `test_ffuf_wrapper_calibrates_and_bounds_the_run` |
| **FN4** Run đếm dòng; nmap dở = “Đã chạy” | **Đã sửa** | `phases.structured_result`; trạng thái `partial` “Chạy dở dang”; `detail` hiện số cặp host/cổng, nhiễu ffuf, ứng viên takeover | `test_run_report_counts_results_not_lines_and_flags_a_cut_off_nmap`; Vitest Run |
| nmap trên IP CDN | **Đã sửa** | `results.cdn_of` (dải Cloudflare tĩnh + banner CDN khác) → “cổng của CDN, chưa chứng minh là origin” | `test_cloudflare_ports_are_labelled…` |
| Log ffuf “not installed or no live hosts” | **Đã sửa** | `log_buffer.py::ReconLogParser.classify` phân biệt thiếu binary / chưa có host sống / bỏ qua theo cấu hình | `test_v160_p1.py::test_ffuf_log_line_tells_apart…` |
| `ASSET_TYPE_HANDLING.md` (độ phủ theo loại asset) | **Đã sửa phần hiển thị; adapter = cần quyết định** | `coverage.py`; panel Review; `AssetCoverageNote` ở Run/Tổng quan; `stats.asset_coverage` | `test_v160_p1.py::test_mobile_other_and_non_github…`; Vitest “Review: coverage by asset type…”, “Run/Overview…” |
| `SITEMAP_REDESIGN_PROPOSAL.md` | **Đã làm** | `SitemapTree.tsx`: hàng gọn, đường nối CSS, panel chi tiết, tìm kiếm phẳng + “Xem trong cây”, giữ lazy-load/phân trang/bàn phím/aria; `sitemap.py` thêm `sources`; mobile xếp dọc | Vitest “Sitemap tree…” (3), `test_v138_sitemap.py` (+1). Ảnh chụp headless ở máy Cloud, không commit |
| Tìm program đã lưu trữ | **Đã sửa** | `Portfolio.tsx`: tab “Đang hoạt động (n) / Đã lưu trữ (m)” | Vitest “Portfolio: archived programs live under their own tab…” |

Bảng gốc từng mục (loại/mức ưu tiên/tác động) nằm ở `ARC_BBP_TRIAGE.md`.

## 5. Đề xuất chưa quyết định (chưa làm; quyết định thuộc chủ dự án)

1. **Timeout linh hoạt theo program/stage.** Đã có: `scan_timeout` toàn scan, `nmap_timeout`, `ffuf_maxtime`, `deep_hosts` theo scan, trần giai đoạn cố định 25/45/62/95%, trần từng lệnh. Chưa có: tự co giãn theo số host khám phá; cấu hình `STAGES` theo profile.
2. **Giữ output partial & chạy tiếp phần chưa quét.** Output dở dang được nhập; `stats.unprobed_hosts` (≤2000) đã lưu. Chưa có nút “Probe tiếp”: cần chốt diff (scan con luôn “không đầy đủ”, không suy ra `gone`), Brief, lịch.
3. **Độ phủ theo loại asset / adapter mobile, source, other.** Hiện chỉ hiển thị trung thực. Adapter cần gate quyền theo từng asset, không suy từ chuỗi mô tả.
4. **Giới hạn thư mục của repo** (trufflehog `--include-paths/--exclude-paths`; sửa `secrets_hunter.sh` ở submodule).
5. **Nhập ffuf/nmap vào bảng dữ liệu có cấu trúc** (“Đường dẫn dò được”, “Cổng/Dịch vụ”). Hiện chỉ đọc lúc dựng báo cáo Run.
6. **Sửa `open_ports.txt` ở engine** (submodule).
7. Burp sitemap import/diff: người dùng bảo để sau.

## 6. Việc chờ Codex audit lại trên bản mới (v1.6.0 = `e456029` trở đi)

Prompt đã soạn ở cuối phiên Cloud (mục 10). Trọng tâm:
- **Review → lệnh chạy:** config/độ phủ/xác nhận trong Review khớp `Command.env/argv` thật (nmap off ở probe, apex, repo khóa, ngân sách).
- **discovery → probe → deep:** coverage, deep chọn host từ câu trả lời của mọi đợt, trần giai đoạn/lệnh, Cancel nhanh.
- **output → DB/UI/Brief/Export:** funnel, takeover, nhãn auth, kết quả nmap/ffuf, ghi chú sửa dữ liệu, Brief tạo lại.
- **rescan/schedule → Diff:** apex/repo/ffuf xác nhận ở lịch; scan đầu = dữ liệu khởi tạo; partial không suy ra `gone`.

**Scan arc-bbp #65 là bằng chứng từ bản cũ (`42e3a0d`). Tuyệt đối không quét lại arc-bbp, Wolt hay host ngoài.** Muốn kiểm dữ liệu #65: dùng bản sao chỉ đọc DB/targets của người dùng (xem mục 7), hoặc dựng fixture.

## 7. Giới hạn môi trường

- Stack của người dùng: Docker project `bbasm-v12` tại `127.0.0.1:18765`, DB `data/bbasm.db` và `targets/` của họ. **Giữ nguyên:** không sửa/commit `.env`, DB, targets; không `docker system prune` hay xóa volume/image không phải của mình; stack QA dùng project, cổng và thư mục riêng (ví dụ `-p bbasm-v160qa`, `BBASM_PORT=18793`).
- Image hiện chạy ở 18765 là bản cũ: sau khi người dùng đồng ý mới rebuild. Bản mới cần build lại vì thêm PyYAML (v1.5.2), shim `nmap`/`ffuf` (v1.6.0). Khi khởi động bản mới trên DB thật, `repair.py` sẽ sửa dữ liệu #65 (có bản sao `bbasm.db.pre-repair-*` trong thư mục `data/`); cân nhắc sao lưu thủ công `data/` trước.
- Không dùng token/cookie HackerOne (`h1_api=false`). Không scan host ngoài; kiểm thử chỉ dùng fixture, mock, `127.0.0.1/127.0.0.2`.
- Công cụ recon cần bash + binary (subfinder, httpx, nmap…): chạy trong Docker/WSL; trên Windows thuần dùng `BBASM_RECON_DISABLED=1` cho phần UI/API.

## 8. Việc KHÔNG làm được / chưa kiểm chứng

| Mục | Lý do | Cách tái hiện tiếp |
| --- | --- | --- |
| `repair.py` trên DB thật của #65 | Cloud không thấy DB/targets của người dùng | Sao chép DB và `targets/arc-bbp` sang thư mục tạm, chạy `BBASM_DATA=… python -m backend.main` (hoặc gọi `backend.repair.run_repairs`), so số High takeover trước/sau (kỳ vọng 128 → ~4 Medium nếu `subjack.txt` còn) |
| Hành vi shim `nmap`/`ffuf` với binary thật | Test dùng binary giả ghi argv | Trong Docker: chạy một lần nmap/ffuf vào 127.0.0.1 với `BBASM_NMAP_TIMEOUT=1` và xem file đầu ra + ghi chú; kiểm `-ac`, `--host-timeout`, `-maxtime` được chấp nhận ở phiên bản đóng gói |
| Định dạng dòng subjack thật | Giả định `[Not Vulnerable] host` và `[SERVICE] host` theo báo cáo QA | Xem `subjack.txt` thật của #65; nếu có dạng khác (`[Edge Case]`…), mở rộng `backend/asm/takeover.py` + test |
| Danh sách IP Cloudflare | Bản chép tĩnh | Cập nhật định kỳ từ danh sách chính thức; chỉ là nhãn “likely” |
| Tỷ lệ trần giai đoạn 25/45/62/95% | Chưa đo trên scan Strong thật | Một scan Strong nhỏ trên stack QA localhost; xem `stats.stages` |
| Cập nhật template từ GitHub thật, persistence volume | Cloud bị 403 tới GitHub; Codex đã xác nhận ở v1.5.4 | — (đã PASS ở `V154_HOST_RESULTS.md`) |
| Đối chiếu policy chính thức cho apex | Không dùng H1 | Người dùng tự xác nhận trong Review |
| Screenshot không được commit | Cloud chỉ giữ ở scratchpad | Chụp lại bằng Playwright headless nếu cần |

## 9. Ghi chú Codex: `NUCLEI_COVERAGE_FOLLOWUP.md` (chưa có trong Git)

Codex có file **chưa commit/push** ở máy local: `E:\code\bbasm\advance_asm_arcqa\NUCLEI_COVERAGE_FOLLOWUP.md`. Cloud không đọc được. **Claude Local cần đọc file này sau khi sửa/kiểm các finding hiện tại; chưa phải yêu cầu sửa ngay.** Nội dung chính theo lời người dùng: 14.036 template là số **đã cài**, không phải số **đã thực thi**; scan #65 chỉ đưa 2 URL cho nuclei; cần audit lại giới hạn 50/200 URL mỗi lệnh, số host/template thực chạy và trạng thái partial trên bản mới. Điểm bắt đầu trong mã (kiểm từ repo): `vendor/claude-bug-bounty/tools/recon_engine.sh` ~dòng 681–700 (`NUC_LIMIT` = 50 khi `--quick`, 200 khi không; `head -"$NUC_LIMIT" live/urls.txt`; `NUC_TIMEOUT` 600/1800 s), `backend/shims/nuclei`, `recon_orch._template_env`, `stats.nuclei_templates` (chỉ ghi số template cài đặt).

## 10. Lệnh cho Claude Local

```bash
git clone https://github.com/gloryy2k/advance_asm.git && cd advance_asm   # hoặc dùng bản sẵn có
git fetch origin
git checkout claude/upbeat-thompson-b7bb23
git pull --ff-only origin claude/upbeat-thompson-b7bb23
git submodule update --init --recursive        # vendor/claude-bug-bounty phải ở 7acb66a
git log --oneline -8                            # e456029 là commit code; commit sau đó chỉ là tài liệu bàn giao
git status --short                              # kỳ vọng: sạch

# kiểm chứng
python -m pytest -q -m "not integration"        # kỳ vọng 445 passed
cd frontend && npm ci && npx vitest run && npx tsc --noEmit && npm run build   # 88 passed
cd .. && python -m pytest -q -m integration -k "not phone" backend/tests/test_ui_e2e_mock_h1.py backend/tests/test_v13_pipeline.py   # cần Playwright/Chromium; dùng port/thư mục tạm

# chạy thử UI/API với dữ liệu tạm (không dụng tới stack của người dùng)
BBASM_DATA=/tmp/bbasm-local/data BBASM_TARGETS=/tmp/bbasm-local/targets BBASM_PORT=18793 BBASM_RECON_DISABLED=1 python -m backend.main
```

Đọc theo thứ tự: `CLOUD_TO_LOCAL_HANDOFF.md` → `ARC_BBP_TRIAGE.md` → `NOTES.md` (cuối file: v1.5.2 → v1.6.0) → `BACKLOG.md`. Các báo cáo QA gốc: `git show origin/test/arc-bbp-strong-audit:ARC_BBP_STRONG_AUDIT.md` (và 3 file còn lại).

**Việc ưu tiên đầu tiên cho Claude Local:**
1. Xác nhận checkout + test như trên (mục này).
2. Chạy `repair` trên **bản sao** DB/targets của #65 (mục 8, dòng 1) để chắc dữ liệu cũ thật sự sạch; so với báo cáo QA (128 High → ~4 Medium).
3. Chuyển prompt audit v1.6.0 cho Codex (mục 6) hoặc tự kiểm theo 4 nhóm đó; không quét lại target.
4. Sau đó mới đọc `NUCLEI_COVERAGE_FOLLOWUP.md` (mục 9).
5. Không mở rộng phạm vi trước khi các mục 1–3 xong; các đề xuất mục 5 cần quyết định của chủ dự án.

### Ràng buộc luôn áp dụng
Không scan host ngoài/arc-bbp/Wolt; không token/cookie H1; không sửa/commit `.env`, DB, targets của người dùng; không `docker prune` toàn cục; không merge `main`; không force-push; chỉ push nhánh `claude/upbeat-thompson-b7bb23`; không tạo PR khi chưa được yêu cầu; không ghi định danh mô hình vào commit/PR/file trong repo; dùng “they/them” cho người chưa rõ đại từ; phần trailer của commit theo cấu hình của phiên Local.

## 11. Prompt để khởi động Claude Local (dán nguyên văn)

```text
Bạn tiếp tục dự án BBASM (FastAPI + SQLite + React/Vite + engine bash vendored) từ Claude Cloud. Không dựa vào lịch sử chat nào.

1. Trong repo gloryy2k/advance_asm: git fetch origin && git checkout claude/upbeat-thompson-b7bb23 && git pull --ff-only && git submodule update --init --recursive. Xác nhận git status sạch và git log -8 có commit e456029 (v1.6.0) cùng commit tài liệu bàn giao phía sau.
2. Đọc theo thứ tự: CLOUD_TO_LOCAL_HANDOFF.md, ARC_BBP_TRIAGE.md, phần cuối NOTES.md (v1.5.2 → v1.6.0), BACKLOG.md. Báo cáo QA gốc lấy bằng git show origin/test/arc-bbp-strong-audit:<file> (ARC_BBP_STRONG_AUDIT.md, FFUF_NMAP_AUDIT.md, ASSET_TYPE_HANDLING.md, SITEMAP_REDESIGN_PROPOSAL.md); chúng mô tả bản cũ 42e3a0d, không phải bằng chứng code mới còn lỗi.
3. Chạy kiểm chứng: python -m pytest -q -m "not integration" (kỳ vọng 445 passed); cd frontend && npm ci && npx vitest run (88 passed) && npx tsc --noEmit && npm run build. Báo số thực tế, nếu khác thì dừng và điều tra trước.
4. Việc đầu tiên: chạy backend.repair (run_repairs) trên BẢN SAO DB/targets của scan arc-bbp #65 do tôi cung cấp, so số takeover High trước/sau (QA ghi 128 High giả); không dùng DB/targets gốc.
5. Sau đó: kiểm shim nmap/ffuf với binary thật chỉ vào 127.0.0.1, rồi đọc E:\code\bbasm\advance_asm_arcqa\NUCLEI_COVERAGE_FOLLOWUP.md (chưa có trong Git) và audit độ phủ nuclei: 14.036 là số template đã cài chứ không phải đã chạy, #65 chỉ đưa 2 URL cho nuclei, giới hạn 50/200 URL mỗi lệnh (recon_engine.sh ~dòng 681), host/template thực chạy, trạng thái partial.
Ràng buộc cứng: không scan arc-bbp, Wolt hay host ngoài; chỉ fixture/mock/127.0.0.1; không token/cookie HackerOne; không sửa/commit .env, DB, targets của tôi; không đụng stack Docker bbasm-v12 (127.0.0.1:18765); không docker prune toàn cục; không merge main; không force-push; không merge fix/path-out-safe-scan (2d540fd) vì tôi đã quyết định không dùng; không tạo PR khi chưa được yêu cầu. Không mở rộng phạm vi: các đề xuất ở mục 5 của handoff cần tôi quyết định trước. Báo cáo bằng tiếng Việt, ngắn gọn, có commit và kết quả test.
```
