# Audit luồng input → scan → output

Ngày: 2026-10-16. Base: `2d540fd` (`fix/path-out-safe-scan`). Đây là review logic và tái hiện bằng DB/file tạm trên máy cục bộ. Không gọi HackerOne, không scan host ngoài, không thay đổi stack/dữ liệu đang chạy. Mức độ ưu tiên là đề xuất để người triển khai xác minh lại.

## Phạm vi đã xem

Review chọn scope và cấu hình; API Resolve/Review/Launch/Rescan/Schedule; lưu snapshot và policy; scope gate và dựng lệnh recon; ingest URL/asset; xuất ZIP. Chưa chạy scan thật để xác nhận tác động vận hành của mọi finding. Các kết luận ghi rõ khi mới dựa trên đường code.

## Đánh giá logic IN/OUT theo đường dẫn đã sửa ở `2d540fd`

Trường hợp gốc: `wolt.com` là IN, còn URL như `https://wolt.com/en/wolt-for-work-contact-request` là OUT. OUT này phải chặn chính đường dẫn và các đường dẫn con, không biến cả `wolt.com` thành OUT. Đồng thời các công cụ active không được truy cập OUT trước khi kết quả bị lọc.

**Làm rõ sau QA công cụ thật:** câu “không được truy cập OUT” ở trên là giả định an toàn của cách triển khai hiện tại, không phải diễn giải chung cho mọi policy. Bản policy Wolt đã lưu có ba endpoint OUT ghi rõ không gửi POST vì dữ liệu tới bên thứ ba, còn hai endpoint OUT khác không có ghi chú này. Các request QA đều là GET. Cần đọc instruction theo từng asset để tách phạm vi finding khỏi quyền gửi GET/POST; xem `PATH_OUT_REAL_TOOLS_RESULTS.md`.

Thay đổi ở `2d540fd` nhìn chung giải quyết đúng hướng:

1. `scope_gate.py` lưu OUT dạng `(host, path)`, so khớp path đã chuẩn hóa, giữ host và path khác trong IN. `ingest.py` loại URL thuộc path OUT khỏi DB và ghi số `path_rule_blocked`.
2. `recon_orch.py` chuyển host có path OUT sang probe-only, tắt crawl/nuclei/ffuf/nmap cho host đó, không đưa host vào deep pass; tùy chọn legacy `allow_active_on_path_rules=true` không mở lại các bước này. Probe root không theo redirect.
3. `safe_path_probe.py` chỉ GET tối đa 50 URL đơn giản đã biết, qua scope gate, không query/fragment, không theo redirect, không lấy body; `monitors.py` loại host có path OUT khỏi các tác vụ có thể gửi request ngoài kiểm soát.

Kiểm thử hiện có: `.venv/Scripts/python.exe -m pytest -q backend/tests/test_v13_path_rules.py backend/tests/test_monitors.py --basetemp .pytest-audit-path-escalated --tb=short` → **15 passed** trên Windows với fixture HTTP `127.0.0.1` (chạy ngoài sandbox socket; lần chạy trong sandbox có 14 passed, 1 failed vì fixture không nhận request). Không scan Wolt hoặc host ngoài.

**Cần Claude review độc lập trước khi coi là đóng lỗi:**

- Truy vết mọi lệnh có thể chạm target (httpx/curl/katana/nuclei/ffuf/nmap, JS/secrets, takeover và tool con) để xác nhận probe-only và cờ no-redirect được tuân thủ thực tế, không chỉ trong plan/env.
- Test fixture localhost ghi mọi request đến path OUT, kể cả redirect, path mã hóa, khác hoa/thường, slash kép, dấu chấm, query, port và URL lấy từ lịch sử. Phân biệt lọc output với chặn request thực tế.
- Xác minh path OUT trên host IN không bị mất toàn bộ URL IN cùng host ở ingest, Diff, Brief, ZIP; ZIP filtered có F2 nên chưa thể xem là an toàn.
- Đối chiếu UI Review/Run: người dùng phải thấy rõ host đó chỉ probe và các bước active bị bỏ qua; `safe_path_probe` chỉ kiểm URL IN đã biết, không tương đương crawl đầy đủ.
- Kiểm tình huống F1: một path hoặc host bị người dùng bỏ chọn có được đưa trở lại khi Rescan/schedule hay không. Đây là vấn đề khác với việc parser hiểu đúng URL OUT.

