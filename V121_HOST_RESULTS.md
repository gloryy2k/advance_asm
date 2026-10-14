# BBASM v1.2.1 — kết quả QA trên host

Ngày 2026-10-14 (Asia/Saigon). Nguồn `claude/upbeat-thompson-b7bb23` tại `88250d8`; nhánh kết quả `test/v121-host-results`. Chỉ các API probe do QA tạo mới nhắm `127.0.0.1`; không gọi HackerOne thật, không dùng token thật, không scan host ngoài. UI chỉ đánh giá ở **1366×850**. Stack QA riêng `../advance_asm-v12test`, Compose project `bbasm-v12`, cổng `127.0.0.1:18765`; `.env` tạm chỉ có `BBASM_PORT=18765` và `BBASM_UPDATE_TEMPLATES=0`. Không sửa code sản phẩm/test, không merge `main`.

## Lệnh, kết quả, bằng chứng

| Mã | Hành động/lệnh | PASS/FAIL/SKIP | Bằng chứng ngắn |
|---|---|---|---|
| T0-GIT | `git fetch origin`; switch/pull nhánh nguồn; `git submodule update --init --recursive`; tạo `test/v121-host-results` | PASS | HEAD `88250d8`, submodule `7acb66a`; branch mới từ nguồn, worktree QA chuyển sang detached `88250d8`. |
| T0-STACK | `docker compose -p bbasm-v12 up -d --build`, sau đó `up -d --force-recreate` | PASS | Build ~14,3s, phần lớn cached. Compose lần đầu giữ container cũ nên đã force recreate; image ID container và `bbasm-v12-bbasm:latest` cùng `sha256:12aa5fc0…`. Container healthy. |
| T1-LINUX | `docker run --rm` image v1.2.1, mount read-only `scripts/`, `vendor/`, `.env.example`; `python -m pytest backend/tests -m "not integration" -q --tb=short` | **FAIL** | **306 passed, 1 failed, 25 deselected**. `test_review_payload_rescan_ack_and_program_name`: POST Launch 200 nhưng `GET /review` ngay sau đó có `automation_ack=None` thay vì timestamp (N1). Image thiếu layout test `/app/vendor`, nên unit chạy trong container tạm với các mount; không sửa image/repo. |
| T1-WIN | `.venv/Scripts/python -m pytest -m "not integration" -q --tb=short` trên Windows gốc | **FAIL** | **301 passed, 6 failed, 25 deselected**. Sáu tên test ở mục “Giới hạn”; đều cần recon native và gặp `platform_unsupported`/422. Hai test hunt command từng fail ở v1.2 nay pass. |
| T1-FE | `cd frontend && npm ci && npm test -- --run && npm run build` | PASS | 46/46 Vitest; TypeScript/Vite build thành công. |
| T1-WS-UI | `pytest -m integration backend/tests/test_websocket_runtime.py backend/tests/test_ui_e2e_mock_h1.py -k "not phone and not mobile" -q` | PASS | **6 passed, 1 skipped, 12 deselected**; H1 chỉ qua mock, 1 ca Launch trên Windows được skip đúng thiết kế. Lần chạy đầu chưa lọc suite đạt 17 pass, 1 skip, 1 deselect nhưng có cả test phone; kết quả mobile không dùng trong đánh giá này. |
| T1-BROWSER | `BBASM_E2E_TARGET=127.0.0.1 BBASM_E2E_URL=http://127.0.0.1:18765 pytest -m integration backend/tests/test_browser_integration.py -q` | PASS | 1 passed trên Docker v1.2.1. |
| T1-DOCKER | `BBASM_DOCKER_TESTS=1 pytest -m integration backend/tests/test_docker_integration.py -q -s` | PASS | 1 passed; image acceptance do test tạo được test tự xóa. |
| T1-RECON-RAW | `docker compose -p bbasm-v12 exec -T bbasm python -m pytest -m integration backend/tests/test_recon_integration.py -q` | **FAIL** | 3 passed, 1 failed: test vẫn hardcode `/app/vendor/...`, trong khi image chuẩn đặt vendor ở `/opt/...` (lỗi layout test F3 cũ). |
| T1-RECON-SETUP | `docker run --rm --entrypoint sh ...` tạo symlink tạm `/app/vendor/claude-bug-bounty → /opt/claude-bug-bounty`, chạy cùng test | PASS | 4/4 passed; symlink chỉ tồn tại trong container tạm, không sửa image, không sửa repo. |
| T1-CI | `gh run list --repo gloryy2k/advance_asm --commit 88250d8 --limit 10` | SKIP | CLI trả rỗng: chưa có run gắn với commit nguồn để kết luận trạng thái CI. |
| T2-A | `POST /api/scope/preview` 11 chuỗi raw; so portfolio trước/sau | PASS | Header `#OUT`/`OUT:` không sinh IN, `# OUTT`, CIDR sai, `bad host!!` báo lỗi; `a.com, b.com` = 2 IN; range lớn = 4 CIDR (≤32); preview không tạo program/draft. |
| F1 / T2-E-SECRET | Tạo file output QA chứa `H1_TOKEN`/Bearer marker giả, AKIA giả và URL `?token=x`; GET `/artifact`, `q=<marker>`, `/artifact/download`, `reveal=true` | PASS | Viewer mặc định che marker và AKIA, `redacted=true`; URL vẫn nguyên; tìm marker `total=0`; download mặc định che, `reveal=true` hiện marker. File thử đã xóa; báo cáo không chứa giá trị marker. |
| F2+F3 DB | Copy mới DB v1.1 vào thư mục tạm; khởi động `python -m backend.main` trên `127.0.0.1:18767`, **không gọi migrate thủ công** | PASS | Startup lên `schema_meta=2`, tạo `bbasm.db.bak-v1-20261014T150421Z`; 6 program, 12 scan, 8836 URL giữ nguyên; backup ở schema v1, `PRAGMA integrity_check=ok`. **0** URL có `tags_json`/`shape`/`score`/`verification` null. [Số liệu migration](review_evidence/v121_migration.json). |
| F2+F3 API | Trên DB bản sao: `/urls?limit=50`, offset=1000, `min_score=1`, `/urls/summary`, `/diff?scan_id=12` | PASS | Tất cả HTTP 200. API 50 URL: 20,8ms; offset 1000: 19,4ms; summary: 49,4ms; `min_score=1` còn 2584 URL. Tag toàn DB: API 1248, auth 789, JS 284, static 350, v.v. Scan #12 lịch sử vẫn baseline null, diff 0 (giới hạn đã biết, không re-ingest). |
| F2+F3 UI | Playwright 1366px mở `/#/program/qa-vuihoc-v11/data?v=urls` trên backend bản sao | PASS | Hàng đầu hiện sau **519,5ms**, 50 hàng trong trang đầu, không page error; đạt mục tiêu <2s. |
| F4 | Preview trùng IN/OUT, wildcard OUT, CIDR OUT; resolve trùng host | PASS | `a.com` IN+OUT: `ok=false`, `effective_in=0`, dòng IN có `shadowed_by`; wildcard chỉ loại `a.x.com`; CIDR chỉ loại `10.0.0.5`; resolve trùng trả 422 `scope_empty_after_out`. |
| F6 / T2-F | Light không ack; Strong qua `/api/scans` không ack; Passive không ack; Light có ack rồi cancel sau 3s | PASS | Light/Strong thiếu ack trả 422 `ack_required`, scan Light vẫn draft; Passive done; Light có ack trả 200, audit có `automation_ack_by_user`; cancel 200, `docker compose top` chỉ còn init/backend. API probe thấy ack trong Review ngay sau Launch; unit Linux vẫn có N1. |
| F7 / T2-I | POST profile `based_on=passive`, PUT config partial, PUT `depth=light`; DELETE profile QA | PASS | Depth lần lượt `passive → passive → light`; `threads=1` được giữ sau PUT cuối. |
| F8 | Playwright 1366px + axe-core WCAG 2 A/AA trên 10 route: Portfolio, New, Help, Profiles, Review, Run, Program, URLs, Hosts, Diff | PASS | **0 serious/critical** trên cả 10 route, không page error. Không chạy kiểm viewport 390px. |
| T2-G | HTTP fixture chỉ `127.0.0.1:80` trong container; Passive #15 → Light #16 → Light #17; cancel #18 → Light #19 | PASS | #16 so #15: `changed=1`, HTTP status `null→200`; #17 so #16: `changed=0`; #19 bỏ qua cancelled #18, baseline #17, `changed=0`. Fixture đã dừng. |
| H1-REVIEW | Đọc `/api/health` và `/api/scans/20/review` cho draft Verisk do người dùng tạo; kiểm điều kiện Launch trong Review | **FAIL** | `h1_api=false`, `policy.source=public_dump`, `policy.text=""`; scope chỉ có hai wildcard IN, không OUT/hướng dẫn asset. UI cảnh báo nhưng vẫn có thể bật Strong và Launch sau hai checkbox tự xác nhận. Không thể xác minh scope/policy hiện hành từ màn Review này (N2). Không Launch scan #20. |
| T5-CLEAN | Dừng backend migration bản sao/HTTP fixture; `docker compose top`, logs, SHA256 DB v1.1 gốc | PASS | Container v1.2.1 healthy, chỉ còn init/backend; không có 500/Traceback/ERROR trong log gần đây. DB gốc trước/sau cùng SHA256 `a8913f3c5db77f67600511032fa2035740df5d5d8daa737f26266d5f195e735e`. |

