# BBASM — audit toàn luồng, gộp AUDIT-2

Nguồn được kiểm: `claude/upbeat-thompson-b7bb23@cadf804`, submodule `vendor/claude-bug-bounty@ccae299`. Nhánh báo cáo: `test/v171-host-audit`. Báo cáo này gộp phép thử mới với [AUDIT-2](V171_HOST_AUDIT.md); không sửa code sản phẩm. Mọi phép tái hiện dùng DB tạm, fixture và container `--network none`. Không quét host ngoài, không gọi HackerOne, không đụng stack `bbasm-v12` hoặc dữ liệu người dùng.

## Kết luận

Luồng cơ bản Resolve → Review → Launch → recon → ingest → rank/diff/brief → Data/Run hoạt động và có nhiều chốt an toàn hữu ích: input được chuẩn hóa, lệnh subprocess dùng argv/quote, scan chủ động có xác nhận, kết quả qua scope gate, API log không ghi body, health và các tab dữ liệu đã tách rõ. Tuy nhiên, **scope gate chưa bao kín mọi request trong engine**, các tác vụ dài còn tranh khóa SQLite, và API xem lịch sử URL chưa xác thực scan như các API kết quả khác. Đây là các điểm cần ưu tiên hơn việc thêm tính năng mới.

| Luồng | Đã kiểm | Đánh giá |
| --- | --- | --- |
| Input và Resolve | Raw/H1, scope, slug, header, OUT, YAML tùy chỉnh; provider H1 giả có độ trễ | Không tái hiện shell injection bằng payload đã thử. Resolve H1 giữ write lock khi chờ provider. |
| Review/Launch/Schedule | Config, xác nhận quét, lưu lịch, khởi động lại app với cap thay đổi | Chốt Launch có; lỗi lưu config ở Review đã ghi backlog. Một lịch lỗi thời có thể làm toàn app không khởi động. |
| Recon và scope | Shim auth, URL lịch sử, JS fetch, custom nuclei | URL JS ngoài scope có thể nhận request và header trước khi backend lọc; DNS template cố định chưa bị chặn. |
| Ingest/Rank/Diff/Brief | Đường ghi DB, rank đồng thời, so baseline, cập nhật policy | Rank lock có thể khiến scan kẹt `running` (đã tái hiện); các giới hạn Diff/PROGRAM.md đã ghi ở AUDIT-1. |
| API và UI kết quả | Assets/Findings so với URL list/summary/tree/export; test frontend | URL `scan=` không hợp lệ vẫn trả 200/dữ liệu cũ. UX lịch sử còn dễ hiểu nhầm dữ liệu snapshot là dữ liệu scan riêng. |
| Hồi quy | Pytest, Vitest, typecheck, build | Backend **475 passed, 33 deselected**; Vitest **96 passed**; `tsc --noEmit` và build PASS. Build cảnh báo một bundle JS 523,86 kB. |

## Finding đã xác nhận

### P1 — Fetch JS ngoài scope có thể mang header nghiên cứu viên (`AUDIT-2`)

**Tái hiện:** `review_evidence/audit2_input_probe.py` cho fake `gau` trả URL `.js` của `127.0.0.2`, scope chỉ có `a.localhost`. Fake `curl` nhận hai lệnh fetch URL ngoài scope, cả hai có header `X-QA-Research: qa-marker`. Không có request mạng thật.

**Nguyên nhân:** `vendor/claude-bug-bounty/tools/recon_engine.sh` dùng URL lịch sử để tải JS trước khi backend ingest áp dụng ScopeGate. **Sửa:** kiểm host/path OUT và redirect tại chỗ phát request, rồi mới gắn header; thêm fixture hai loopback để chặn hồi quy.

### P1 — Rank giữ khóa ghi có thể để scan kẹt `running` (`AUDIT-2`)

**Tái hiện:** `review_evidence/audit2_lock_probe.py` chạy `rank_program` thật và `_finalize` trên kết nối khác. Rank giữ khóa 35 giây làm lần ghi đầu lỗi sau 30,09 giây. Với timeout DB rút còn 0,15 giây để thử đủ retry, cả hai scan và nhánh ghi `failed` dự phòng đều lỗi, trạng thái vẫn `running`. Cơ chế đã được chứng minh; chưa thể khẳng định duy nhất đó là nguyên nhân scan #67 cũ.

