# Prompt cho Codex — QA tự động BBASM v1.2 (dán nguyên khối bên dưới vào Codex)

> Phần "Việc người dùng tự test tay" ở cuối file KHÔNG dành cho Codex. Codex chỉ in ra hướng dẫn, không điều khiển màn hình.

```text
Bạn là QA host cho BBASM v1.2 trên máy này (Windows + Docker Desktop). Chạy kiểm thử tự động, ghi bằng chứng, KHÔNG sửa code sản phẩm/test. Nếu thấy lỗi thì ghi finding, đừng vá.

## Ràng buộc bắt buộc
- Nhánh nguồn: claude/upbeat-thompson-b7bb23 (commit a753d1b trở đi). Nhánh kết quả: test/v12-host-results (tạo mới từ nhánh nguồn). KHÔNG merge main.
- Mọi scan API chỉ nhắm 127.0.0.1. KHÔNG gọi HackerOne thật, KHÔNG scan host ngoài, KHÔNG dùng Live Nation hay bất kỳ program thật. UI HackerOne dùng mock (review_tools/mock_h1_server.py).
- KHÔNG sửa .env gốc của người dùng, KHÔNG tạo .env chứa path container (/opt, /app). Dùng worktree riêng ../advance_asm-v12test, project Docker `bbasm-v12`, cổng 127.0.0.1:18765, BBASM_UPDATE_TEMPLATES=0.
- KHÔNG đụng tới stack/dữ liệu QA cũ (advance_asm-v11test) ngoại trừ ĐỌC bản sao DB ở T4. Không docker prune toàn cục.
- Không ghi token/key vào báo cáo. Không commit data/, targets/, raw URL, bundle JS.
- Giới hạn tốc độ KHÔNG nằm trong phạm vi v1.2 (người dùng chủ động giữ nguyên); đừng báo "katana -c 50 -p 20" hay JS curl không throttle là lỗi mới — chỉ ghi chú nếu thấy.
- Phần cần người thật (thiết bị thật, mắt nhìn, H1 thật) → KHÔNG làm, ghi SKIP và in hướng dẫn chi tiết.

## T0 Chuẩn bị
git fetch origin; git switch claude/upbeat-thompson-b7bb23 && git pull; git submodule update --init --recursive; git switch -c test/v12-host-results. Ghi OS, python/node/docker/compose version, git log -1, submodule status. Tạo worktree/.env tạm như ràng buộc.

## T1 Test tự động nền (kỳ vọng từ cloud: 301 unit, 46 Vitest, 17 mock-H1 E2E)
- python -m venv .venv; pip install -r requirements.txt; python -m pytest -m "not integration" -q  → ghi số passed/failed. Từ v1.2.1: gate là Linux/WSL2/CI (cloud: 307 passed). Trên Windows gốc chỉ ghi tên các test fail, không coi là lỗi sản phẩm. Nếu có WSL2 thì chạy thêm ở đó. Khác 301 thì ghi lý do. Riêng test hunt_command trên Windows (đường dẫn C:\...) PHẢI pass.
- cd frontend && npm ci && npm test && npm run build → kỳ vọng 46 passed.
- pip install playwright && python -m playwright install chromium (nếu thiếu). Chạy: python -m pytest -m integration backend/tests/test_websocket_runtime.py backend/tests/test_ui_e2e_mock_h1.py -q → kỳ vọng 1 + 17 passed.
- Docker: docker compose -p bbasm-v12 up -d --build; BBASM_DOCKER_TESTS=1 python -m pytest -m integration backend/tests/test_docker_integration.py -q -s; rồi BBASM_E2E_TARGET=127.0.0.1 BBASM_E2E_URL=http://127.0.0.1:18765 python -m pytest -m integration backend/tests/test_browser_integration.py -q.
- Recon integration trong image: ghi lại nếu vẫn lỗi path vendor /app vs /opt (finding cũ F3) — không vá.
- GitHub Actions: kiểm run cho commit nguồn bằng gh run list; không có thì SKIP, ghi rõ.

## T2 API v1.2 trên stack Docker (script Python httpx, lưu ở thư mục tạm ngoài repo, tham khảo scripts/v11_host_probe.py)
Dùng 127.0.0.1 làm target thật duy nhất.
- T2-A Parser/Scope: POST /api/scope/preview với: "#OUT", "# OUTT", "OUT:", "a.com, b.com", "10.0.0.5/24", "10.0.0.1-10.0.0.20", "https://*.x.com", "app.x.com:8443", "bad host!!", "*.a.*.com", range quá lớn "10.0.0.0-10.200.0.0". Kỳ vọng: header OUT không tạo IN; sai cú pháp và CIDR không chuẩn là lỗi kèm ô+dòng; range thành ≤32 CIDR hoặc lỗi; "bad host!!" chỉ là MỘT lỗi (không có dòng hợp lệ ma). Thử thêm ô scope_out riêng: host nằm ở OUT không bao giờ vào danh sách IN. Preview là pure (không tạo program/draft: kiểm GET /api/programs?include_drafts=true trước/sau).
- T2-B H1 handle: 6 dạng (h1:acme, acme, hackerone.com/acme, https://hackerone.com/acme?type=team, https://www.hackerone.com/acme/, hackerone.com/acme#scope) đều ra handle "acme" ở preview. Không gọi H1 thật.
- T2-C Draft lifecycle: resolve raw 127.0.0.1 (name qa-v12) → GET /api/drafts có; DELETE /api/scans/{id} xoá được; scan đã chạy DELETE → 422 invalid_state. Program chỉ có draft không hiện ở GET /api/programs.
- T2-D Review/Plan: GET /api/meta/phases (12 bước, đủ key/title/what/touches/tools/view). POST /api/meta/plan với config passive và với light → mỗi bước có trạng thái; bước bị tắt có lý do; trường `forced` đúng. GET /api/scans/{id}/review trả scope/policy/target path.
- T2-E Launch & kết quả theo bước: launch passive (automation_ack=false) → done. GET /api/scans/{id}/phases: mỗi bước có trạng thái (đã chạy/bỏ qua/0 kết quả), số liệu, danh sách file. GET /artifact?path=<file thật> trả nội dung phân trang (offset/limit/q). Kiểm bảo mật: path=../../etc/passwd, path tuyệt đối, path chứa %2e%2e, symlink (tạo symlink trong thư mục scan trong container rồi đọc) → đều bị từ chối artifact_unavailable. Nội dung có chuỗi giống secret (ghi file thử có H1_TOKEN=abc123 / AKIA... vào thư mục scan) → bị che, reveal=true chỉ hiện khi gọi tường minh. /artifact/download trả file.
- T2-F Launch light không ack: launch depth light với automation_ack=false phải bị chặn hoặc cảnh báo đúng thiết kế (ghi lại hành vi thực tế, đối chiếu ACCEPTANCE.md). Với ack=true: audit.jsonl có bản ghi ack.
- T2-G Diff Passive→Light (R4 quan trọng nhất): một program mới raw 127.0.0.1. Chạy: Passive (scan A) → Light (scan B, bật http probe, tắt nmap/nuclei/active crawl, scan_timeout ≤300) → Light lần 2 (scan C, cùng config) .
  Ghi: GET /diff cho B và C, stats `baseline_scan_id`, `diff_compared_hosts`, số new/changed/gone. Kỳ vọng: B có changed>0 hoặc new>0 vì A không có http status còn B có (host 127.0.0.1 phải listen: dùng chính BBASM 18765); C so với B nên ≈0 và baseline_scan_id=B.id. Hủy giữa chừng một scan Light rồi chạy tiếp: baseline phải bỏ qua scan cancelled. Nếu B vẫn changed=0 dù http status khác → FINDING P1 kèm dump asset trước/sau (http_status, tech) của A, B.
- T2-H URL inventory: sau scan có URL (nếu 127.0.0.1 không sinh URL, dùng seed: SEED_DEMO=1 mock server ở T5 rồi gọi cùng endpoint): GET /api/programs/{slug}/urls (filter q, tag, host, verification, min_score, include_static, scan=latest|all, limit/offset, header X-Total-Count), /urls/summary (funnel, by_tag, top_shapes, hosts), /urls/export (.txt). Kỳ vọng: không hàng nào verification="live" cho URL lịch sử; URL ngoài scope không xuất hiện; funnel cộng khớp.
- T2-I Profiles: POST/PUT/DELETE/duplicate /api/profiles; PUT /api/programs/{slug}/default-profile; profile chỉ chứa recipe, KHÔNG chứa scope; resolve program mới dùng profile mặc định đã gán (GET /api/scans/{id}/config). Profile có field lạ → 422 (extra=forbid).
- T2-J Export: GET /export?mode=brief|filtered|full → mở ZIP, MANIFEST.json, so sánh: brief không có recon/, filtered không chứa dòng ngoài scope (thử bơm một dòng host ngoài scope vào file recon trong container rồi export), full có raw. Mặc định (không tham số) = filtered. AGENT_BRIEF.md < 12000 byte, có mục Policy và nhãn độ tin cậy (manual/api/public).
- T2-K Hunt command: GET /api/programs/{slug}/summary → hunt_command. Docker + BBASM_HOST_TARGETS='E:\code\...\targets' (một biến thể thử qua .env tạm) → lệnh dạng cd "E:\...\targets\slug" && claude với MỘT dấu \ mỗi separator, không JSON-escape đôi. Thử thêm đường dẫn có khoảng trắng và dấu nháy. Không đặt biến → hiện "targets/<slug>" + ghi chú.
- T2-L Health: GET /api/health có missing_by_depth, h1_api, runtime; httpx là binary Go đúng (không phải script Python).
- T2-M Cancel & cleanup: launch light, huỷ sau 3s, docker compose -p bbasm-v12 top → không còn nuclei/httpx/subfinder/katana/nmap/recon_engine.
- T2-N Persistence: snapshot SHA256 targets + bảng program/scan_run/schedule, docker compose restart, so lại (giống y hệt). Schedule: bật passive, đẩy next_run_at về quá khứ trong SQLite khi container dừng, start → scan scheduled xuất hiện; tắt schedule sau đó.
- T2-O Rò rỉ secret: grep log container + mọi audit.jsonl tìm H1_TOKEN, H1_USER, GITHUB_TOKEN, CHAOS_KEY → 0.

## T3 Migration DB v1→v2 trên BẢN SAO DB thật
- Sao chép (copy, KHÔNG move, không mở bản gốc để ghi) E:\code\bbasm\advance_asm-v11test\data\bbasm.db vào thư mục tạm riêng: ../v12-migrate/data/bbasm.db (+ -wal/-shm nếu có, chỉ copy khi stack v11 đã dừng hoặc dùng sqlite3 .backup).
- Trước: sqlite3 dump bảng đếm (program, scan_run, asset, url, finding, diff_event) + PRAGMA user_version/schema_version.
- Chạy backend với BBASM_DATA trỏ vào bản sao (docker compose riêng hoặc python -m backend.main port 18767, KHÔNG trùng stack chính). Kỳ vọng: tự migrate lên v2, tạo bbasm.db.bak-v1-<ts> (tối đa 3 bản), số hàng các bảng cũ giữ nguyên, GET /api/programs và /diff/assets/urls phân trang hoạt động trên dữ liệu 8.8k URL, ghi thời gian phản hồi.
- Mô phỏng lỗi: làm hỏng bản sao thứ hai (ví dụ khoá bảng/đặt file read-only giữa chừng hoặc dùng test TC-MIG như hướng dẫn trong test) và xác nhận rollback từ backup, DB không rơi vào nửa v2.
- Với dữ liệu thật scan #9–#12: dùng GET /api/programs/qa-vuihoc-v11/urls/summary trên bản sao để xem funnel/top_shapes; ghi lại số URL, số shape, tag counts (đây là bằng chứng chất lượng triage). KHÔNG chạy scan nào tới host thật.
- Diff trên dữ liệu thật: GET /api/programs/qa-vuihoc-v11/diff và stats của scan #12: ghi baseline_scan_id, diff_compared_hosts, new/changed/gone. (Scan #12 gốc ghi changed=0 trong khi #9 chưa có http status; xem v1.2 có giải thích/khắc phục không.) Không re-ingest được thì ghi rõ giới hạn.

## T4 Giao diện qua trình duyệt headless (Playwright, tự động; KHÔNG điều khiển màn hình thật)
- PYTHONPATH=. SCR=<thư mục tạm> SEED_DEMO=1 python review_tools/mock_h1_server.py (cổng 18766, mock H1 + dữ liệu demo-shop 2 scan), rồi SCR=<thư mục tạm> python review_tools/ui_screenshots.py → ảnh desktop 1366 và mobile 390 vào thư mục tạm (không commit).
- Bằng script Playwright: duyệt 10 route (#/, #/new, #/help, #/profiles, #/scan/<id>, #/scan/<id>/review, #/program/<slug> và 4 tab data/findings/history/guide + view urls/hosts/diff/brief/instructions): mỗi route ở 390px kiểm document.scrollWidth <= innerWidth; ở Review mobile, nút "Chạy" ở vị trí cố định (position:fixed, bottom trong viewport 390x800 mà không cuộn); không có console error; không request 4xx/5xx bất thường.
- Kiểm theo ngữ nghĩa (selector theo role/tên, không toạ độ): Review có công tắc từng bước và lý do khi bị tắt; đổi preset → plan đổi; lưu thành profile → xuất hiện ở #/profiles; Run hiện "Kết quả theo bước", mở file xem được và tìm kiếm trong file hoạt động; tab URL có phễu, lọc theo tag, nút tải .txt; Help có mục "Chức năng & kết quả"; trang H1 đưa handle dạng URL có ?type=team vẫn nhận; nhãn "CHƯA XÁC MINH" hiện cho dữ liệu H1 công khai.
- Hiệu năng (tự động): với bản sao DB thật (T3) đo thời gian mở tab URL và Assets, cuộn/phân trang trên >1000 hàng (ghi ms; flag nếu >2s tải trang đầu hoặc UI treo).
- Axe: chạy @axe-core/playwright (hoặc axe-core nạp qua page.add_script_tag) trên các route chính, ghi số violation theo mức serious/critical. Nếu không cài được, SKIP có lý do.

## T5 Chất lượng vận hành
- Tìm lỗi chung: console.error, unhandled rejection, response 500 trong log container sau toàn bộ T2/T4.
- WebSocket: reconnect khi restart container giữa lúc scan (ghi hành vi UI/Run page, không vá).
- Ghi thời gian: passive scan 127.0.0.1 hết bao lâu; light (probe only) bao lâu.

## Đầu ra
Tạo V12_HOST_RESULTS.md ở gốc worktree nhánh test/v12-host-results theo đúng khuôn V11_HOST_RESULTS.md: bảng (Mã | Lệnh/Hành động | PASS/FAIL/SKIP | Bằng chứng ngắn), tổng số PASS/FAIL/SKIP, mục Finding mới (P1–P3, tái hiện, tác động, hướng sửa — chỉ đề xuất), mục "Chưa chạy hoặc giới hạn bằng chứng", mục dọn tài nguyên (docker compose -p bbasm-v12 down; xoá image bbasm-v12-bbasm; xoá thư mục tạm; xác nhận bản gốc advance_asm-v11test/data/bbasm.db KHÔNG đổi bằng SHA256 trước/sau).
Kèm review_evidence/v12_diff_chain.json (số liệu T2-G: id scan, baseline_scan_id, new/changed/gone, mô tả http_status/tech trước-sau, không chứa raw URL/token) và review_evidence/v12_migration.json (đếm hàng trước/sau, tên file backup, thời gian).
Commit trên test/v12-host-results, push origin test/v12-host-results. KHÔNG push vào nhánh khác. Dừng lại và báo nếu bước nào cần quyền ngoài phạm vi trên.
```

