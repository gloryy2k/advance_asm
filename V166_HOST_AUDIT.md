# QA NUC-5 — BBASM v1.6.5

## Phiên bản, phạm vi

- Nhánh nguồn `claude/upbeat-thompson-b7bb23` ở `5619aff`; `e3ed38d` là tổ tiên của HEAD, NUC-5 trong `COORD_TASKS.md` là `READY_FOR_QA`. API, shim, UI và hồi quy được kiểm trên đúng **`e3ed38d`**, submodule `bfd61ba`; nhánh báo cáo tách từ `5619aff`.
- Dùng image QA riêng `bbasm-v166nuc-qa` (nuclei **v3.11.1**), ba template nội bộ và HTTP server chỉ nghe `127.0.0.1` **bên trong container `--network none`**. UI mở qua Playwright headless ở `127.0.0.1:18767`; request Launch được chặn để chỉ kiểm payload, không khởi chạy scan. Không chạm stack `bbasm-v12`.

| ID | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| NUC-5 | GET `/api/tools/templates/lookup?tag=bbasmqa` với nuclei thật và bộ đã cài giả lập 3 template | **PASS** | Trả `total=2`: `QA Alpha/low/http/qa/a.yaml` và `QA Beta/medium/http/qa/b.yaml`; template `otherqa` không lẫn vào. Tag `absentqa` trả 200, `total=0`; `bad tag!` trả 422 `invalid_tag`. Chạy offline bằng [`check_nuc5_api.py`](review_evidence/v166_qa/check_nuc5_api.py). |
| NUC-5 | Shim + đoạn Phase 9 nguyên văn từ `recon_engine.sh`, nuclei thật, `BBASM_NUCLEI_AUTO_SELECT=1`, bộ template quản lý chỉ ở đường `-t <official>` | **FAIL** | Argv có đúng một `-as` và `-vv`, nhưng nuclei thoát **1**: `could not get templates in directory .../home/nuclei-templates: no such file or directory`. `coverage.failed=true`, `requests=0`, `findings.jsonl` rỗng, `templates_loaded.txt` được tạo nhưng rỗng. `stats.jsonl` có 1 dòng JSON và 1 dòng lỗi. [`phase9_default.json`](review_evidence/v166_qa/phase9_default.json). |
| NUC-5 | Đối chứng: chép cùng template (có tag `tech`) vào `HOME/nuclei-templates` **chỉ trong fixture**; chạy lại Phase 9 | **PASS có điều kiện** | Nuclei thoát 0; `-as`/`-vv` mỗi cờ một lần; `templates_loaded.txt` có 2 dòng; `stats.jsonl` 2 dòng JSON, 382 byte; `findings.jsonl` có **1** finding `bbasm-nuc5-local` trên `127.0.0.1`; `coverage.failed=false`, `requests=1`. Chỉ thay vị trí template, không sửa code. [`phase9_with_home.json`](review_evidence/v166_qa/phase9_with_home.json) và [`check_nuc5_phase9.py`](review_evidence/v166_qa/check_nuc5_phase9.py). |
| NUC-5 | Review desktop 1366px: tra cứu tag, bật toggle, kiểm payload Launch | **PASS** | Bảng hiện đúng 2 template với tên, mức và đường dẫn. Chọn Light, bật “Tự chọn thêm template…”; POST Launch được Playwright chặn và ghi `config.nuclei_auto_select=true`, `depth=light`, `automation_ack=true`. [Ảnh Review](review_evidence/v166_qa/nuc5_review_1366.png), [`check_nuc5_ui.py`](review_evidence/v166_qa/check_nuc5_ui.py). |
| NUC-5 | `python -m pytest -q -m "not integration"` trong image Linux, có rồi không có binary nuclei+ffuf | **PASS** | Cả hai lượt **466 passed, 33 deselected, 4 warnings** (52,77 s và 52,35 s). Bản “không có tool” chỉ đổi tên binary trong container dùng một lần. Ba deprecation thư viện và một cảnh báo pytest cache trên source mount read-only. |
| NUC-5 | `npx vitest run` ×3, `npx tsc --noEmit`, `npm run build` | **PASS** | Vitest **94/94** cả 3 lượt (14,77 s; 13,61 s; 13,32 s). TypeScript và build exit 0. Vite cảnh báo bundle 518,82 kB vượt ngưỡng 500 kB. |

## Finding mới — không sửa code

### NUC-5 · P1 · Auto-select làm nuclei thất bại trong image chuẩn

**Tái hiện:** build image từ `e3ed38d`, tạo bộ template quản lý ở `official/` và chạy [`check_nuc5_phase9.py`](review_evidence/v166_qa/check_nuc5_phase9.py) với `BBASM_NUCLEI_AUTO_SELECT=1`, không đặt `QA_COPY_TEMPLATE_HOME`. Container có nuclei thật và `-t <official>`, nhưng không có `HOME/nuclei-templates` (image QA cũng không có `/root/nuclei-templates`). Nuclei v3.11.1 dùng đường mặc định đó để khởi tạo automatic scan service, không dùng riêng đường `-t` cho bước này; nó thoát 1 trước khi gửi request. Đối chứng `QA_COPY_TEMPLATE_HOME=1` chạy thành công. Đây là lỗi của đường chạy `-as` mới trong image, không phải thiếu template tại `official/`.

**Hướng sửa:** cấu hình automatic scan service dùng chính bộ template quản lý, hoặc cung cấp đường mặc định bên trong container trỏ tới bộ đó (đảm bảo có template gắn tag `tech`) mà không kích hoạt tải template. Kiểm lại trên image thật với bộ quản lý, `--network none` và target localhost trước khi cho NUC-5 PASS.

### NUC-5 · P2 · Run có thể báo 0 template dù nuclei tạo finding

Trong đối chứng thành công, `stats.jsonl`/`coverage.json` của nuclei v3.11.1 ghi `templates=0`, đồng thời `matched=1`, `requests=1`, `findings.jsonl=1`. `backend.asm.results.summarize_nuclei()` trả `templates=0`; phần detail Run sẽ nói “nuclei tự báo đã chạy 0 template”. Không thể dùng trường `templates` này làm số template thực chạy ở chế độ `-as` nếu nó mâu thuẫn với finding. **Hướng sửa:** hiển thị “chưa xác định” khi telemetry tự mâu thuẫn, hoặc xác định số template đã nạp từ nguồn có nghĩa rõ ràng; không gọi số đã nạp là số đã chạy.

### NUC-5 · P3 · `templates_loaded.txt` lẫn bản ghi finding JSONL

Đối chứng có 2 dòng trong file: 1 dòng template đã nạp và 1 dòng finding JSONL đầy đủ (có request/response), trong khi cùng finding đã có ở `findings.jsonl`. Nguyên nhân là shim chuyển **toàn bộ stdout** của nuclei vào `templates_loaded.txt`; `-jsonl -o` vẫn in finding trên stdout. **Hướng sửa:** chỉ giữ các dòng mô tả template trong file này hoặc đổi tên/giải thích file để không gọi toàn bộ nội dung là danh sách template.

## Kết luận và giới hạn

**NUC-5 FAIL tổng thể** do P1 ở luồng nuclei thật; API, UI và hồi quy đạt. P2/P3 là vấn đề độ tin cậy của kết quả khi đã khắc phục P1. Chỉ dùng vài template fixture và localhost, chưa kiểm với toàn bộ kho 14 nghìn template. Không sửa code sản phẩm, không dùng token/H1 và không scan host ngoài.