**Tổng: 18 PASS, 4 FAIL, 1 SKIP (23 dòng).** Các hàng `T1-LINUX` và `T1-WIN` là hai môi trường khác nhau; lỗi Windows là giới hạn recon native đã biết. `T1-RECON-RAW` chưa chạy nguyên trạng do đường dẫn test hardcode, còn cùng 4 ca pass sau setup tạm. Hàng H1-REVIEW là kiểm tra bổ sung sau khi người dùng mở draft #20.

## Finding mới

### N1 — P2: thời điểm ghi automation ack còn race trong unit Linux

- **Tái hiện:** chạy unit backend trong Linux như T1-LINUX. `backend/tests/test_u1_lifecycle.py::test_review_payload_rescan_ack_and_program_name` gọi Launch `automation_ack=true` nhận 200, rồi đọc Review ngay; `automation_ack=None` khiến 1/307 test fail. API probe Docker trên scan localhost lại thấy ack trong Review và audit, nên lỗi phụ thuộc thứ tự/timing.
- **Tác động:** Review hoặc dữ liệu audit trên DB có thể thiếu dấu thời gian xác nhận ngay sau khi API báo launch thành công. Chưa có bằng chứng ack bị mất lâu dài; audit JSONL ở API probe vẫn có sự kiện ack.
- **Hướng sửa:** lưu ack và trạng thái queued trong một giao dịch trước khi worker được chạy, hoặc bảo đảm worker merge `stats_json` không ghi đè ack; giữ regression test đọc Review ngay sau Launch. Không sửa code trong phiên QA.

