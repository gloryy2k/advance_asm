# QA NUC-6 · v1.6.7

Ngày 17/10/2026. Nhánh nguồn `claude/upbeat-thompson-b7bb23` tại `c7a5b90` (chứa `41984f8`); submodule `vendor/claude-bug-bounty` tại `5a329e0`. `COORD_TASKS.md` ghi NUC-6 `READY_FOR_QA`, base `c19e5b6`. Kiểm Phase 9 và hồi quy trên code `41984f8`; `c7a5b90` chỉ cập nhật bảng công việc. Chỉ dùng fixture `127.0.0.1`, container QA riêng `--network none`; không dùng H1 hoặc stack `bbasm-v12`.

## Kết quả

| Mã | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| NUC-6.1 | `git fetch origin; git switch claude/upbeat-thompson-b7bb23; git pull --ff-only; git submodule update --init --recursive` | PASS | HEAD `c7a5b90`, ancestor `41984f8`, submodule `5a329e0`. |
| NUC-6.2 | Chạy đoạn Phase 9 thực từ `recon_engine.sh` bằng nuclei thật với 300 URL localhost | PASS | `targets.txt` 300 dòng; `coverage.json`: `live_urls=300`, `given_urls=300`, `limit=0`, `timed_out=false`, `failed=false`; fixture ghi 300 request, nuclei tạo 300 finding. [normal300.json](review_evidence/v168_qa/normal300.json), [coverage](review_evidence/v168_qa/coverage_normal300.json). |
| NUC-6.3 | `BBASM_NUCLEI_TIMEOUT=5` trên 300 URL localhost, HTTP fixture cố ý giữ mỗi request 20 giây | PASS, có finding P2 | Nuclei dừng sau 5,10 giây, exit `124`; `timed_out=true`, `given_urls=300`, 50 request đã bắt đầu. [timeout5.json](review_evidence/v168_qa/timeout5.json). |
| NUC-6.4 | Không đặt biến timeout, chạy Quick và Full | PASS | Quick: log `timeout=3600s`, 300/300 URL; Full: log `timeout=7200s`, 1/1 URL. [normal300.json](review_evidence/v168_qa/normal300.json), [full_default.json](review_evidence/v168_qa/full_default.json). |
| NUC-6.5 | Playwright headless 1366px: Review → Light → mở tùy chỉnh → điền 45 vào `nuclei tối đa mỗi lần chạy (giây)` → Launch | PASS | Ô hiện và nhận 45; request Launch bị chặn trước khi tới server, payload có `config.nuclei_timeout=45`, `depth=light`. [Ảnh Review](review_evidence/v168_qa/nuc6_review_1366.png), [script UI](review_evidence/v168_qa/check_nuc6_ui.py). |
| NUC-6.6 | `python -m pytest -q -m 'not integration'` trong image có nuclei+ffuf thật | PASS | `471 passed, 33 deselected` (50,28 giây). |
| NUC-6.7 | Cùng lệnh trong image không có nuclei+ffuf trên PATH | PASS | `471 passed, 33 deselected` (50,28 giây). |
| NUC-6.8 | `npx vitest run`; `npx tsc --noEmit`; `npm run build` | PASS | 94 tests passed; tsc exit 0; Vite build exit 0 (cảnh báo bundle >500 kB). |

Script [check_nuc6_phase9.py](review_evidence/v168_qa/check_nuc6_phase9.py) lấy nguyên đoạn Phase 9 từ image, chạy nuclei binary thật trong container không mạng với template và server ở `127.0.0.1:8099`. Lệnh tái hiện mỗi chế độ:

```powershell
docker run --rm --network none --entrypoint python --mount 'type=bind,source=<QA_DIR>,target=/qa' bbasm-v168nuc-qa /qa/check_nuc6_phase9.py normal300
docker run --rm --network none --entrypoint python --mount 'type=bind,source=<QA_DIR>,target=/qa' bbasm-v168nuc-qa /qa/check_nuc6_phase9.py timeout5
docker run --rm --network none --entrypoint python --mount 'type=bind,source=<QA_DIR>,target=/qa' bbasm-v168nuc-qa /qa/check_nuc6_phase9.py full_default
```

`<QA_DIR>` là thư mục scratch chứa script; script ghi fixture và output vào `/qa/phase9`. Image `bbasm-v168nuc-qa` được build từ `41984f8` với submodule `5a329e0`; container UI QA chạy riêng ở `127.0.0.1:18768` và đã được dọn. Vì test chạy riêng đoạn Phase 9, kết quả này không đo toàn bộ orchestration scan Strong.

## Finding mới

**P2 — Log nói “no findings” sau khi nuclei timeout, dễ bị hiểu là đã quét xong.** Với fixture 300 URL phản hồi chậm và `BBASM_NUCLEI_TIMEOUT=5`, log có cảnh báo `stopped after 5s (timeout) ... PARTIAL`, ngay sau đó lại có `[DONE] nuclei: no findings`; exit thực là `124`, `coverage.timed_out=true`, mới có 50 request bắt đầu. Tái hiện bằng chế độ `timeout5` ở trên. Nguyên nhân: nhánh `else` in `log_done "nuclei: no findings"` khi `NUC_FAILED=false`, dù `NUC_EXIT=124` tại `vendor/claude-bug-bounty/tools/recon_engine.sh` Phase 9. Hướng sửa: khi `NUC_EXIT=124`, dùng nhãn “dở dang, chưa có finding trong phần đã chạy” thay cho `[DONE] no findings`; thêm test log timeout. Không sửa code trong nhánh QA này.

## Giới hạn và dọn dẹp

- `given_urls` là số URL giao cho nuclei, không phải số URL nuclei đã hoàn tất. Trong ca timeout có 300 URL được giao và 50 request bắt đầu; không suy ra 250 URL còn lại đã quét.
- Chưa chạy scan qua toàn bộ API/runner; chỉ kiểm chính xác đoạn Phase 9 bằng binary thật và kiểm payload UI bằng cách chặn Launch.
- Đã dọn container và image QA `bbasm-v168nuc-*`; không prune toàn cục, không chạm dữ liệu/stack người dùng.

**Kết luận NUC-6:** các tiêu chí chính PASS; một lỗi câu chữ P2 trong log timeout cần Claude xử lý riêng.
