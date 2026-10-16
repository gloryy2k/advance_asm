# QA NUC-3 / NUC-4 — BBASM v1.6.2

## Phiên bản và cách ly

- Nguồn `origin/claude/upbeat-thompson-b7bb23` tại `ab9abc4`; `COORD_TASKS.md` ghi NUC-3/NUC-4 `OPEN`, owner Codex, `base_commit=d65c4f5`. `git merge-base --is-ancestor d65c4f5 ab9abc4` trả 0. Submodule `vendor/claude-bug-bounty` là `6638e72`.
- Build image riêng `bbasm-v163qa-bbasm` (build thành công). Mọi lần chạy đều dùng `docker run --rm --network none`; fixture HTTP nằm trên `127.0.0.1` **bên trong container**. Không chạy Arc/Wolt/host ngoài, không dùng H1/token, không chạm stack `bbasm-v12` hoặc dữ liệu người dùng.
- Script tái hiện và số liệu máy đọc được nằm trong [`review_evidence/v163_qa/`](review_evidence/v163_qa/). DB, targets, log và template fixture thực thi được ghi vào thư mục QA tạm ngoài repo.

| ID | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| NUC-3 | Chạy **nuclei thật** qua đúng Phase 9 của engine trên 80 URL loopback, một template HTTP địa phương, tốc độ 1 request/giây và fixture trễ 4 giây/request; đo `stats.jsonl` sau hơn 300 giây | **PASS** | Thời gian **321,79 s**; nuclei exit **0**, 80/80 URL và 80 request, `failed=false`, `timed_out=false`. `stats.jsonl`: **66 dòng JSON / 11.794 byte** (không có dòng lỗi khác). Trung bình ~36,7 byte/giây; ngoại suy tuyến tính tới 1.800 s là **~369 dòng / ~65.972 byte (~64,4 KiB)**. Đây là ước tính, chưa chạy thật đủ 1.800 s. Không thấy tăng dung lượng bất thường. |
| NUC-4 | Chạy **Strong qua `JobRunner.submit` và `ReconOrchestrator` thật**, một host main và một host deep do nguồn khám phá giả cung cấp; đọc endpoint `/api/scans/1/phases` | **PASS** | Scan fixture `#1` **done**, 12,78 s. Hai lệnh thật ở `recon/scans/1/1` (main) và `/3` (deep) đều chạy Phase 9 và tự tạo `nuclei/coverage.json`: mỗi lượt `given_urls=live_urls=1`, `limit=200`, `failed=false`. Server loopback nhận `main.qa.test /nuclei-check` và `deep.qa.test /nuclei-check` từ nuclei thật. `/phases` HTTP **200**, nuclei `status=ran`, `count=2`, `given_urls=live_urls=2`, `requests=2`, `hosts=2`, `limits=[200]`, `failed=false`; detail ghi **“2/2 URL đang sống được đưa cho nuclei”**. |
| Hồi quy backend | `python -m pytest -q -m "not integration"` trong image có nuclei + ffuf thật; lần nữa trong container tạm ẩn hai binary | **PASS** | Lần lượt **453 passed, 33 deselected, 4 warnings** trong 54,31 s và 52,99 s. Mount repo read-only và bản sao vendor chuẩn hóa LF để chạy trên Linux. |
| Hồi quy frontend | `npx vitest run`, `npx tsc --noEmit`, `npm run build` | **PASS** | **89 passed**; TypeScript và build exit 0. Vite còn cảnh báo bundle JS 511,12 kB vượt ngưỡng 500 kB; không phải lỗi build. |

## Tái hiện

Build image QA từ checkout `ab9abc4`/submodule `6638e72`, rồi chép ba script trong `review_evidence/v163_qa/` vào một thư mục tạm, ví dụ `E:\code\bbasm\qa_v163`. Các script dùng `/qa` trong container và tự tạo fixture/DB ở đó:

```powershell
docker compose -p bbasm-v163qa build
docker run --rm --network none --entrypoint python --mount "type=bind,source=E:\code\bbasm\qa_v163,target=/qa" bbasm-v163qa-bbasm /qa/check_nuclei_long.py
docker run --rm --network none --add-host main.qa.test:127.0.0.1 --add-host deep.qa.test:127.0.0.1 -e PYTHONPATH=/app --entrypoint python --mount "type=bind,source=E:\code\bbasm\qa_v163,target=/qa" bbasm-v163qa-bbasm /qa/check_orchestrated.py
```

Trong NUC-4, `subfinder`, `curl` và `httpx` là shim fixture để sinh host và trạng thái HTTP ổn định; runner, script recon, nuclei, ingest, build_report và route `/phases` là mã/binary thật. Mạng container bị tắt. NUC-3 trích nguyên khối Phase 9 từ script nằm trong image, rồi gọi nuclei thật với bộ template địa phương. Bảng số chi tiết ở [`metrics.json`](review_evidence/v163_qa/metrics.json).

Hồi quy backend dùng `docker run --rm --network none --entrypoint python` với source mount read-only tại `/app` và bản sao `vendor/claude-bug-bounty` đã chạy `python scripts/normalize_vendor_lf.py` tại `/app/vendor/claude-bug-bounty`, sau đó truyền `-m pytest -q -m "not integration"`. Lượt không có binary truyền `/qa/unit_without_tools.py` thay cho `-m pytest`, chỉ đổi tên `/usr/local/bin/nuclei` và `/usr/local/bin/ffuf` trong container dùng một lần. Frontend chạy lần lượt `npx vitest run`, `npx tsc --noEmit`, `npm run build` tại `frontend/`.

## Giới hạn và finding

- **Không có finding mới** trong NUC-3/NUC-4. NUC-4 chứng minh trường `failed=false` của hai lượt thành công được gộp đúng; không cố tạo một lỗi nuclei trong deep pass của cùng scan. Trường hợp lỗi riêng lẻ đã được QA ở NUC-1.
- Ở lần gọi pytest trực tiếp từ image, collection thiếu module `scripts` vì Dockerfile không copy thư mục này. Lệnh hồi quy đúng đã mount **toàn bộ source repo read-only** và bản sao vendor LF, sau đó cả hai cấu hình đều đạt 453 passed. Đây là khác biệt của môi trường chạy test, không phải lỗi sản phẩm khi scan.

**Kết luận:** NUC-3 **PASS**, NUC-4 **PASS**. Không sửa code sản phẩm hoặc `COORD_TASKS.md`.