### N2 — P1: Review H1 từ nguồn công khai chưa đủ dữ liệu nhưng vẫn cho phép Strong sau xác nhận

- **Tái hiện:** không cấu hình H1 API (`/api/health.h1_api=false`), Resolve `https://hackerone.com/verisk_vdp?type=team`; draft #20 có `policy.source=public_dump`, `policy.text=""`, đúng hai wildcard IN (`*.iso.com`, `*.verisk.com`), không OUT/hướng dẫn riêng. Review cho chọn Strong; điều kiện Launch chỉ kiểm hai checkbox xác nhận, không kiểm policy/scope đã được xác minh. Chưa Launch scan này.
- **Tác động:** người dùng không thể đối chiếu điều kiện tự động quét hoặc phạm vi hiện hành ngay trên Review nhưng vẫn có thể chạy công cụ active dựa vào bản sao công khai có thể đã cũ. Đây là rủi ro quyết định sai phạm vi; không kết luận program thật cho phép hay cấm scan.
- **Hướng sửa:** khi metadata là `public_dump` và thiếu policy, hiển thị Review ở trạng thái chưa đủ điều kiện cho Light/Strong; yêu cầu nhập/xác minh policy và scope hiện hành, hoặc Resolve lại từ API H1. Cho xem timestamp, nguồn và trạng thái từng asset; không gợi ý Strong trước khi có đủ thông tin. Kiểm bằng H1 mock và tình huống fallback.

