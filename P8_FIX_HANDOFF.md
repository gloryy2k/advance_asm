# P8 FIX HANDOFF — sửa toàn bộ finding của P3_P8_REVIEW_RESULTS.md

> **Đối tượng:** Codex. **Nhánh làm việc:** `build/p8-acceptance` (submodule `vendor/claude-bug-bounty` branch `build/bbasm-depth-toggles`, pin hiện tại `7acb66a`).
> **Nguồn:** đọc `P3_P8_REVIEW_RESULTS.md` (kết quả nghiệm thu thật trên Kali) + `BUILD_SPEC.md`. Fix theo thứ tự ưu tiên. Mỗi fix kèm test regression.
> **Ràng buộc (giữ nguyên):** reuse framework qua subprocess; agent bridge chỉ sinh folder; path qua `BBASM_BBROOT/BBASM_TOOLS_SUBDIR`; scope safety + audit outbound; giữ LF; **không scan target thật khi code**; test cần tool/mạng/Docker thật đánh dấu `@pytest.mark.integration`.

---

## 🔴 FIX-1 (HIGH, CHẶN MERGE) — cancel/timeout phải giết CẢ cây tiến trình, không chỉ 1 process group

**Vấn đề:** `backend/jobs/runner.py::stop_process_group` dùng `os.killpg(process.pid, …)` chỉ giết process group của bash session. Nhưng `recon_engine.sh` chạy tool qua GNU `timeout` (`timeout "$NUC_TIMEOUT" nuclei …` dòng ~696; `timeout 300 katana` ~446; `timeout 300 amass` ~316; gau historical) — `timeout` đặt tool vào **process group RIÊNG**. Hệ quả: khi cancel/timeout, nuclei/katana/amass **không bị giết** và **tiếp tục active-scan target** (đã tái hiện: nuclei sống >25s sau cancel, PGID ≠ pid bash). Vi phạm §2.6/§18.

**Yêu cầu fix (runner-side, authoritative):** teardown phải giết **toàn bộ hậu duệ** của tiến trình bash (tất cả đều chung session do `start_new_session=True`).

Cách khuyến nghị (thêm `psutil` vào `requirements.txt`):
```python
# stop_process_group(process, grace=...):
import psutil
try:
    root = psutil.Process(process.pid)
    procs = root.children(recursive=True) + [root]
except psutil.NoSuchProcess:
    procs = []
for p in procs:
    try: p.terminate()
    except psutil.NoSuchProcess: pass
_, alive = psutil.wait_procs(procs, timeout=grace)
for p in alive:
    try: p.kill()
    except psutil.NoSuchProcess: pass
# giữ thêm os.killpg(process.pid, SIGKILL) như belt-and-suspenders (bọc ProcessLookupError)
await process.wait()
```
Nếu KHÔNG muốn thêm dep: duyệt `/proc/*/stat` lấy các pid có **session id == process.pid** (Linux) rồi SIGTERM→SIGKILL. Nêu rõ giới hạn non-Linux.
(Tùy chọn defense-in-depth phía vendor: đổi các `timeout …` thành `timeout --foreground …` để tool ở cùng group — nhưng **không thay thế** fix runner-side.)

**Test regression (bắt buộc, `@pytest.mark.integration` vì cần process thật):**
- Spawn một command mô phỏng recon: bash chạy `setsid`/`timeout` bọc một child `sleep 300` để child nằm ở **process group khác** pid bash. Cancel/timeout → assert **child sleep đã chết** (không chỉ bash). Đây là ca `TC-RUN-2` còn thiếu — sửa luôn để nó phủ grandchild ở group tách.
- Unit (không cần tool thật): mock `psutil`/tree để verify `stop_process_group` gọi terminate+kill trên toàn bộ hậu duệ.

**Acceptance:** trên Kali, scan light có nuclei → cancel → `pgrep nuclei` rỗng trong vài giây; hard-timeout cũng không để lại tiến trình.

---

## 🟠 FIX-2 (MED) — DB reset nhưng `targets/` còn → scan_id đụng dir cũ → fail

**Vấn đề:** `backend/jobs/recon_orch.py::build` có:
```python
if root.exists():
    raise ValueError("Scan output already exists; create a new scan instead of reusing stale output")
```
Khi `data/bbasm.db` bị reset (counter scan_id về 1) nhưng `targets/<slug>/recon/scans/1/` cũ còn → launch fail ngay. DB và targets ở 2 volume có thể lệch (restore/copy/reset).

