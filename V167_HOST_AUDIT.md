# QA NUC-5 vòng 2 — BBASM v1.6.6

## Phiên bản và phạm vi

- Nhánh nguồn `claude/upbeat-thompson-b7bb23` tại `8d3e96e` chứa `4102e75`; `COORD_TASKS.md` ghi **NUC-5 READY_FOR_QA vòng 2**, `result_commit=4102e75`. Toàn bộ kiểm thử chạy trên code **đúng tại `4102e75`**, submodule `bfd61ba`; nhánh báo cáo tách từ `8d3e96e`.
- Image QA riêng `bbasm-v167nuc-qa`, nuclei thật **v3.11.1**. Phase 9 chỉ nhắm HTTP fixture trong container tại `127.0.0.1:8099`, container `--network none`. Không token, không H1, không scan host ngoài và không chạm stack `bbasm-v12`.

| ID | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| NUC-5 | Chạy lại đoạn Phase 9 nguyên văn từ `recon_engine.sh` bằng [`check_nuc5_phase9.py`](review_evidence/v167_qa/check_nuc5_phase9.py); `BBASM_NUCLEI_AUTO_SELECT=1`; template quản lý **chỉ** ở `-t <official>`; ban đầu `/root/nuclei-templates` không tồn tại; **không** đặt `QA_COPY_TEMPLATE_HOME` | **PASS** | Shim thêm đúng một `-as` và `-vv`, tự chuẩn bị đường template mặc định; nuclei thoát **0**. `coverage.failed=false`, `given_urls=1`, `requests=1`, `matched=1`; `findings.jsonl` có 1 finding `bbasm-nuc5-local` trên localhost. [`phase9_v2.json`](review_evidence/v167_qa/phase9_v2.json). |
| NUC-5 | Kiểm `nuclei/templates_loaded.txt` và `nuclei/stats.jsonl` sau Phase 9 | **PASS** | `templates_loaded.txt` có **1 dòng template**, **0 dòng bắt đầu bằng `{`**; finding JSONL chỉ ở `findings.jsonl`. `stats.jsonl` có 2 dòng JSON, 384 byte, không bị lẫn stdout. |
| NUC-5 | Dùng chính `coverage.json` từ lượt nuclei thật, trong đó nuclei tự báo `templates="0"` nhưng `requests="1"`, `matched="1"`; gọi `build_report()` bằng [`check_nuc5_report.py`](review_evidence/v167_qa/check_nuc5_report.py) | **PASS** | Phase `status=ran`, `count=1`; detail nói “nuclei đã gửi 1 request trên 1 host — số template nuclei tự báo **không đáng tin**…”, không nói “đã chạy 0 template”; dữ liệu có `templates=null`, `templates_unreliable=true`. [`report_v2.json`](review_evidence/v167_qa/report_v2.json). |
| NUC-5 | `python -m pytest -q -m "not integration"` trong image Linux với nuclei+ffuf thật, rồi trong container dùng một lần ẩn hai binary | **PASS** | Cả hai lượt **470 passed, 33 deselected, 4 warnings** (54,43 s và 54,02 s). Cảnh báo: 3 deprecation thư viện và pytest cache không ghi được trên source mount read-only. |
| NUC-5 | `npx vitest run`, `npx tsc --noEmit`, `npm run build` | **PASS** | Vitest **94/94** (16,10 s); TypeScript và build exit 0. Vite cảnh báo bundle 518,82 kB vượt ngưỡng 500 kB. |

## Tái hiện và kết luận

Build image từ `4102e75`: `docker build -t bbasm-v167nuc-qa .`. Chạy fixture offline: `docker run --rm --network none -e PYTHONPATH=/app --entrypoint python --mount 'type=bind,source=E:\code\bbasm\qa_v167,target=/qa' bbasm-v167nuc-qa /qa/check_nuc5_phase9.py`; sau đó cùng lệnh với `/qa/check_nuc5_report.py`. Script đặt `HOME=/root` đúng như image thật và kiểm tra `/root/nuclei-templates` **chưa có** trước khi gọi shim; không tự tạo bản sao template. Thay đường dẫn scratch `E:\code\bbasm\qa_v167` khi chạy trên máy khác.

**NUC-5 PASS vòng 2.** Ba finding P1/P2/P3 của `test/v166-host-audit@db4442a` đều không còn tái hiện. Không phát hiện finding mới trong phạm vi này. Giới hạn: dùng một template localhost, chưa đo thời gian/đĩa khi shim đồng bộ bộ khoảng 14 nghìn template; không chạy lại thao tác UI/API tra cứu tag vì không nằm trong ba sửa đổi, nhưng hồi quy backend/frontend đều đạt. Không sửa code sản phẩm hoặc dữ liệu người dùng.
