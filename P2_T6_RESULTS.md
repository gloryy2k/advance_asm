# P2 — T6 validation results (Kali/Linux, real tools)

## Chốt P2 — người dùng xác nhận sau fix

Commit 695ef2d, submodule 7acb66a: 124 unit + 3 integration tests pass;
`bash -n` OK. Scan light 127.0.0.1 done trong khoảng 7 giây (trước 4m39s),
không có process gau hoặc urls/gau.txt; audit đủ scope_resolved → audited_spawn
→ scan_finished. F1/F2 hoàn tất. Health gau/katana/dnsx đều true.
Đính chính: katana/dnsx vốn đã có trong ~/go/bin, không phải thiếu tool.
Các mục chờ chạy lại bên dưới là lịch sử trước xác nhận này. Nhánh domain live
→ nuclei → findings chưa được xác nhận bằng scan thật.

> **Người chạy:** validation trên máy Kali thật (không phải báo cáo suông). **Ngày:** 2026-10-12.
> **Đối tượng đọc:** Codex — đọc rồi FIX 2 finding ở cuối, commit lên `build/p2-runner` (+ submodule `build/bbasm-depth-toggles`, bump pointer).
> **Commit được test:** `build/p2-runner @5efda86` ("enable audited recon with safe tool defaults"), submodule `@9cb6954`.

## Môi trường
- venv Python 3.14.7, cài đúng `requirements.txt`.
- Tool có: subfinder, httpx, nuclei, amass, ffuf, nmap, git (và `gau` trong `~/go/bin`). Thiếu: dnsx, katana (fail-soft skip, OK).
- Target: **`127.0.0.1`** (máy local, được phép tuyệt đối, không chạm bên thứ ba) — vì không có target ngoài được chỉ định.

## Kết quả — 3 tiêu chí T6 ĐẠT ✅

**Bước 2 — `pytest -m integration`:** `3 passed, 110 deselected`
- `test_real_offline_aggregator_adapter`, `test_tc_ro_6_passive_toggles_skip_active_commands`, `test_tc_run_2_real_child_process_group_cleanup`. Không scan ngoài.

**Bước 3 — resolve → launch → done** (raw `127.0.0.1`, depth light):
- `POST /api/scope/resolve` → `scan_id=1`, slug `127.0.0.1`, draft config light ✅
- `POST /api/scans/1/launch` → chạy tool thật → `status=done` sau ~4m39s ✅
- stats: `observed:1, subs:1, live:0, urls:0, findings:0` (127.0.0.1 không mở 80/443 → không live → nuclei bỏ qua, hợp lý).

**Bước 4 — kiểm tra:**
| Tiêu chí | Kết quả |
|---|---|
| Scan `done` | ✅ |
| `audit.jsonl` có `allow/audited_spawn` | ✅ `{"host":"web","decision":"allow","rule":"audited_spawn","scan_id":1,"resource":".../.inputs/1/hosts-0.txt"}` + `allow 127.0.0.1` + `done/scan_finished` |
| Output `recon/scans/<id>/` | ✅ `recon/scans/1/0/{live/httpx_full.txt, subdomains/all.txt, urls/gau.txt, takeover_candidates.txt}`, `.inputs/1/hosts-0.txt` |

→ **AuditedEgress (T1) chạy đúng**: audit allow → spawn → done. Scope gate + output isolation theo `scan_id` đúng. Depth-light toggle (skip_nmap, no httpx-skip, nuclei low,medium) áp đúng.

---

## 2 FINDING CẦN FIX (không chặn, nhưng phải xử lý)

### F1 — `gau` (historical URL collection) treo/chậm + outbound không-gated cho IP/CIDR  [ưu tiên cao]
**Hiện tượng:** ~4m39s của scan gần như toàn bộ là `gau` query các kho lịch sử **bên ngoài** (web.archive.org / otx / commoncrawl) cho `127.0.0.1`. Với một IP, historical URL là vô nghĩa (luôn rỗng) nhưng vẫn tốn nhiều phút. Đây cũng là **outbound tới bên thứ ba** mà model audited-spawn chỉ ghi lệnh recon, không ràng buộc — đúng quirk `NOTES.md` đã cờ ("list-mode historical collection dùng basename").