**Yêu cầu fix:** phân biệt **reuse thật trong cùng DB** (lỗi đúng) với **orphan từ DB khác** (không nên fail cứng). Cách khuyến nghị:
- Khi `root.exists()`: kiểm trong DB hiện tại có `scan_run` nào khác đang "sở hữu" dir này không (vd có scan_run cùng id ở trạng thái running/done ghi dir đó). Nếu KHÔNG (orphan) → **di chuyển** dir sang `recon/scans/.orphan-<scan_id>-<ts>/` (hoặc xoá) + `plan.warnings.append(...)`, rồi tạo mới. Nếu CÓ (đang chạy/đụng thật) → giữ raise.
- HOẶC namespace output bằng token duy nhất theo DB-instance (vd lưu một `instance_id` trong `schema_meta` lúc tạo DB, đưa vào đường dẫn): `recon/scans/<instance_id>/<scan_id>/`. Chọn 1 hướng, ghi lý do vào NOTES.

**Test:** tạo stale dir `recon/scans/1/` thủ công + DB mới không có scan tương ứng → build() không raise, dir cũ được dời/dọn, scan chạy; còn khi có scan đang chạy chiếm dir → vẫn raise.

---

## 🟡 FIX-3 (LOW) — diff ghi CHANGED khi host 200 → offline

**Vấn đề:** `backend/asm/diff_engine.py::apply` chỉ so status khi observation mới **có** `status_code`. Host từng 200 nay offline (không probe-live) → không CHANGED → "host offline" vô hình.

**Yêu cầu fix (chỉ khi scan `complete` và đã probe-live, không áp cho passive):** nếu host trong baseline `active` có `status_code` nhưng observation lần này đã được probe mà **không còn live** (host vẫn được recon nhưng httpx không thấy) → ghi `changed` với `{"status_code": {"before": X, "after": null}}` (hoặc field `reachable: false`). Tránh nhiễu: chỉ khi depth != passive và host thực sự nằm trong tập đã probe. Nếu phân biệt "không probe" vs "probe nhưng offline" khó từ dữ liệu hiện có, ghi rõ giả định vào NOTES và chọn hành vi bảo thủ.

**Test:** baseline host status 200 → scan complete không thấy live → 1 diff_event `changed` (status→null). Passive → không sinh event giả.

---

## 🟡 FIX-4 (LOW, doc) — TC-RK-1 lệch công thức §12.3

`BUILD_SPEC.md §16 TC-RK-1` kỳ vọng `score ≥ 7`, nhưng §12.3 cho `api+graphql+200+fresh = 6.0`. Code đúng. **Sửa spec**: đổi kỳ vọng TC-RK-1 thành `≥ 6` (và cập nhật mô tả cho khớp: api(2.5)+fresh(1.5)+tech_risk(1.5)+status_200(0.5)=6.0; auth chỉ cộng nếu host/title có login/sso/oauth/admin/account). Không chỉnh trọng số để ép 7 trừ khi người dùng yêu cầu.

---

## Mục CHƯA chạy được ở sandbox — để lại cho người dùng (ghi rõ, KHÔNG đánh dấu hoàn tất)

Codex không cần (và thường không thể) chạy các mục môi trường-đặc thù; chỉ đảm bảo code/test đúng để người dùng chạy:
- **Docker build/compose** + `BBASM_DOCKER_TESTS=1 pytest test_docker_integration.py` — host review thiếu compose plugin. Rà lại Dockerfile/entrypoint/compose cho khớp các ENV/toggle mới (gồm `psutil` nếu thêm).
- **Browser E2E** (`test_browser_integration.py`) — cần Playwright + domain được phép.
- **Windows/WSL2** — chưa kiểm; `.gitattributes` đã ép LF. Nếu FIX-1 dùng `/proc` session-walk thì phải guard non-Linux (Windows không có `/proc`), ưu tiên `psutil` để portable.
- **H1 program thật**, **CI GitHub Actions** của commit bàn giao.

---

## Hoàn tất & bàn giao
1. Fix FIX-1..FIX-4 trên `build/p8-acceptance`; FIX-1 nếu chạm vendor thì commit vào `build/bbasm-depth-toggles`, push, bump submodule pointer.
2. Thêm/sửa test cho mỗi fix; chạy `pytest -m "not integration"` (phải xanh) + đánh dấu integration cho test cần process thật.
3. Cập nhật `requirements.txt` (nếu thêm `psutil`), `NOTES.md` (ghi quyết định FIX-2/FIX-3), và `P3_P8_REVIEW_RESULTS.md`/ACCEPTANCE nếu cần.
4. Mô tả PR: fix nào, cơ chế, kết quả test, và nhắc người dùng chạy các mục môi trường còn lại.
5. Gặp quyết định ngoài spec → KHÔNG tự đoán; chọn default an toàn + reversible, ghi vào NOTES để review.

**Definition of done:** cancel/timeout không để lại tiến trình tool (FIX-1 có test); DB reset + stale targets không làm scan fail (FIX-2); diff phản ánh host offline (FIX-3); spec TC-RK-1 khớp công thức (FIX-4); `pytest -m "not integration"` xanh; không vi phạm ràng buộc; LF giữ nguyên.
