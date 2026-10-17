# Bảng công việc Claude Local ↔ Codex QA

Nguồn sự thật duy nhất về task nào đang mở, ai cầm, base commit nào, trạng thái gì. Chỉ Claude ghi vào file này
(sống trên nhánh code `claude/upbeat-thompson-b7bb23`). Codex không commit vào nhánh này — Codex chỉ tạo nhánh
`test/vNNN-host-audit` mới để nộp báo cáo QA, không bao giờ ghi đè nhánh cũ, không merge.

**Quy tắc bàn giao đầy đủ**: xem cuối file. Không agent nào tự đổi trạng thái của task mình không sở hữu.

**Nhắc Codex (2026-10-18):** `codex/scan-output-selector`@97ab94f là Codex tự viết feature (bộ chọn kết quả theo lần scan ở Program page), không phải task nào được giao trong bảng này — lệch "Quy tắc bàn giao" (Codex chỉ QA task `READY_FOR_QA`, không sửa/viết code sản phẩm). Lần này Claude đã review kỹ, vá 1 lỗ hổng nhỏ rồi merge (xem hàng lịch sử dưới), nhưng **từ nay Codex chỉ QA theo bảng này, không tự đề xuất/viết feature mới** — có ý tưởng thì ghi vào `BACKLOG.md` hoặc báo người dùng, không tự code.

## Trạng thái: `OPEN` (chưa ai làm) · `IN_PROGRESS` · `READY_FOR_QA` · `PASS` · `FAIL` (kèm lý do) · `DONE` · `BLOCKED` (chờ quyết định D#)

| ID | Ưu tiên | Owner | Trạng thái | base_commit | result_commit | Tóm tắt |
| --- | --- | --- | --- | --- | --- | --- |
Không còn task nào `OPEN`/`READY_FOR_QA`. Mọi việc còn lại trong `BACKLOG.md` chờ quyết định D2–D4 ở dưới.

## Việc đã đóng (lịch sử, không mở lại — sự cố tái phát ra ID mới)

| ID | Kết quả | Commit | Ghi chú |
| --- | --- | --- | --- |
| Chọn kết quả theo lần scan (Program page) | **Merged sau review Claude** (Codex tự viết, ngoài `COORD_TASKS.md` — xem nhắc nhở trên) | `97ab94f` (Codex) + merge + `58c5c3f` (vá `/diff`) | Logic/test đúng, 477 backend + 95 Vitest passed. 1 lỗ hổng nhỏ tìm thấy và vá: `/diff` không validate `scan_id` thuộc program/không phải draft như các bộ chọn khác — không rò dữ liệu thật, chỉ âm thầm trả rỗng thay vì báo lỗi. Xem NOTES.md v1.6.9. |
| NUC-6 — bỏ giới hạn 50/200 URL/lượt nuclei (D1) | **PASS** (QA Codex `test/v168-host-audit`@05e0692) | `41984f8` (BBASM) + `5a329e0`/`ccae299` (submodule) | 300/300 URL không còn cắt ở 200; `BBASM_NUCLEI_TIMEOUT` override đúng; ô Review đúng. 1 finding P2 (log "no findings" sai khi timeout) đã sửa ngay, xem NOTES v1.6.8. |
| (v1.6.1) Repair idempotency + test cô lập PATH | PASS (QA Codex `test/v161-host-audit`@6b9efe6, mã C1/C2) | `1e26cfe` | Xem NOTES.md v1.6.1. |
| NUC-5 — nuclei "tự chọn theo công nghệ" (`-as`) | **PASS vòng 2** (QA Codex `test/v167-host-audit`@ccbdca7, sửa P1/P2/P3 của `test/v166-host-audit`@db4442a) | `4102e75` | Nuclei thật thoát 0, finding thật trên localhost; `templates_loaded.txt` sạch (0 dòng JSON); Run nói đúng "không đáng tin" khi `templates:0` mâu thuẫn. |
| (v1.6.1) Nuclei coverage.json + stats-json | PASS (QA Codex, mã C4-C7) | `7428043`, `f20a636` | Xem NOTES.md v1.6.1. Phát sinh C8, C9 → NUC-1, NUC-2. |
| NUC-1 — coverage.json hỏng khi nuclei lỗi | **PASS** (QA Codex `test/v162-host-audit`@03c1f6b) | `d65c4f5` (BBASM) + `6638e72` (submodule, sau khi vá thêm log "[DONE] nuclei: no findings" sai mà Codex phát hiện) | Codex: nuclei thoát mã 1, `coverage.json` parse được, `failed=true`, Run hiện đúng "LỖI: nuclei không chạy được", không hiện `n/a`/sentinel. |
| NUC-2 — giới hạn sai khi gộp quick/full | **PASS** (QA Codex `test/v162-host-audit`@03c1f6b) | `d65c4f5` | Codex: gộp quick (50/60) + full (2/2) → `limits=[50,200]`, detail "mỗi lượt có giới hạn riêng: 50, 200 URL", không còn câu sai. |
| DOC-1 | DONE (không cần QA) | `d65c4f5` | `NOTES.md` +v1.6.1/v1.6.2, `BACKLOG.md` +mục "Độ phủ nuclei", `CLOUD_TO_LOCAL_HANDOFF.md` ghi chú lỗi thời. |
| NUC-3 — đo `nuclei/stats.jsonl` phình bao nhiêu | **PASS** (QA Codex `test/v163-host-audit`@6452c63) | d65c4f5 (đo, không sửa) | 321,79s thật: 66 dòng/11.794 byte. Ngoại suy 1800s ≈ 369 dòng/~64,4 KiB — không phình bất thường. |
| NUC-4 — scan Strong qua orchestration thật | **PASS** (QA Codex `test/v163-host-audit`@6452c63) | d65c4f5 (đo, không sửa) | `JobRunner`/`ReconOrchestrator` thật, main+deep đều tự tạo `coverage.json`; `/api/scans/{id}/phases` gộp đúng 2/2 URL, 2 request, `failed=false`. |
| ENG-1 — `open_ports.txt` mất cổng | **PASS** (QA Codex `test/v164-host-audit`@3379dfd) | `bb17169`/`bfd61ba` | `grep -oE` giữ đủ mọi cổng/dòng, log `Open ports: 4` đúng. |
| UX-1 — bảng Cổng/Dịch vụ, Đường dẫn dò được | **PASS** (vòng 2, QA Codex `test/v165-host-audit`@74aacf5, sau khi sửa 2 finding FAIL của `test/v164-host-audit`@3379dfd) | `976e1c3` | `scan=<id>` được forward đúng, hiện "Đang xem scan #N"; draft có output mồ côi trả `found=false`. Không finding mới. |