**Tác động:** mỗi scan IP/CIDR lãng phí nhiều phút; một tool mạng-chậm có thể kéo dài tới hard timeout; outbound non-target không được giới hạn.

**Fix đề xuất (nhất quán cách toggle hiện có, sửa trong submodule `recon_engine.sh` + map ở `recon_orch.recon_env`):**
1. Thêm toggle `BBASM_SKIP_HISTORICAL` (default **bật** cho category `ip`/`cidr`; cho web/wildcard giữ gau nhưng vẫn nên bound) → bỏ bước gau/waybackurls khi target không phải domain.
2. Bound `gau` bằng `timeout <giây>` (vd theo `BB_RATE_LIMIT`/một ENV `BBASM_HISTORICAL_TIMEOUT`, default ~60s) để không bao giờ treo cả scan.
3. (Tùy chọn) thêm `--providers`/`--timeout` của gau nếu bản gau hỗ trợ, để giới hạn provider.
4. Unit test: depth light + category ip → command KHÔNG có bước historical (hoặc có timeout wrapper); category web → có, kèm timeout.

### F2 — `/api/health` báo sai tool khả dụng (PATH không khớp recon_engine)  [trung bình]
**Hiện tượng:** health báo `gau/katana/dnsx = false` vì nó kiểm PATH **không gồm `~/go/bin`**, trong khi `recon_engine.sh` export `PATH="$HOME/go/bin:..."` và **thực sự dùng `gau`** (bằng chứng: gau đã chạy trong scan trên). Dashboard đang under-report tool đang có.

**Fix đề xuất:** health resolve tool theo cùng PATH mà recon_engine dùng — gồm `~/go/bin` (và các path recon_engine prepend). Có thể export cùng PATH trước khi `shutil.which`, hoặc kiểm trực tiếp trong các thư mục đó. Unit test: giả lập binary trong `~/go/bin` → health báo `true`.

---

## Ghi chú
- `dnsx`/`katana` thiếu thật trên máy test → DNS/active-crawl bị skip (fail-soft đúng), không phải lỗi.
- Không scan target thật của bên thứ ba trong quá trình validate. Cần chạy lại với một domain in-scope thật (có live host) để xác nhận nhánh httpx-live → nuclei → findings; nhưng pipeline end-to-end đã được chứng minh.
- Sau khi fix F1/F2: chạy lại `pytest -m "not integration"` + `pytest -m integration`, và 1 scan `light` để xác nhận thời gian giảm và health đúng.

## Follow-up F1/F2 — code đã sửa, chưa đo lại trên Kali

- IP/CIDR không query historical; list hỗn hợp lọc IP trước khi gọi provider.
- Domain dùng budget 60 giây mặc định (`BBASM_HISTORICAL_TIMEOUT`), gau không
  retry vô hạn; Wayback dùng thời gian còn lại của cùng budget. Có thể tắt toàn
  bộ bằng `BBASM_SKIP_HISTORICAL=1`.
- Health/runner cùng effective PATH, gồm `~/go/bin` và các thư mục POSIX mà
  recon_engine prepend. Unit kiểm tra binary giả trong Go bin được health nhận ra.
- Post-fix unit: **124 passed, 3 deselected**; `bash -n` đạt.
- **Chưa chạy lại integration/scan light:** máy sửa code là Windows, thiếu recon
  tools, chỉ có distro WSL docker-desktop và daemon Docker không chạy. Số ~4m39s
  ở trên vẫn là kết quả trước sửa. Chưa có số đo thời gian sau sửa.
- Trên Kali: pull `build/p2-runner`, `git submodule update --init --recursive`,
  chạy lại hai nhóm pytest rồi resolve một scan mới `127.0.0.1`, depth light.
  Ghi thời gian, status, audit, log "Historical collection skipped (BBASM)" và
  `/api/health` (gau phải true khi binary executable nằm trong `~/go/bin`).
