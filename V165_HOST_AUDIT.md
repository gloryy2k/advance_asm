# QA UX-1 vòng 2 — BBASM

## Phiên bản và phạm vi

- Nhánh nguồn `claude/upbeat-thompson-b7bb23` ở `1594804`; `976e1c3` là tổ tiên của HEAD, UX-1 trong `COORD_TASKS.md` là `READY_FOR_QA (vòng 2)`. Kiểm code sản phẩm **đúng tại `976e1c3`**, submodule `bfd61ba`; nhánh báo cáo tách từ `1594804`.
- Fixture dùng `example.com` làm tên giả trong DB và các IP tài liệu `192.0.2.x`/`104.18.1.x` trong file mẫu; không gửi request tới các địa chỉ đó. API/test chạy trong container `--network none`; UI chỉ mở qua Playwright headless tại `127.0.0.1:18766`. Không chạm stack `bbasm-v12`.

| ID | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| UX-1 | Chạy lại `check_ux_api.py`: 2 scan hoàn tất có dữ liệu khác nhau, scan #3 là draft | **PASS** | `scan=latest` chọn #2: ports 8 cặp/3 host, dirs 35 phản hồi. `scan=1` chọn #1: ports 2 cặp/1 host, dirs 1 phản hồi. Draft trống, ID không tồn tại và program chưa có scan hoàn tất đều `found=false`. |
| UX-1 | Chạy lại `check_ux_draft_orphan.py`: đặt `nmap_greppable.txt` và `ffuf_orphan.json` trong output của draft #3 | **PASS** | `/ports?scan=3` và `/dirs?scan=3` đều HTTP 200, `found=false`; ports `pairs=[]`, dirs `total=0`. Script có assertion cho cả hai. |
| UX-1 | Chạy lại `check_ux_ui.py` ở 1366px; mở `?v=ports&scan=1` và `?v=dirs&scan=1` | **PASS** | Cổng/Dịch vụ có đúng 2 hàng của #1, không có nhãn DỞ DANG của #2; Đường dẫn dò được có 1 hàng/1 phản hồi của #1. Cả hai tab hiện “Đang xem scan #1.” Ảnh: [ports #1](review_evidence/v165_qa/ports_scan_1_1366.png), [dirs #1](review_evidence/v165_qa/dirs_scan_1_1366.png). |
| UX-1 | Kiểm UI mặc định vẫn dùng scan mới nhất | **PASS** | Ports 8 hàng, nhãn DỞ DANG và cảnh báo 7 cặp Cloudflare; dirs 35 phản hồi, 33 nhiễu, 2 hàng đáng xem, cảnh báo host chỉ có 403. |
| UX-1 | `python -m pytest -q -m "not integration"` trong image Linux với nuclei+ffuf thật, rồi trong container dùng `unit_without_tools.py` ẩn hai binary | **PASS** | Cả hai lượt **459 passed, 33 deselected, 4 warnings**; lần lượt 50,46 s và 49,76 s. Cảnh báo gồm 3 deprecation thư viện và pytest cache không ghi được trên source mount read-only. |
| UX-1 | `npx vitest run` ×3, `npx tsc --noEmit`, `npm run build` | **PASS** | Vitest **93/93** ở cả 3 lượt (13,70 s; 13,40 s; 12,83 s). `tsc` exit 0; Vite build exit 0. Vite còn cảnh báo bundle 515,74 kB lớn hơn ngưỡng 500 kB. |

## Lệnh tái hiện

Build image QA riêng từ `976e1c3`: `docker build -t bbasm-v165ux-qa .`. Script fixture được lưu trong `review_evidence/v165_qa/`; mount thư mục chứa script vào `/qa`, đặt `PYTHONPATH=/app` rồi chạy `python /qa/check_ux_api.py` và `python /qa/check_ux_draft_orphan.py` trong image với `--network none`. Chạy container UI cùng image, bind `127.0.0.1:18766:8000`, `BBASM_DATA=/qa/fixture2/data`, `BBASM_TARGETS=/qa/fixture2/targets`, `BBASM_RECON_DISABLED=true`; trên host chạy `python check_ux_ui.py` bằng Playwright headless. Script dùng đường dẫn scratch `E:\code\bbasm\qa_v165`; thay đường dẫn này nếu chạy ở máy khác.

Hồi quy backend dùng image QA, source mount read-only tại `/app` và bản sao vendor đã chuẩn hóa LF tại `/app/vendor/claude-bug-bounty`; không có request mạng (`--network none`). Lượt “không có tool” đổi tên binary **chỉ trong container dùng một lần**, không thay đổi host hay image. Hồi quy frontend chạy trong `frontend/` của checkout `976e1c3`.

## Finding và kết luận

**UX-1 PASS.** Hai finding P2 của `test/v164-host-audit@3379dfd` đều không còn tái hiện được. Không phát hiện finding mới trong phạm vi này. Không sửa code sản phẩm, DB hoặc targets của người dùng.