---

# Việc người dùng tự test tay (Codex không làm; làm theo từng bước)

Mỗi mục: chuẩn bị → thao tác → kết quả mong đợi → ghi lại.

## M1. Diff với dữ liệu thật (quan trọng nhất)
- Chuẩn bị: program của bạn có quyền scan; mở `http://127.0.0.1:18765`. Dùng stack v1.2 (đừng dùng stack v11 cũ).
- Thao tác: tạo scan **Passive** (preset Passive) → chờ xong → tạo scan **Light** (rescan từ trang Program) với "Quét HTTP probe" bật, nmap/nuclei/active crawl tắt → chờ xong → vào Program → Lịch sử → Diff.
- Mong đợi: ở Diff có chữ "So với scan #<id của Passive>"; host đã có HTTP status/tech được liệt kê là "đã đổi". Nếu vẫn 0 mà bạn thấy host có status 200 ở tab Hosts → chụp màn hình Diff + Hosts + trang Run của hai scan và gửi lại.
- Ghi: số scan, số new/changed/gone, baseline hiển thị đúng không.

## M2. Dễ nhìn / dễ dùng
- Mở lần lượt: Tổng quan, Review, Run, Program (5 khu vực), Help, Profiles.
- Tự hỏi và ghi lại (có/không + ghi chú): (1) vào Review có hiểu ngay "bước nào chạy, bước nào tắt, vì sao"? (2) công tắc bước và giá trị (threads, timeout…) có đổi được và Review tóm tắt đúng không? (3) trang Run: mỗi bước cho biết làm gì, có chạm target không, kết quả ở đâu? bấm vào file xem được? (4) tab URL có tìm đúng URL bạn cần trong <30 giây? (5) chữ nào còn khó hiểu / thừa?

