# AUDIT-2 — đầu vào người dùng và khóa SQLite

Nguồn: `claude/upbeat-thompson-b7bb23@cadf804`, submodule `vendor/claude-bug-bounty@ccae299`. Nhánh QA: `test/v171-host-audit`. `COORD_TASKS.md` ghi AUDIT-2 là **OPEN**, `base_commit=cccaa5d` (tổ tiên trực tiếp của `cadf804`); mô tả của yêu cầu gọi `cadf804` là base. Audit được thực hiện trên `cadf804`.

Chỉ dùng DB/thư mục tạm và fixture loopback trong container `--network none`; không chạy scan tới host thật, không dùng token/cookie, không chạm stack `bbasm-v12`. Không sửa code sản phẩm.

| Mã | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| AUDIT-2/A1 | Kiểm `request_headers` từ API/config → `BBHUNT_AUTH_HEADERS` → `_auth_helper.sh` → argv | **Không tái hiện shell injection** | Chuỗi giả chứa `$(touch ...)` vẫn là một đối số `-H`; file đánh dấu không được tạo. Discovery không mang header; stdout không chứa giá trị. |
| AUDIT-2/A2 | Kiểm header khi URL JS lấy từ nguồn lịch sử nằm ngoài scope | **Finding P1** | Fixture IN `a.localhost`, `gau` trả `http://127.0.0.2/out-of-scope.js`: `recon_engine.sh` gọi `curl` 2 lần tới URL đó, cả 2 mang `X-QA-Research: qa-marker`. URL đi vào `urls/all.txt` trước khi ingest lọc scope. |
| AUDIT-2/A3 | Kiểm YAML tùy chỉnh qua `POST /api/tools/templates/custom` | **Finding P2** | Template DNS có `name: other.localhost` được API nhận HTTP 200; chạy lại với binary `nuclei -validate` thật cũng HTTP 200. Tên DNS cố định không phụ thuộc target. Chưa chạy template để gửi truy vấn DNS. |
| AUDIT-2/A4 | Kiểm `url_exclude_patterns`, `excluded_hosts`, scope, slug/handle và cách tạo lệnh | **Không thấy thực thi lệnh từ payload thử** | Pattern chứa `;` bị từ chối; host OUT sai bị từ chối; ID template sai bị từ chối; slug được chuẩn hóa. Raw scope `127.0.0.1;printf_QA` được tách thành 2 asset (IP + manual asset), không được chuyển thành lệnh shell. Subprocess chính dùng argv riêng và header Bash array có quote. |
| AUDIT-2/B1 | `rank_program` giữ `BEGIN IMMEDIATE` 35 giây, `_finalize` dùng SQLite timeout thật 30 giây | **Tái hiện lỗi khóa; retry phục hồi** | Lần ghi đầu ném `OperationalError` sau 30,09 giây; lần thứ hai thành công sau khi rank nhả khóa; scan thành `done`. |
| AUDIT-2/B2 | Hai scan hoàn tất đồng thời khi rank giữ khóa, rút timeout SQLite còn 0,15 giây để đi hết 4 retry | **Tái hiện scan kẹt `running`** | Cả 8 lần ghi đều `OperationalError`; cả hai `_finalize` ném lỗi sau 6,63 giây. Khi chạy tiếp qua `_worker` thật, cả hai nhánh ghi `failed` dự phòng cũng lỗi `OperationalError`; hai hàng DB vẫn `running`. Fixture đặt `BBASM_MAX_CONCURRENT_SCANS=2`; chưa chạy hai pipeline scan đầy đủ. |

## Finding mới

### P1 — Header nghiên cứu viên gửi tới URL ngoài scope trong bước phân tích JS

**Tái hiện:** chạy `review_evidence/audit2_input_probe.py` trong container không mạng. Fake `gau` trả một URL `.js` thuộc `127.0.0.2` trong khi target IN là `a.localhost`; fake `curl` ghi argv. Cả hai lời gọi đều mang header tùy chỉnh.

**Nguyên nhân:** `recon_engine.sh` đưa URL lịch sử vào `urls/all.txt`, sau đó lấy `.js` và gọi `curl` ở dòng 493–505 cùng `BB_AUTH_ARGS`. Scope gate của backend lọc khi ingest, tức sau hoạt động mạng này. Rủi ro là request ngoài scope và lộ giá trị header/định danh nghiên cứu viên cho host ngoài scope. Việc quote `"$js_url"` ngăn tách argv nhưng không chặn URL ngoài scope.

