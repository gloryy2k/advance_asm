# QA UX-1 / ENG-1 — BBASM

## Phiên bản và phạm vi

- `origin/claude/upbeat-thompson-b7bb23` tại `26b6c58`; bảng `COORD_TASKS.md` ghi **UX-1 READY_FOR_QA** (`base=ab9abc4`, `result=6ba098d`) và **ENG-1 READY_FOR_QA** (`base=ab9abc4`, `result=bb17169`, submodule `bfd61ba`). Cả hai result commit đều là tổ tiên của HEAD. API/UI được kiểm trên đúng `6ba098d`; Phase 3 được kiểm trên đúng `bb17169` + `bfd61ba`. Hồi quy chạy trên code gộp của `bb17169`.
- Chỉ dùng DB, nmap/ffuf output giả và localhost. Container API/Phase 3 chạy offline (`--network none`); UI chỉ được mở bằng Playwright headless tại `127.0.0.1:18766` với recon tắt. Không scan host ngoài, không dùng H1/token, không chạm stack `bbasm-v12`.

| ID | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| UX-1 | GET `/api/programs/example.com/ports` và `/dirs` trên 2 scan hoàn tất + 1 draft; `scan=latest`, `scan=<id>`, ID không tồn tại | **PASS cho luồng chuẩn; FAIL tổng thể vì 2 finding bên dưới** | `latest` chọn scan #2: ports **8 cặp/3 host/7 cổng khác nhau**, `complete=false`, `cdn_pairs=7`; dirs **35 phản hồi, 33 nhiễu, 2 đáng xem**, có host chỉ 403. `scan=1` trả dữ liệu riêng: ports **2 cặp/1 host**, dirs **1 phản hồi**. Draft trống, scan không tồn tại và program chưa có scan hoàn tất đều `found=false`. |
| UX-1 | Mở hai tab Dữ liệu ở 1366px | **PASS cho nội dung, FAIL khi chọn scan cũ** | “Cổng/Dịch vụ” có **8 hàng**, câu **DỞ DANG** và cảnh báo **7 cặp Cloudflare… chưa chứng minh là origin**. “Đường dẫn dò được” hiện **35/33/2**, ghi **403 không chứng minh đường dẫn tồn tại**, chỉ có **2 hàng đáng xem**. Ảnh: [Cổng/Dịch vụ](review_evidence/v164_qa/ports_latest_1366.png), [Đường dẫn dò được](review_evidence/v164_qa/dirs_latest_1366.png). Khi mở `?v=ports&scan=1`, UI vẫn có 8 hàng/DỞ DANG của scan #2; `?v=dirs&scan=1` vẫn hiện 35 phản hồi của scan #2. |
| ENG-1 | Trích nguyên khối Phase 3 từ `recon_engine.sh` của image, cho hàm nmap fixture viết 2 dòng greppable; host đầu có 3 open port, host sau có 2 (trùng 80), thêm 1 closed | **PASS** | `open_ports.txt` là **80/open, 443/open, 8080/open, 8443/open** (4 cổng khác nhau), log `Open ports: 4`. Không còn chỉ giữ cổng cuối mỗi dòng. Không chạy nmap thật hoặc kết nối mạng. |
| Hồi quy | `python -m pytest -q -m "not integration"` trong image Linux, source mount read-only; `npx vitest run`, `npx tsc --noEmit`, `npm run build` | **PASS** | Backend **457 passed, 33 deselected, 4 warnings** (53,64 s). Frontend **92 passed**; TypeScript/build exit 0. Vite chỉ cảnh báo bundle JS 515,36 kB vượt ngưỡng 500 kB. |

## Finding mới (không sửa code)

### UX-1 · P2 · Hai tab bỏ qua scan đã chọn

**Tái hiện:** trên DB fixture có scan #1 (2 cổng, 1 ffuf result) và scan #2 (8 cổng, 35 ffuf responses), mở `http://127.0.0.1:18766/#/program/example.com/data?v=ports&scan=1`, rồi `...?v=dirs&scan=1`. API `/ports?scan=1` và `/dirs?scan=1` trả đúng scan #1, nhưng UI vẫn gọi `/ports` và `/dirs` không kèm `scan`, nên hiển thị scan #2. Câu giới thiệu của tab Cổng/Dịch vụ nói “scan gần nhất (hoặc scan bạn chọn)” nhưng không thể xem scan được chọn ở đây. **Hướng sửa:** truyền `scan` từ `routeParams()` vào `PortsView`/`DirsView`, giữ tham số khi đổi tab, hiển thị rõ số scan đang xem; thêm test với hai scan có số liệu khác nhau.

### UX-1 · P2 · Draft có output mồ côi được công bố như kết quả scan

**Tái hiện:** giữ scan #3 ở trạng thái `draft`, đặt `4/ports/nmap_greppable.txt` và `4/dirs/ffuf_orphan.json` trong thư mục output fixture của nó. GET `/api/programs/example.com/ports?scan=3` trả `found=true`, `pairs=1`; `/dirs?scan=3` trả `found=true`, `total=1`, dù scan chưa launch. Draft **không có file** trả `found=false` như kỳ vọng. **Hướng sửa:** khi `scan=<id>`, `_resolve_scan_id` phải kiểm trạng thái scan; ít nhất từ chối `draft` trước khi đọc output. Nếu muốn hỗ trợ xem kết quả dở dang của scan đang chạy, định nghĩa rõ trạng thái được phép và phân biệt với scan hoàn tất.

## Bằng chứng tái hiện

- Script fixture/API: [`check_ux_api.py`](review_evidence/v164_qa/check_ux_api.py), edge case draft: [`check_ux_draft_orphan.py`](review_evidence/v164_qa/check_ux_draft_orphan.py).
- Playwright headless: [`check_ux_ui.py`](review_evidence/v164_qa/check_ux_ui.py). Ảnh chỉ chứa dữ liệu giả và được chụp ở 1366px.
- ENG-1: [`check_eng_phase3.py`](review_evidence/v164_qa/check_eng_phase3.py), chạy trong image `bbasm-v164eng-bbasm` offline bằng `docker run --rm --network none --entrypoint python --mount "type=bind,source=E:\code\bbasm\qa_v164,target=/qa" bbasm-v164eng-bbasm /qa/check_eng_phase3.py`.
- Bộ pytest đầu tiên gọi thẳng trong image thiếu module `scripts` vì Dockerfile không copy module này; lượt hồi quy đúng mount source repo read-only và bản sao vendor đã chuẩn hóa LF. Kết quả 457 passed ở trên là lượt đúng.

**Kết luận:** ENG-1 **PASS**. UX-1 **FAIL** do hai lỗi P2 khi chọn scan cũ và khi draft có output mồ côi; các đường đọc và câu chữ trong luồng chuẩn đã PASS. Không sửa code sản phẩm hoặc bảng phối hợp.
