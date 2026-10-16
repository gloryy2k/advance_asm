# QA NUC-1 / NUC-2 — BBASM v1.6.2

## Phiên bản và phạm vi

- Nguồn: `origin/claude/upbeat-thompson-b7bb23` tại `390bad0`; commit này chỉ thêm `COORD_TASKS.md`. Kiểm mã nguồn đúng `result_commit=d65c4f5` của cả hai task, với submodule `vendor/claude-bug-bounty=488d910`. `f20a636` là `base_commit` và là tổ tiên của `d65c4f5`; trước đó có `7428043`, `1e26cfe`.
- QA trong container/image riêng `bbasm-v162qa-bbasm`, `--network none`. Nuclei thật chỉ gọi server fixture `127.0.0.1:8099`. Không chạy scan Arc/Wolt hoặc host ngoài, không dùng H1/token, không đụng stack `bbasm-v12`.
- Harness tái hiện: [`review_evidence/v162_qa/`](review_evidence/v162_qa/). File sinh ra, DB fixture và targets fixture chỉ ở thư mục QA tạm bên ngoài repo.

| ID | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| NUC-1 | Chạy Phase 9 bằng nuclei thật với template không tồn tại; đọc `coverage.json` và gọi `build_report` | **PASS** | Nuclei thoát mã **1** (`QA_NUC_EXIT=1`), khác 0/124. `coverage.json` parse được, `failed=true`, `live_urls=given_urls=2`, `timed_out=false`. `build_report` trả `status=partial`, detail: **“2/2 URL đang sống được đưa cho nuclei — LỖI: nuclei không chạy được (cấu hình hoặc template hỏng — xem nuclei/stats.jsonl); số liệu trên không đại diện cho một lượt quét thật”**. Detail không có “0 kết quả”, `n/a`, số `9223372036854775808`, hay số template giả. |
| NUC-2 | Gộp hai lượt Phase 9 thật: quick có 60 URL, full có 2 URL; đọc `summarize_nuclei`, `structured_result`, `build_report` | **PASS** | Quick: `given_urls=50/60`, `limit=50`, log **“only 50 of 60”**; full: `given_urls=2/2`, `limit=200`. Tổng `given_urls=52/62`, `limits=[50,200]`. Run detail: **“mỗi lượt có giới hạn riêng: 50, 200 URL”**; không còn câu sai “giới hạn 200 URL mỗi lượt”. `build_report` trả `status=ran`, `count=52`. |
| Kiểm thử backend | `python -m pytest -q -m "not integration"` trong image có nuclei + ffuf thật ở `/usr/local/bin`, sau đó trong container riêng tạm ẩn hai binary khỏi đường dẫn này | **PASS** | Cả hai cấu hình: **453 passed, 33 deselected, 4 warnings**; lần lượt 49.77 s và 49.58 s. Repo và vendor được mount read-only; 24 script vendor được mount từ bản sao đã chuẩn hóa LF cho Linux. |
| Kiểm thử frontend | `cd frontend && npx vitest run && npx tsc --noEmit && npm run build` | **PASS** | **89 tests passed**, TypeScript exit 0, Vite build exit 0. Vite cảnh báo bundle 511.12 kB vượt ngưỡng 500 kB, không phải lỗi build. |

## Lệnh tái hiện chính

Các script trong `review_evidence/v162_qa/` dùng đường dẫn `/qa` trong container, trích đúng Phase 9 từ engine đã build và khởi tạo fixture HTTP loopback. Ví dụ sau khi build image QA từ `d65c4f5`:

```powershell
docker run --rm --network none --entrypoint python --mount "type=bind,source=E:\code\bbasm\qa_v162,target=/qa" bbasm-v162qa-bbasm /qa/check_nuclei_phase.py badtemplate
docker run --rm --network none --entrypoint python --mount "type=bind,source=E:\code\bbasm\qa_v162,target=/qa" bbasm-v162qa-bbasm /qa/check_nuclei_phase.py quick60
docker run --rm --network none --entrypoint python --mount "type=bind,source=E:\code\bbasm\qa_v162,target=/qa" bbasm-v162qa-bbasm /qa/check_nuclei_phase.py normal
docker run --rm --network none --entrypoint python --mount "type=bind,source=E:\code\bbasm\qa_v162,target=/qa" bbasm-v162qa-bbasm /qa/check_aggregate.py
```

`check_nuc1_report.py` và `check_nuc2_report.py` gọi trực tiếp `build_report` trên DB/targets fixture. Bốn script trong repo có thể chép vào thư mục QA tạm `/qa` để chạy lại các lệnh trên; đường dẫn Windows trong ví dụ là đường dẫn QA của lượt này, không phải dữ liệu người dùng.

## Ghi chú

- `last_stats` **thô** của nuclei khi lỗi vẫn có chuỗi `n/a` và sentinel `9223372036854775808`; parser đã không đưa các giá trị ấy vào detail Run. Đây là khác biệt giữa dữ liệu nguyên bản để chẩn đoán và số liệu hiển thị.
- Engine vẫn in dòng `[DONE] nuclei: no findings` sau cảnh báo exit code 1. Run đã đánh dấu `partial` và báo lỗi đúng theo điều kiện NUC-1; nên cân nhắc sửa câu log này riêng để tránh người xem log hiểu nhầm.
- Chưa chạy scan Strong qua toàn bộ orchestration hoặc đo file stats của scan dài; hai việc đó là NUC-4 và NUC-3 riêng trên bảng phối hợp, ngoài phạm vi QA lần này.

**Kết luận:** NUC-1 **PASS**, NUC-2 **PASS** trên đúng commit kết quả `d65c4f5` và submodule `488d910`.
