# AUDIT-1 — audit luồng dữ liệu BBASM

Nguồn: `claude/upbeat-thompson-b7bb23` tại `c596bc9` (18/10/2026); `d954726` là tổ tiên của HEAD. Gitlink `vendor/claude-bug-bounty` là `ccae299`. Báo cáo này nằm trên nhánh QA `test/v169-host-audit`; không sửa code sản phẩm. Toàn bộ phép thử dùng SQLite tạm và `127.0.0.1`, không gọi H1 hay scan host ngoài.

Đã đọc hàng `AUDIT-1` trong `COORD_TASKS.md` và `BACKLOG.md`. Không tính lại các vấn đề Claude đã ghi: giới hạn/phase trong `recon_engine.sh`, scan kẹt `running` khi finalize lỗi, và Review nuốt lỗi lưu config. Các finding dưới đây là đường lỗi khác hoặc cơ chế cụ thể mới được đo. Script tái hiện: `review_evidence/audit1_repro.py`; output nguyên văn: `review_evidence/audit1_output.txt`.

## Kết quả ngắn

| Mã | Ưu tiên | Khu vực | Kết quả |
| --- | --- | --- | --- |
| AUDIT-1/F1 | P1 | Ingest finding nuclei | 2 URL khớp cùng template trên cùng host chỉ còn 1 finding; mất URL đầu. |
| AUDIT-1/F2 | P1 | Diff baseline | Scan `done` với `observations={}` bị bỏ qua; scan sau đối chiếu nhầm scan cũ, bỏ sót host xuất hiện lại. |
| AUDIT-1/F3 | P1 | PROGRAM.md | Resolve lại cùng program với policy mới cập nhật DB nhưng file agent vẫn giữ policy cũ. |
| AUDIT-1/F4 | P2 | Ranking/SQLite | Truy vấn URL cho từng asset quét toàn bảng; rank giữ khóa ghi cho cả lượt. Đây là cơ chế có thể góp phần timeout/kẹt, chưa chứng minh là nguyên nhân duy nhất của #67/#68. |
| AUDIT-1/F5 | P2 | ScopeGate | Quy tắc IN `github.com` cho phép `repo:https://github.com/other/repo` ở gate dù repo cụ thể không nằm trong scope. Chưa chứng minh planner tự sinh lệnh cho repo lạ. |

## Bằng chứng và hướng sửa

### AUDIT-1/F1 — hai phát hiện nuclei bị gộp theo host/template

`backend/jobs/ingest.py` lấy `matched-at` vào `detail_json`, nhưng khóa duy nhất `finding(program_id,type,name,asset_id)` trong `backend/schema.sql` không chứa URL. UPSERT của finding ở `ingest.py` ghi đè `detail_json` khi cùng template khớp URL thứ hai. `stats.findings` cũng đếm theo cùng khóa. Fixture 2 dòng `fixture-template` tại `http://127.0.0.1/one` và `/two`: DB chỉ còn 1 dòng và chỉ giữ `/two`; `stats.findings=1`.

Tái hiện: chạy script bên dưới, xem dòng `NUCLEI`. Kỳ vọng giữ 2 địa điểm khớp hoặc 1 finding có danh sách cả 2 địa điểm và số đếm tương ứng. Hướng sửa: định danh finding bằng template + URL chuẩn hóa (hoặc bảng match con), migration giữ dữ liệu cũ; đồng bộ phần đếm/API/Brief, và test 2 đường dẫn cùng host.

### AUDIT-1/F2 — scan hoàn tất nhưng rỗng không được dùng làm baseline

`backend/asm/diff_engine.py::_baseline_from_scan` chọn scan `done/done_partial` gần nhất chỉ khi `observations` là dict **và không rỗng**. Fixture: scan #1 có host `127.0.0.1`; scan #2 `done` có `observations={}` (host đã gone); scan #3 thấy host trở lại. `capture` chọn baseline #1 thay vì #2, `apply` trả `new=0, changed=0, gone=0`. Event `changed` cho host trở lại bị mất, mặc dù asset trong DB đang `state='gone'`.

Tái hiện: xem dòng `DIFF`; `empty_completed=2`, `chosen_baseline=1`. Hướng sửa: phân biệt **observations đã được lưu nhưng rỗng** với scan cũ thiếu trường observations; scan hoàn tất/rỗng vẫn là baseline hợp lệ. Bổ sung regression 3 scan có status `done`, gồm lượt giữa rỗng.

### AUDIT-1/F3 — policy trong file agent cũ hơn DB/UI