## Giới hạn và mục chưa chạy

- Sáu test Windows fail, đúng tên: `test_health_reports_recon_support_and_launch_rejects_unsupported_platform`; `test_tc_lc_5_second_resolve_does_not_rewrite_scope_rules_until_launch`; `test_launch_applies_reviewed_snapshot_to_scope_rules`; `test_tc_lc_6_delete_draft_cleans_orphan_program_but_not_launched`; `test_review_payload_rescan_ack_and_program_name`; `test_tc_pr_default_profile_seeds_new_drafts_but_keeps_their_scope`. Chạy recon thật trong Docker/WSL2; test Windows native nên tách expectation `platform_unsupported`.
- Không có GitHub Actions run cho `88250d8`. Recon integration nguyên trạng trong image vẫn fail path `/app/vendor` so với `/opt`; chỉ pass với symlink setup trong container tạm.
- Không kiểm mobile/390px hoặc thiết bị thật. Lần chạy E2E đầu chưa lọc có các ca phone; chỉ kết quả chạy lại với `-k "not phone and not mobile"` được tính vào báo cáo.
- 8.836 URL là dữ liệu v1.1 trên **bản sao**; không quét lại target cũ. `funnel=null` và Diff cũ #12 0/null vì không có bằng chứng ingestion mới, không coi là tái tính Diff. Mọi API probe scan mới dùng `127.0.0.1`.
- Axe chỉ phát hiện vi phạm máy nhận diện được theo WCAG 2 A/AA; chưa thay thế kiểm tra bàn phím/cảm quan trên desktop thật.

## Dọn dẹp và trạng thái bàn giao

- Đã xóa file chứa marker giả, dừng HTTP fixture và backend migration bản sao. Không prune Docker, không sửa DB gốc v1.1; backup tự động của bản sao đã xác minh còn schema v1, 8836 URL và integrity `ok`.
- Thư mục thử nghiệm tạm ngoài repo được xóa sau khi rút bằng chứng; chỉ `V121_HOST_RESULTS.md` và `review_evidence/v121_migration.json` được commit.
- Theo yêu cầu, **giữ `bbasm-v12-bbasm-1` đang chạy** trên `http://127.0.0.1:18765` để người dùng xem. Dữ liệu QA nằm trong worktree riêng `../advance_asm-v12test`.

## HƯỚNG TEST TAY

- ☐ PASS/FAIL — Trên desktop 1366px, vào `http://127.0.0.1:18765`, mở Review, Run, Program, URL, Help; ghi chỗ khó hiểu hoặc không dùng được bằng bàn phím.
- ☐ PASS/FAIL — Chỉ với program bạn có quyền scan và sau khi đọc policy: Passive → Light → Light, xem Diff có baseline đúng, ghi scan ID và số new/changed/gone. Không dùng dữ liệu thật để suy từ bài test localhost.
- ☐ PASS/FAIL — Sau khi N1 được xử lý, Launch Light có ack rồi mở lại Review ngay; phải thấy thời điểm ack và audit JSONL có sự kiện xác nhận.
- ☐ PASS/FAIL — Khi nâng cấp DB thật sau khi sao lưu riêng, kiểm số program/scan/URL, tab URL có hàng, backup `bbasm.db.bak-v1-*`; giữ bản sao dự phòng ít nhất một tuần.
