# Bảng công việc Claude Local ↔ Codex QA

Nguồn sự thật duy nhất về task nào đang mở, ai cầm, base commit nào, trạng thái gì. Chỉ Claude ghi vào file này
(sống trên nhánh code `claude/upbeat-thompson-b7bb23`). Codex không commit vào nhánh này — Codex chỉ tạo nhánh
`test/vNNN-host-audit` mới để nộp báo cáo QA, không bao giờ ghi đè nhánh cũ, không merge.

**Quy tắc bàn giao đầy đủ**: xem cuối file. Không agent nào tự đổi trạng thái của task mình không sở hữu.

## Trạng thái: `OPEN` (chưa ai làm) · `IN_PROGRESS` · `READY_FOR_QA` · `PASS` · `FAIL` (kèm lý do) · `DONE` · `BLOCKED` (chờ quyết định D#)

| ID | Ưu tiên | Owner | Trạng thái | base_commit | result_commit | Tóm tắt |
| --- | --- | --- | --- | --- | --- | --- |
| NUC-3 | P2 | Codex | OPEN | d65c4f5 | — | Đo `nuclei/stats.jsonl` phình bao nhiêu ở fixture chạy dài hơn 12s hiện có (vài trăm giây), không cần sửa gì nếu không có vấn đề. |
| NUC-4 | P2 | Codex | OPEN | d65c4f5 | — | Chạy 1 scan Strong qua orchestration thật (`ReconOrchestrator`/`JobRunner`, không gọi tay `recon_engine.sh`) với ≥2 lệnh chạm Phase 9 (main+deep), xác nhận `build_report` gộp đúng ngoài fixture ghép tay. |
| UX-1 | P3 | Claude | READY_FOR_QA | ab9abc4 | `6ba098d` | `GET /api/programs/{slug}/ports` và `/dirs` (mới) + 2 tab "Cổng/Dịch vụ"/"Đường dẫn dò được" trong Dữ liệu. Đọc lại `backend.asm.results.summarize_ports/summarize_dirs` của scan cụ thể (`?scan=latest|<id>`), không có bảng DB riêng. |
| ENG-1 | P4 | Claude | OPEN | — | — | Sửa `open_ports.txt` ở `recon_engine.sh` (submodule) parse đúng mọi cặp host/cổng. Không khẩn (BBASM đã bù ở tầng đọc). |

## Việc đã đóng (lịch sử, không mở lại — sự cố tái phát ra ID mới)

| ID | Kết quả | Commit | Ghi chú |
| --- | --- | --- | --- |
| (v1.6.1) Repair idempotency + test cô lập PATH | PASS (QA Codex `test/v161-host-audit`@6b9efe6, mã C1/C2) | `1e26cfe` | Xem NOTES.md v1.6.1. |
| (v1.6.1) Nuclei coverage.json + stats-json | PASS (QA Codex, mã C4-C7) | `7428043`, `f20a636` | Xem NOTES.md v1.6.1. Phát sinh C8, C9 → NUC-1, NUC-2. |
| NUC-1 — coverage.json hỏng khi nuclei lỗi | **PASS** (QA Codex `test/v162-host-audit`@03c1f6b) | `d65c4f5` (BBASM) + `6638e72` (submodule, sau khi vá thêm log "[DONE] nuclei: no findings" sai mà Codex phát hiện) | Codex: nuclei thoát mã 1, `coverage.json` parse được, `failed=true`, Run hiện đúng "LỖI: nuclei không chạy được", không hiện `n/a`/sentinel. |
| NUC-2 — giới hạn sai khi gộp quick/full | **PASS** (QA Codex `test/v162-host-audit`@03c1f6b) | `d65c4f5` | Codex: gộp quick (50/60) + full (2/2) → `limits=[50,200]`, detail "mỗi lượt có giới hạn riêng: 50, 200 URL", không còn câu sai. |
| DOC-1 | DONE (không cần QA) | `d65c4f5` | `NOTES.md` +v1.6.1/v1.6.2, `BACKLOG.md` +mục "Độ phủ nuclei", `CLOUD_TO_LOCAL_HANDOFF.md` ghi chú lỗi thời. |

## Quyết định sản phẩm đang chờ bạn (không lên task thi công tới khi chốt)

- **D1** — Giới hạn 50/200 URL/lượt của nuclei: giữ nguyên / tăng / thêm vòng "nuclei tiếp". Xem `BACKLOG.md` mục "Độ phủ nuclei".
- **D2** — Cưỡng chế giới hạn thư mục repo khi quét secrets (trufflehog `--include-paths`).
- **D3** — "Probe tiếp" phần chưa quét (`stats.unprobed_hosts`); nên chốt **trước** D1 nếu D1 chọn hướng "nuclei tiếp" (dùng chung cơ chế).
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