`backend/jobs/scope_resolver.py` cập nhật `program.policy_json` khi resolve lại cùng slug. `backend/brief/generator.py::ensure_program` và `generate` chỉ ghi `PROGRAM.md` nếu file chưa tồn tại, vì file được phép chỉnh tay. Fixture resolve raw scope `127.0.0.1` với `POLICY_VERSION_A`, tạo PROGRAM.md, rồi resolve lại cùng slug với `POLICY_VERSION_B`: DB chứa B, file vẫn chứa A và không có B. Nếu agent đọc file này để quyết định scope/policy, nó có thể hành động theo bản cũ.

Tái hiện: xem dòng `POLICY`. Hướng sửa: tách phần policy/scope do hệ thống quản lý khỏi phần ghi chú người dùng, cập nhật phần quản lý có kiểm soát phiên bản; nếu có xung đột nội dung tự sửa, hiện cảnh báo rõ trong UI và không dùng file cũ như nguồn hiện hành.

### AUDIT-1/F4 — ranking N+1 full scan và giữ khóa ghi

`backend/asm/ranking.py::rank_program` bắt đầu `BEGIN IMMEDIATE` trước vòng qua toàn bộ asset. Mỗi asset gọi `SELECT url FROM url WHERE asset_id=? AND last_seen_scan=?`; schema và migrations không có index trên cặp cột đó. Fixture 700 asset/20.000 URL: SQLite báo `SCAN url` cho truy vấn; lượt rank mất **0,492 s**. Thêm index chỉ trong DB tạm thì báo `SEARCH url USING INDEX ...` và còn **0,080 s** (~6,2 lần nhanh hơn). Dữ liệu thật, ổ đĩa và mật độ URL sẽ cho thời gian khác; đây không phải benchmark Docker.

`backend/jobs/runner.py::_post` dùng `asyncio.wait_for` quanh `_thread`/executor. Hết hạn chờ không dừng được thread đang chạy. Fixture làm `score_asset` chậm có chủ đích: hủy future đang chạy trả `false`; một kết nối SQLite khác không thể ghi trạng thái cuối khi rank giữ transaction, nhưng ghi được sau khi thread kết thúc. Đây là cơ chế lock được tái hiện, **không phải bằng chứng nguyên nhân chính xác** của timeout 300 s ở scan #67/#68.

Tái hiện: xem hai dòng `RANK`, `LOCK`. Hướng sửa: index đúng theo truy vấn hoặc gom/batch dữ liệu một lần; rút transaction ghi xuống giai đoạn UPDATE, tránh xử lý tính điểm bên trong khóa; khi timeout, đừng coi worker là đã dừng cho tới khi nó thật sự kết thúc hoặc có cơ chế hủy hợp tác. Đo lại bằng bản sao DB lớn sau sửa.

### AUDIT-1/F5 — repo bị rút thành host ở ScopeGate

`backend/scope_gate.py::in_scope` gọi `normalize_pattern(target.removeprefix('repo:'))`, làm URL repo thành host `github.com`. Với IN=`github.com`, gate trả `true` cho `repo:https://github.com/other/repo`. Một program chỉ cho phép web `github.com` không đồng nghĩa cho phép mọi source repo trên host đó. Fixture trực tiếp ghi `other_repo_allowed=true` trong dòng `SCOPE`.

Hướng sửa: so `repo:` bằng định danh repo chuẩn hóa riêng, không cho nó thừa hưởng quy tắc host/web; giữ kiểm tra repository con/đường dẫn riêng. Planner hiện tạo command từ asset source code đã resolve; báo cáo này chỉ xác nhận sai ở gate độc lập, chưa xác nhận có lệnh thực sự nhắm repo ngoài scope.

## Phạm vi đã xem và giới hạn

- Đọc luồng `scope_resolver → scope_gate → recon_orch → ingest → diff → rank → brief`, schema/migrations, `runner.py`/`db.py`, `UrlExplorer.tsx` và `SitemapTree.tsx`. URL DB có unique `(program_id,url)`; chưa tìm được bằng chứng mất URL do dedup ở frontend. `SitemapTree.more()` không kiểm generation sau fetch trong khi các fetch khác có, nên có khả năng trộn trang cũ sau đổi filter; chưa có fixture browser xác nhận, **không tính là finding**.
- Không chạy scan thật, không dùng DB người dùng, không benchmark full stack. Script tái hiện mở DB tạm rồi tự dọn. QA worktree chưa khởi tạo submodule; script dùng checkout vendor khác trên máy đã xác nhận đúng gitlink `ccae299`.
- Lệnh chạy: `E:\code\bbasm\advance_asm\.venv\Scripts\python.exe -m review_evidence.audit1_repro E:\code\bbasm\advance_asm_local\vendor\claude-bug-bounty` từ gốc nhánh QA. Exit code 0; sáu dòng kết quả nằm trong `review_evidence/audit1_output.txt`.