## M3. Nhập scope & H1
- Tab raw: dán scope thật của bạn (nhiều dạng: `*.a.com`, bullet, dòng có `#` ghi chú, dải IP, ô OUT riêng). Xem bảng xem trước: mỗi dòng có trạng thái; lỗi có chỉ ô + số dòng. Thử cố tình dán sai (`# OUTT`, `10.0.0.5/24`, `bad host!!`) → phải bị chặn, không có dòng "hợp lệ" ma.
- Tab HackerOne **không token** rồi **có token** (chỉ trên máy bạn, program cho phép; token đặt trong `.env` H1_USER/H1_TOKEN): so sánh phần Policy và nhãn tin cậy ("CHƯA XÁC MINH" khi chỉ có dữ liệu công khai). Sau khi launch, đọc lại policy gốc trên trang H1 và xác nhận bot/scanner được phép **trước khi** ack.

## M4. Mobile thật
- Mở `http://<IP máy>:18765` trên điện thoại (cùng mạng; đặt `BBASM_BIND=0.0.0.0` tạm thời và tắt sau khi xong — chỉ trong mạng tin cậy). Duyệt Review, Run, Program, URL: không cuộn ngang, nút Launch luôn thấy, bấm được bằng ngón cái, chữ đọc được ngoài sáng.

## M5. Hunt command
- Program → Hướng dẫn: bấm "Sao chép lệnh hunt", dán vào terminal của bạn: phải `cd` đúng vào thư mục target rồi mở Claude. Đặt `BBASM_HOST_TARGETS` trong `.env` nếu dùng Docker, thử đường dẫn có khoảng trắng.

## M6. Migration trên DB thật
- Dừng stack cũ. **Copy** `data/bbasm.db` sang chỗ khác làm bản dự phòng riêng (ngoài việc app tự backup). Chạy stack v1.2 trên dữ liệu thật; kiểm program/scan cũ còn đủ, có file `bbasm.db.bak-v1-<thời gian>`. Nếu mọi thứ ổn, giữ bản dự phòng 1 tuần rồi xoá.

## M7. Việc Codex không đo được
- Windows native chỉ chạy UI/API; recon thật cần Docker/WSL2 (đã là thiết kế).
- Scheduler tick thật qua một ngày, Lighthouse/axe trên màn hình thật, cảm nhận hiệu năng >1000 hàng — ghi cảm nhận vào phần M2.