## Quyết định sản phẩm đang chờ bạn (không lên task thi công tới khi chốt)

- **D1 — ĐÃ CHỐT (2026-10-17):** bỏ hẳn giới hạn 50/200 URL/lượt của nuclei; mọi URL sống đều được đưa vào, an toàn thời gian dựa vào ngân sách giai đoạn đã có. Xem NOTES v1.6.7, `BACKLOG.md` mục "Độ phủ nuclei".
- **D2** — Cưỡng chế giới hạn thư mục repo khi quét secrets (trufflehog `--include-paths`).
- **D3** — "Probe tiếp" phần chưa quét (`stats.unprobed_hosts`). Không còn phụ thuộc D1 (D1 đã chọn hướng không cần "quét tiếp").
- **D4** — Adapter riêng mobile/source-code/other.

Chi tiết phương án + khuyến nghị: xem phần "Quyết định cần bạn chốt" trong kế hoạch đã gửi (lưu lại trong lịch sử trò chuyện; nếu cần chép lại thành file, báo Claude).

---

## Quy tắc bàn giao (dán nguyên văn cho cả hai agent)

```text
QUY TẮC BÀN GIAO BBASM (Claude Local ↔ Codex QA)

1. Trước khi làm bất cứ gì: đọc COORD_TASKS.md trên claude/upbeat-thompson-b7bb23 (git show <nhánh>:COORD_TASKS.md
   nếu bạn không checkout nhánh đó). Tìm đúng task bằng ID, xác nhận base_commit khớp git log hiện tại.
2. Nếu bạn là Claude (sửa code):
   - Chỉ sửa task đang ở trạng thái OPEN hoặc FAIL (có ghi lý do fail). Đổi trạng thái sang IN_PROGRESS trước khi sửa.
   - Sửa xong, test xanh, commit. Đổi trạng thái sang READY_FOR_QA, điền result_commit = commit vừa tạo.
   - Không sửa hai task chạm cùng file trong một commit trừ khi bảng ghi rõ chúng được nhóm chung.
3. Nếu bạn là Codex (QA):
   - Chỉ QA task đang READY_FOR_QA. Checkout đúng result_commit (không phải HEAD, không phải commit khác).
   - Không sửa code sản phẩm. Viết báo cáo + bằng chứng vào một nhánh test/vNNN-host-audit MỚI (không ghi đè nhánh QA cũ).
   - Trả PASS kèm bằng chứng cụ thể (lệnh, số liệu, file), hoặc FAIL kèm cách tái hiện chính xác.
4. Không agent nào tự đổi trạng thái của task mình không sở hữu, trừ khi được bảng giao rõ ("owner: cả hai").
5. Không merge main, không force-push, không tạo PR, không sửa .env/DB/targets của người dùng, không đụng
   stack bbasm-v12 (127.0.0.1:18765), không scan Arc/Wolt/host ngoài. QA chỉ dùng fixture/mock/127.0.0.1.
6. Nếu base_commit không khớp HEAD bạn thấy: DỪNG, báo cho người dùng, không tự đoán commit nào mới hơn là đúng.
```