**Hướng sửa:** kiểm host/scheme và quy tắc path OUT bằng cùng scope gate **trước mỗi fetch active** từ URL do nguồn lịch sử/crawl cung cấp; chỉ gắn header sau khi URL đích được phép. Kiểm cả redirect, endpoint JS, config checks và các nguồn URL tương tự. Thêm test canary bằng hai loopback để khẳng định không gửi request/header ngoài scope.

### P2 — Template DNS tự thêm có thể nhắm tên ngoài target

**Tái hiện:** gửi YAML có `dns: [{name: other.localhost, type: A}]` tới `/api/tools/templates/custom`; nhận HTTP 200 ngay cả khi `nuclei -validate` thật được gọi. Không có truy vấn DNS tới host đó trong audit này.

**Nguyên nhân:** `backend/templates.py::_unsafe` chặn URL tuyệt đối trong chuỗi và TCP host cố định, nhưng không kiểm `dns.name` cố định. Khi được chọn qua `nuclei_custom`, shim thêm file này vào lệnh `nuclei -t` mà không có ràng buộc scope ở cấp truy vấn template.

**Hướng sửa:** buộc `dns.name` dùng biến target được nuclei hỗ trợ hoặc xác thực tên cố định theo scope tại thời điểm chạy; áp dụng cùng nguyên tắc cho mọi trường template có thể định địa chỉ đích. Test validator và lệnh nuclei với DNS fixture loopback.

### P1 — Ghi trạng thái cuối có thể thất bại khi rank giữ write lock quá lâu

**Tái hiện:** `review_evidence/audit2_lock_probe.py` dùng `rank_program` thật, làm `score_asset` ngủ khi transaction `BEGIN IMMEDIATE` đang mở, rồi gọi `_finalize` thật từ kết nối khác. Với timeout SQLite thật 30 giây và rank giữ 35 giây, lần đầu lỗi sau 30,09 giây và retry phục hồi. Với timeout rút 0,15 giây để thử đủ 4 retry trong khi rank vẫn giữ khóa, hai scan đều còn `running`. Phép thử bổ sung chạy `_worker` thật với `_execute` fixture chỉ làm finalize: đường fallback `failed` cũng ném `OperationalError`, hai hàng DB tiếp tục `running`.

**Nguyên nhân:** `rank_program` tính điểm cho mọi asset trong một write transaction. `asyncio.wait_for` dừng chờ `_post(rank)` nhưng không dừng thread SQLite đang chạy; `_finalize` và cả nhánh xử lý lỗi của worker cần write lock đó. Nếu lock kéo dài quá các lần retry, trạng thái cuối không ghi được. Thử nghiệm chứng minh cơ chế; không thể quy kết duy nhất scan #67 cũ vì không có thread dump của lần đó. Hai scan khác program vẫn tranh cùng write lock SQLite.

**Hướng sửa:** tính điểm ngoài transaction ghi và cập nhật thành lô ngắn; để thread rank có cơ chế dừng/cooperative cancellation khi quá hạn; có đường ghi trạng thái cuối riêng sau khi transaction được giải phóng và recovery khi khởi động cho scan `running` mồ côi. Kiểm lại 2 pipeline đồng thời với DB fixture lớn.

## Phạm vi và lệnh lặp lại

Lệnh trong worktree QA (image chỉ làm runtime, container không có mạng):

```powershell
docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm_v171qa:/qa:ro' -w /qa bbasm-v12-bbasm:latest -m review_evidence.audit2_input_probe
docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm_v171qa:/qa:ro' -w /qa bbasm-v12-bbasm:latest -m review_evidence.audit2_lock_probe
docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm_v171qa:/qa:ro' -w /qa bbasm-v12-bbasm:latest -m review_evidence.audit2_lock_probe --worker-only
```

Output đầy đủ: `review_evidence/audit2_input_output.txt`, `review_evidence/audit2_lock_output.txt`. Binary `curl/gau/httpx` trong fixture A2 được giả lập để **không phát request thật**; nuclei thật chỉ chạy `-validate` cho A3. Không kiểm mọi cách biểu diễn URL/template của nuclei và không đo xác suất lỗi khi hai scan đầy đủ chạy cùng lúc. Không chạy lại toàn bộ pytest/Vitest vì đây là audit chỉ đọc và không có sửa code sản phẩm.
