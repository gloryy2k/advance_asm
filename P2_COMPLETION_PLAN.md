# P2 COMPLETION PLAN — hướng khắc phục để hoàn tất P2

> **Đối tượng đọc:** agent triển khai (Codex). **Hành động:** làm theo các task bên dưới, commit & push lên branch `build/p2-runner` (+ submodule branch `build/bbasm-depth-toggles` nếu cần, rồi bump pointer).
> **Nguồn chuẩn vẫn là `BUILD_SPEC.md`.** File này CHỐT một quyết định đang treo (egress) và liệt kê task cụ thể. Mọi thứ khác trong spec giữ nguyên.
> **Trạng thái sau review (người dùng đã duyệt hướng này):** code P0/P1/P2 chất lượng tốt, bám spec. P2 chỉ thiếu phần cho recon chạy thật, do `ClosedEgress` tự chặn. Không có lỗi kiến trúc nào khác cần đập đi làm lại.

---

## 0. QUYẾT ĐỊNH ĐÃ CHỐT về egress (đọc kỹ trước khi làm)

Đề xuất trong `P2_EGRESS_REVIEW.md` (xây OS-level network isolation + per-scan TLS egress proxy chặn/audit từng request của tool) **KHÔNG được chọn**. Lý do:

- Vượt spec: §2.3/§8.4 định nghĩa scope-safety = **lọc seed in-scope + scope_gate + audit**, KHÔNG yêu cầu chặn/giải mã outbound nội bộ của tool.
- Mâu thuẫn §2 (reuse, keep simple) và §19 (non-goals: không viết lại recon, giữ tối giản). MITM/network-jail là một subsystem mới.
- Chặn chính chức năng cốt lõi (hiện mọi launch → `failed`), tệ hơn ý định spec.
- Không đúng thực tế: subfinder/httpx/nuclei/katana là đúng bộ tool chạy trực tiếp khi hunt; outbound phụ (redirect/CDN/interactsh) là bình thường trong ngành.

**Hướng chốt:** mở recon thật bằng **audited-spawn** (ghi audit allow rồi spawn — đúng model spec), cộng vài **toggle default-safe tương xứng** để giảm outbound-ra-ngoài-seed. Ý tưởng egress-proxy chỉ giữ làm **hardening TÙY CHỌN tương lai** ở lớp Docker network (§13/§24), KHÔNG phải cổng P2.

→ Hành động với `P2_EGRESS_REVIEW.md`: hạ cấp nội dung thành "Optional future hardening (không phải P2 requirement)". Không xoá lịch sử phân tích.

---

## RÀNG BUỘC (giữ nguyên, không vi phạm)
- Web dashboard FastAPI + WebSocket + React + SQLite.
- Luồng resolve → review → launch; depth passive/light/strong.
- Reuse framework qua subprocess, KHÔNG viết lại recon.
- Agent bridge chỉ sinh folder, KHÔNG spawn agent hunt.
- KHÔNG đổi fork/layout submodule sang upstream mới; giữ layout `tools/`.
- Đường dẫn framework qua `BBASM_BBROOT`/`BBASM_TOOLS_SUBDIR`.
- Scope safety + audit outbound bắt buộc; giữ LF.
- **KHÔNG scan target thật trong lúc code.** Mọi test cần tool/mạng thật đánh dấu `@pytest.mark.integration`, để người dùng chạy.

---

## TASK

### T1 — Mở live recon bằng `AuditedEgress` (thay mặc định `ClosedEgress`)
**File:** `backend/jobs/recon_orch.py`, `backend/jobs/runner.py`.

1. Thêm class `AuditedEgress` cạnh `ClosedEgress` trong `recon_orch.py`:
```python
class AuditedEgress:
    """Model scope-safety của spec: seed/discovery đã được scope_gate lọc;
    ghi audit 'allow' trước khi spawn rồi cho chạy. KHÔNG phải network isolation."""
    def check(self, plan, command):
        audit(plan.audit_path, command.category, "allow", "audited_spawn",
              scan_id=plan.scan_id, resource=command.resource)
```
2. `runner.py`: đổi default `self.egress = egress or ClosedEgress()` → `AuditedEgress()`.
3. Thêm safety-switch ENV **`BBASM_RECON_DISABLED`** (default `0`): nếu `1` thì dùng `ClosedEgress` (giữ khả năng tắt khẩn cấp). Giữ `ClosedEgress` cho test.
4. Giữ nguyên: seed in-scope đã lọc ở `ReconOrchestrator.build`, discovery lọc qua `gate.in_scope` trong `discovered_commands` — không đổi.

**Acceptance T1:** launch một scan (mock process factory, unit) → đi `queued → running → done`, audit.jsonl có bản ghi `allow/audited_spawn`. Với `BBASM_RECON_DISABLED=1` → vẫn `failed` (deny).

### T2 — Toggle default-safe giảm outbound-ra-ngoài-seed (tương xứng, không subsystem)
Thêm các toggle, **mặc định AN TOÀN (tắt hành vi chạm bên thứ 3)**, cho phép user bật lại qua config/ENV. **Đọc file thật trước khi chèn** (số dòng có thể đổi).