**Sửa:** tính điểm ngoài write transaction, cập nhật theo lô ngắn; không để thread rank tiếp tục giữ lock sau timeout; khôi phục scan mồ côi khi khởi động.

### P1 — Resolve H1 giữ write lock SQLite trong khi chờ nguồn metadata (mới)

**Tái hiện:** `review_evidence/full_flow_resolve_lock_probe.py` dùng provider giả chờ trên event, không gọi H1. Khi provider đang chờ, một giao dịch ghi program khác lỗi `OperationalError` sau busy timeout fixture 0,15 giây. `review_evidence/full_flow_resolve_lock_output.txt` ghi kết quả. Đây là phép đo cơ chế; chưa đo thời gian chờ thường gặp của H1 thật.

**Nguyên nhân:** `ScopeResolver.resolve` bắt đầu `BEGIN IMMEDIATE` trước `provider.resolve`. Với timeout SQLite mặc định dài hơn, các thao tác ghi khác có thể đợi lâu, gồm ghi trạng thái scan/schedule. **Sửa:** lấy metadata trước transaction; chỉ khóa DB ngắn khi kiểm tra/trình tự cấp slug và lưu kết quả, xử lý race khi hai resolve cùng tên.

### P1 — Một lịch có config cũ không hợp lệ làm backend không khởi động (mới)

**Tái hiện:** `review_evidence/full_flow_startup_probe.py` lưu lịch Strong với `scan_timeout=7200` khi cap là 7200; khởi động lại cùng DB tạm với cap 2700. Lifespan app ném `ScopeError: scan_timeout exceeds configured depth hard limit`; `/api/health` không phục vụ được. Kịch bản tương ứng với đổi cấu hình triển khai hoặc nâng cấp làm cap thấp hơn.

**Nguyên nhân:** `ScanScheduler.start()` xác thực từng lịch rồi để lỗi của một lịch thoát ra khỏi startup. **Sửa:** cô lập từng lịch lỗi, vô hiệu hóa nó và lưu `last_error`, tiếp tục khởi động các lịch còn lại và API; hiển thị cảnh báo để người dùng sửa lịch.

### P2 — `scan=` của URL không xác thực scan thuộc program và đã hoàn tất (mới)

**Tái hiện:** `review_evidence/full_flow_url_selector_probe.py` tạo hai program loopback, một URL của scan #1, một draft #3. Với `scan=` là scan #2 của program khác, draft #3 hoặc ID không tồn tại, `/urls`, `/urls/summary`, `/urls/tree`, `/urls/export` đều trả 200 và vẫn có URL scan #1; `/assets` cùng tham số trả 422. `summary/tree.scan_id` vẫn là #1. Output chi tiết: `review_evidence/full_flow_url_selector_output.txt`.

**Nguyên nhân:** `_url_scope` chỉ chuyển chuỗi thành số, không gọi bộ kiểm `_selected_completed_scan` đã dùng cho Assets/Findings. Đây là **gắn sai dữ liệu cũ với lựa chọn scan**, chưa quan sát thấy dữ liệu program khác bị lộ. **Sửa:** dùng cùng kiểm tra program/status cho mọi endpoint URL, trả 422 khi ID sai, và cho `scan_id` trong summary/tree khớp scan đã chọn.

### P2 — Custom nuclei DNS template có thể nhắm tên cố định ngoài scope (`AUDIT-2`)

**Tái hiện:** `review_evidence/audit2_input_probe.py` nhập YAML `dns: [{name: other.localhost, type: A}]`; API và `nuclei -validate` thật đều chấp nhận. Chưa chạy template để quan sát DNS query. **Sửa:** kiểm mọi trường template định địa chỉ đích khi import và tại launch, hoặc chỉ cho phép biến target; không dựa riêng vào `nuclei -validate` để xác nhận scope.

## Việc đã ghi trước trong BACKLOG, chưa được sửa ở commit kiểm tra

Các mục dưới đây là **giới hạn/finding đã biết**, không tính là phát hiện mới trong vòng này:

1. **P1 dữ liệu đúng:** AUDIT-1 ghi findings nuclei cùng host/template nhưng khác URL bị gộp; Diff bỏ qua scan `done` có `observations={}` khi chọn baseline; `PROGRAM.md` có thể còn policy cũ sau resolve lại. Cần test hồi quy với dữ liệu nhiều scan và policy thay đổi.
2. **P2 an toàn và thao tác:** ScopeGate với `repo:` rút gọn thành host, cần kiểm chính sách repo/thư mục ở tất cả bước; Review nuốt lỗi auto-save config khiến checkbox trông như đã lưu. Những việc này đang ở `BACKLOG.md`.
3. **Độ phủ recon:** ffuf chỉ dò 2/5 host đầu; katana lấy tối đa 50 URL đầu, config check/JS cũng có giới hạn. Run nên hiện số được xử lý/số đủ điều kiện và lý do dừng; người dùng cần chỉnh giới hạn trong config. Nuclei đã bỏ giới hạn 50/200 URL và có coverage, không tính lỗi cũ.
4. **Lịch sử dữ liệu:** các bảng tổng hợp dùng first/last seen để suy ra trạng thái theo scan, không giữ snapshot bất biến đầy đủ; brief và ZIP hiện hành không tái dựng chính xác bản ở scan cũ. Giao diện nên phân biệt rõ “từng thấy tính đến scan #N” với “thu được trong scan #N” và liên kết sang output thô của lượt đó.

## Thứ tự xử lý đề xuất

| Ưu tiên | Việc | Tiêu chí đóng |
| --- | --- | --- |
| 1 | Chặn request/header ra ngoài scope tại engine; ràng buộc template tùy chỉnh | Fixture hai loopback không nhận request ngoài scope kể cả JS lịch sử/redirect; YAML định địa chỉ cố định bị từ chối hoặc được gate lúc chạy. |
| 1 | Rút ngắn transaction rank/Resolve; bảo vệ startup scheduler | Hai scan đồng thời đều về trạng thái cuối; provider chậm không khóa DB; một lịch lỗi không làm mất `/api/health`. |
| 2 | Đồng nhất bộ chọn scan của URL và lưu snapshot hợp nghĩa | Scan khác program/draft/không tồn tại trả 422; API/UI nói rõ “dữ liệu scan này” hay “đã biết đến thời điểm này”. |
| 2 | Sửa dữ liệu Diff/PROGRAM.md/nuclei dedup và lỗi auto-save đã có trong backlog | Regression tương ứng của AUDIT-1 và UI Review qua API thật. |
| 3 | Minh bạch độ phủ từng tool và cải thiện Data/Run UX | Run nêu X/Y host, URL, template, request và trạng thái partial; người dùng tìm được output đúng scan mà không phải đoán. |

## Lệnh và giới hạn kiểm chứng

```powershell
docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm_v171qa:/qa:ro' -w /qa bbasm-v12-bbasm:latest -m review_evidence.full_flow_url_selector_probe
docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm_v171qa:/qa:ro' -w /qa bbasm-v12-bbasm:latest -m review_evidence.full_flow_startup_probe
docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm_v171qa:/qa:ro' -w /qa bbasm-v12-bbasm:latest -m review_evidence.full_flow_resolve_lock_probe
docker run --rm --network none --entrypoint python -v 'E:\code\bbasm\advance_asm_v171qa:/qa:ro' -w /qa bbasm-v12-bbasm:latest -m pytest -q -m 'not integration'
# Trong checkout khác cùng commit cadf804, có node_modules sẵn:
cd E:\code\bbasm\advance_asm_local\frontend
npm test
npx tsc --noEmit
npm run build
```

Không chạy scan end-to-end tới host thật hoặc Docker integration vì phạm vi chỉ fixture/localhost và không đụng stack đang dùng. Không xác nhận xác suất các race/lock trên DB lớn; fixture rút busy timeout để tái hiện điều kiện. Không chứng minh mọi biến thể YAML/URL an toàn. Build frontend PASS nhưng còn cảnh báo bundle >500 kB; đây là cơ hội tối ưu tải trang, chưa đo trải nghiệm trình duyệt trong vòng này.