| Mã | Ưu tiên | Finding | Bằng chứng | Trạng thái |
| --- | --- | --- | --- | --- |
| F1 | P1 | Asset bỏ chọn ở Review không được giữ cho lần Scan lại/lịch chạy | `Review.tsx:183` ghi vào `config.excluded_hosts`; `runner.py:192` lưu toàn bộ `resolved_scope` vào `scope_rule`; `scope_resolver.py:125` tạo config mới không kế thừa `excluded_hosts`; `programs.py:231` rescan từ toàn bộ `scope_rule`. | Tái hiện bằng DB tạm; tác động lên scheduler suy ra từ code. |
| F2 | P1 | ZIP `filtered` có thể chứa URL/host OUT | `export.py:18-44` dùng `URL_OR_HOST.search(line)` (chỉ match đầu) rồi ghi nguyên dòng; dòng không match được giữ. `Program.tsx:479` gọi chế độ này là an toàn để chuyển cho người khác. | Tái hiện bằng file tạm. |
| F3 | P1 | Scheduler không kiểm lại `launch_gate` khi dispatch Light/Strong | `programs.py:195-229` kiểm gate khi bật lịch; `scheduler.py:62-100` khi tick chỉ kiểm config và required headers trước khi tạo scan. Policy program có thể được cập nhật bởi Resolve (`scope_resolver.py:211`). | Kết luận tĩnh; cần test tích hợp. |
| F4 | P2 | Review của draft cũ lấy policy mới của program | `scope_resolver.py:211` cập nhật `program.policy_json` khi tạo draft mới; `runner.py:207-236` lấy scope/gate của draft nhưng policy/hints/trust từ program hiện tại. | Tái hiện bằng DB tạm. |
| F5 | P2 | Mẫu OUT glob hợp lệ bị từ chối trong cấu hình scan | `scope_gate.py:78` hỗ trợ `normalize_pattern(value, deny=True)` nhưng `runner.py:145-151` gọi không có `deny=True` cho `excluded_hosts`. | Tái hiện bằng hàm cục bộ. |

## Cách tái hiện tối thiểu

### F1: lựa chọn scope không sống qua lần scan sau

1. Resolve raw scope gồm `a.example.com`, `b.example.com` (không scan hai host này).
2. Trong Review, bỏ chọn `b.example.com`, launch với cấu hình có `excluded_hosts=["b.example.com"]`.
3. Đọc `scope_rule` của program rồi tạo draft `rescan`: `scope_rule` vẫn có cả hai host; draft mới có `excluded_hosts=[]` nếu không có profile tùy chỉnh. Lịch chạy đọc `scope_rule` và config của lịch, nên cần kiểm trường hợp lịch được bật sau bước 2.

Tái hiện cục bộ phần lưu snapshot và config: `SAVED_SCOPE_AFTER_LAUNCH ['a.example.com', 'b.example.com']`; `NEXT_DRAFT_CONFIG_EXCLUDED []`. Rủi ro: host đã được bỏ chọn có thể được quét ở lần sau mà người dùng không nhận ra. Hướng sửa: xác định lựa chọn Review là scope hiện hành hay chỉ áp dụng cho một scan; lưu/persist rõ ràng theo quyết định đó, và hiển thị lại trước mọi lần chạy.

### F2: ZIP filtered lọt OUT

Input file recon: `https://in.example/a https://out.example/b` trên một dòng. Với gate cho phép URL đầu, `_filtered_copy` trả `lines_kept=1, lines_dropped=0` và output vẫn chứa `https://out.example/b`. Dòng không có token domain/URL cũng được giữ. Hướng sửa: kiểm tất cả URL/host trên một bản ghi; với JSON/CSV cần parse theo cấu trúc hoặc bỏ bản ghi không thể xác định an toàn. Thay mô tả UI cho đến khi bộ lọc được kiểm chứng.

### F3: lịch không kiểm lại gate

1. Tạo program H1 giả qua provider mock, policy/scope đầy đủ; bật lịch Light.
2. Resolve lại cùng program với policy thiếu hoặc OUT chưa phân loại.
3. Kích hoạt tick lịch trên DB tạm. Kỳ vọng nên là từ chối scan với `scope_incomplete`. Hiện `dispatch` không gọi `require_gate`, nên cần chạy integration test để xác nhận tác động chính xác. Hướng sửa: kiểm gate trên snapshot metadata đang dùng ngay trước khi queue, ghi lỗi/lý do lên lịch.

### F4: draft policy không đồng nhất

Resolve hai lần cùng raw scope và cùng tên program, lần lượt với `policy_text=POLICY_ONE` và `POLICY_TWO`. Đọc Review của draft thứ nhất trả `policy.user_text=POLICY_TWO`. Với H1, snapshot `launch_gate` cũ và `request_header_hints` mới cũng có thể không khớp. Hướng sửa: lưu policy snapshot theo scan/draft, dùng cùng snapshot cho Review, header gate và launch; quyết định cách thông báo khi policy mới hơn draft.

### F5: validate glob không nhất quán

`normalize_pattern('api*.example.com', deny=False)` ném `ValueError: invalid domain`; cùng input với `deny=True` trả `api*.example.com`. `ScopeGate` nhận mẫu này để loại trừ, còn `JobRunner._validate` chặn cấu hình. Hướng sửa: dùng cùng quy tắc normalize cho các mẫu OUT do người dùng thêm, đồng thời kiểm URL path OUT riêng.

## Cần Claude đánh giá trước khi sửa

- Kiểm lại mức ưu tiên và ý nghĩa sản phẩm của lựa chọn bỏ chọn asset: áp dụng cho một lần scan hay trở thành scope của program? UI hiện ghi “Sau khi chạy, scope đã chọn trở thành scope hiện hành”, nên F1 đang được đánh giá theo cam kết này.
- Với F2, phân biệt “lọc bản ghi” và “biên tập nội dung”. Cần test các định dạng recon thực tế, nhiều token trên một dòng, IP, URL path OUT, JSONL/CSV.
- Với F3/F4, thêm integration test trên DB tạm; xác nhận policy của scan đang chạy không bị draft mới thay đổi giữa chừng.
- Chỉ sửa code sau khi xác nhận bằng test hồi quy. Không dùng dữ liệu scan hoặc H1 thật để tái hiện năm finding này.