**Trong submodule `vendor/claude-bug-bounty/tools/recon_engine.sh`** (commit vào branch `build/bbasm-depth-toggles`, push, rồi bump pointer ở parent):
- `nuclei`: nếu `BBASM_NO_INTERACTSH=1` (default 1) → thêm `-no-interactsh` (tắt OOB callback ra interactsh).
- `httpx`: nếu `BBASM_NO_REDIRECT=1` (default 1) → KHÔNG follow redirect (không để permitted URL redirect sang host OOS). Nếu đang có cờ follow-redirect thì bỏ khi toggle bật.
- `katana`: giới hạn crawl trong host in-scope (vd `-crawl-scope`/field-scope tương ứng tool), khi `BBASM_SKIP_ACTIVE_CRAWL=0`.

**Trong `recon_orch.recon_env`:** set các ENV trên theo config (map từ `scan_config`; mặc định an toàn). Thêm field tương ứng vào `ScanConfig` + `scan_config` table nếu muốn user chỉnh ở REVIEW (hoặc giữ ENV-only, default-safe — tối thiểu là default-safe).

**trufflehog (verify live key) nằm trong `secrets_hunter.sh`, KHÔNG phải recon_engine.sh:**
- Đọc `secrets_hunter.sh`. Nếu truyền được cờ tắt verify (vd trufflehog `--no-verification`) qua argv/ENV mà KHÔNG sửa submodule → làm ở `recon_orch._source` (thêm cờ), default **tắt verify**.
- Nếu buộc phải sửa submodule → mở rộng patch **tối thiểu** trong cùng branch `build/bbasm-depth-toggles` (thêm 1 toggle `BBASM_NO_VERIFY=1` default), ghi rõ ở NOTES rằng patch nay chạm thêm `secrets_hunter.sh`. Cho user bật verify khi họ chủ động.

**Acceptance T2:** unit test (mock) xác nhận khi default, argv/env tool chứa `-no-interactsh`, httpx không follow redirect, source_code không verify; khi user bật → ngược lại. `bash -n` pass cho mọi script sửa.

### T3 — Dọn 2 quirk framework đã ghi nhận
- **List-mode historical collection dùng basename:** đảm bảo file list đầu vào đặt tên theo `scan_id`/bước (đã nằm dưới `recon/scans/<scan_id>/.inputs`), tránh lẫn dữ liệu historical giữa các scan. Nếu recon_engine dùng basename list làm khóa, đặt tên list ổn định-duy-nhất per scan.
- **Concurrency cố định ở vài helper phase:** chấp nhận cho P2; ghi known-limitation vào NOTES (BB_THREADS/BB_RATE_LIMIT chính đã được tôn trọng). Không cần sửa nếu không rẻ.

### T4 — Cập nhật test
- Sửa test "default egress denial" → **"default egress audited-allow"** (default giờ cho chạy). Thêm test `BBASM_RECON_DISABLED=1` → deny.
- Thêm unit cho T2 (toggle default-safe có mặt trong argv/env).
- Giữ các integration-marked cho tool/mạng thật (TC-RO-6, process-tree, scan thật) — KHÔNG chạy ở đây.
- Chạy `pytest -m "not integration"` → phải xanh. Ghi số liệu vào NOTES.

### T5 — Tài liệu & dọn
- `P2_EGRESS_REVIEW.md`: hạ cấp thành "Optional future hardening (Docker network layer, §13/§24) — KHÔNG phải P2 requirement". Nêu rõ P2 hoàn tất bằng audited-spawn + toggle default-safe.
- `NOTES.md`: ghi mục "P2 completion": AuditedEgress, toggle default-safe, quirk T3, kết quả test.
- (Tuỳ chọn) đề xuất sửa `BUILD_SPEC.md §3.3`: interface thật là `ScopeChecker.is_in_scope()` chứ không phải `in_scope()`. Nếu không tự sửa spec, ghi vào NOTES để người dùng sửa.

### T6 — Validation hoàn tất (NGƯỜI DÙNG chạy, không làm khi code)
Trên Kali/Docker, target **do người dùng tự cho phép**:
- `pytest -m integration` (TC-RO-6 tác động toggle thật, process-tree teardown).
- 1 scan `light` in-scope → xác nhận `done`, `audit.jsonl` có `allow/audited_spawn`, output dưới `recon/scans/<scan_id>/`.
Ghi rõ trong PR: đã/ chưa chạy phần này.

### T7 — Merge
Lineage tuyến tính `main→p0→p1→p2`. Sau khi T1–T5 xanh và T6 được người dùng xác nhận: chuẩn bị PR `build/p2-runner → main` (fast-forward) kèm bump submodule pointer trong cùng PR. **Chưa tự merge** nếu người dùng chưa duyệt.

---

## DEFINITION OF DONE (P2)
- [ ] Launch (mock) chạy tới `done`; audit ghi `allow/audited_spawn`. `BBASM_RECON_DISABLED=1` → deny.
- [ ] Toggle default-safe: nuclei `-no-interactsh`, httpx no-redirect, katana in-scope crawl, source_code no-verify — mặc định bật; user tắt được.
- [ ] Submodule chỉ thay đổi tối thiểu, đúng branch `build/bbasm-depth-toggles`, pointer bump ở parent; giữ layout `tools/`.
- [ ] `pytest -m "not integration"` xanh; integration vẫn được đánh dấu, không chạy khi code.
- [ ] `P2_EGRESS_REVIEW.md` hạ cấp; `NOTES.md` cập nhật; (spec §3.3 được nêu).
- [ ] Không có path hardcode; LF giữ nguyên; không vi phạm RÀNG BUỘC.

## KHI GẶP QUYẾT ĐỊNH NGOÀI PHẠM VI
Không tự đoán. Chọn default an toàn + reversible, ghi rõ câu hỏi/giả định vào `NOTES.md` và mô tả PR để người dùng review.
