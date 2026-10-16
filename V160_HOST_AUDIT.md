# BBASM v1.6.0 — kiểm chứng host cô lập

Ngày kiểm: 2026-10-16. Nguồn: `claude/upbeat-thompson-b7bb23` tại `d89ae6d` (bàn giao), code v1.6.0 tại `e456029`. Nhánh QA: `test/v160-host-audit`. Chỉ dùng fixture, dữ liệu giả và `127.0.0.1`; không chạy scan Arc/Wolt/H1, không dùng token/cookie, không chạm stack `bbasm-v12` cổng 18765. Stack QA riêng `bbasm-v160qa` dùng cổng 18793. Không sửa code sản phẩm.

## Kết quả

| Mã | Hành động | Kết quả | Bằng chứng |
| --- | --- | --- | --- |
| T0 | Xác nhận checkout và submodule | PASS | HEAD `d89ae6d`; `git log -8` có `e456029`; worktree QA sạch trước khi thêm báo cáo; submodule `7acb66a`. |
| T1 | `python -m pytest -q -m "not integration"` trong runtime container cô lập, không có binary `nuclei`/`ffuf` thật che fixture | PASS | **445 passed, 33 deselected**, 3 warning, 56,13 s. Không thay đổi image hoặc code sản phẩm; chỉ giấu hai binary trong container tạm. |
| T1b | Cùng bộ test khi image có binary `nuclei`/`ffuf` thật | FAIL | **437 passed, 8 failed**. Bảy test template dùng binary thật thay vì fixture; một test kỳ vọng `missing_tool` cho ffuf nhưng nhận `no_input`. Đây là độ nhạy của test harness với `PATH`, không chứng minh lỗi lúc scan. |
| T2 | `npm ci`, `npx vitest run`, `npx tsc --noEmit`, `npm run build` | PASS | **88 Vitest passed**; TypeScript và build thành công. Vite cảnh báo bundle >500 KB. |
| F1a | `run_repairs` trên bản sao SQLite và `targets/arc-bbp` từ dữ liệu #65 | PASS | Trước: 128 `subjack.txt:candidate` mức High. Sau: 4 `subjack:GEMFURY` mức Medium, 124 mục sạch bị bỏ; `stats.findings` 138→14, `takeover={candidates:4,not_vulnerable:124,unreadable:0}`. Brief đổi SHA256; có `bbasm.db.pre-repair-takeover-20261016T152536`. Lần hai #65 không đổi. |
| F1b | Nhánh repair khi file `subjack.txt` của một program khác vắng mặt | FAIL | DB copy còn 51 finding cũ của Wolt nhưng QA chỉ copy targets Arc; repair hạ 51 mục xuống info, lần gọi hai vẫn trả cùng nhóm, thêm `stats.repairs` và backup. Đây là trường hợp thiếu file nguồn, không phải kết quả kiểm Wolt thật. |
| FN1 | Shim nmap/ffuf với binary thật, fixture HTTP `127.0.0.1:8099` | PASS | nmap `-sT -sV -p 8099`: cổng 8099 mở, kết thúc 6,64 s. ffuf v2.3.0: 1 `/safe` 200; 6 đường dẫn 403 đồng kích thước bị loại; `ffuf.json` có 1 result và `autocalibration=true`. |
| FN1b | Test integration cắt giữa batch probe | PASS | `test_a_batch_cut_off_mid_way...`: 1 passed, 10 deselected, 22,84 s sau khi chuẩn hóa LF của bản vendored trong mount QA tạm, tương tự Dockerfile. |
| FN2–FN4 | Đọc lại output #65 bằng result reader v1.6.0, không scan lại | PASS | nmap: 100 cặp host/cổng, 13 host, 6 cổng khác nhau; `complete=false`; 95 cặp được gắn nhãn CDN. ffuf: 26 dòng thô, 24 nhiễu, 2 đáng xem; output cũ `calibrated=false`. |
| UI | Sitemap với 5.051 URL giả, 4 host, thư mục nhiều cấp và nhánh lớn | PASS | 1366/390 px không cuộn ngang, không JS page error. Tìm `item-4321` ra 1 URL; chọn và bấm “Xem trong cây” mở 69 treeitem, tô URL tương ứng. Ảnh trong `review_evidence/v160_qa/`. |
| UIa | Tab “Đã lưu trữ” với program giả | PASS | Program biến khỏi nhóm hoạt động và xuất hiện ở tab lưu trữ; trang program có nút Khôi phục/Xóa vĩnh viễn. Ảnh `archived-1366.png`. |
| API | `/api/health` trên stack QA | PASS | `ok=true`; JSON vẫn có `h1_api`, `missing_by_depth`, `optional_tools`, `runtime`, `tools` (20 mục). |
| N | Audit tĩnh luồng nuclei và đối chiếu dữ liệu #65 | PARTIAL | 14.036 là template **đã cài**, không phải số đã thực thi. Engine còn giới hạn `nuclei/targets.txt` 50 URL quick/200 URL full; mặc định deep host tối đa 50. #65 truyền 2 URL cho nuclei main và tạo 5 finding thô; deep rỗng sau probe timeout. Chưa có thống kê đáng tin về số template thực chạy hoặc số request. |

## Finding cần Claude Local xem

### P2 — Repair không idempotent khi mất file nguồn

`backend/repair.py::repair_takeover` nhánh `not have_file` đổi severity/detail nhưng giữ `name='subjack.txt:candidate'`. Query đầu hàm vẫn chọn chính các row này ở lần khởi động sau, nên tiếp tục thêm ghi chú `stats.repairs`, tạo backup và thử sinh Brief. Tái hiện: DB có finding tên cũ, bỏ `targets/<slug>/recon/scans/<id>/monitors/takeover/subjack.txt`, gọi `run_repairs` hai lần; lần hai phải là no-op nhưng hiện vẫn trả nhóm đã hạ mức. Hướng sửa: đánh dấu tên/trạng thái đã migrate và thêm test gọi hai lần trong trường hợp không có file. Bản copy QA cố ý chỉ chứa Arc nên đã kích hoạt nhánh này ở 51 row Wolt; không suy ra DB gốc đã mất file đó.

### P2 — Test phụ thuộc binary trên `PATH`

Khi image có `nuclei`/`ffuf` thật, 8 test dùng fixture/giả định “thiếu tool” bị sai; khi giấu binary trong container test tạm, đủ 445 pass. Hướng sửa: fixture cô lập tool path hoặc inject discovery rõ ràng cho từng test; CI nên chạy thêm một cấu hình có đủ binary thật. Không sửa sản phẩm trong vòng QA này.

### P2 — Nuclei chưa trình bày độ phủ thực tế

`vendor/claude-bug-bounty/tools/recon_engine.sh` cắt danh sách target bằng `head -50/-200` trước lệnh nuclei; default deep host 50. UI/`stats.nuclei_templates` đang cho biết số template đã cài, không cho biết số URL/host được chọn, đã xử lý, bỏ qua, số template thực chạy, hay trạng thái partial theo từng lệnh. Đừng gọi scan này “toàn bộ template trên mọi host”. Hướng xem xét: ghi các bộ đếm đầu vào/chạy xong/bị cắt và lý do; nếu cần độ phủ cao hơn, phân lô có checkpoint/resume và giới hạn theo policy. Giữ filter severity và template rủi ro. Đây là finding về khả năng quan sát và phạm vi, chưa chứng minh nuclei bỏ sót một lỗ hổng cụ thể.

## Giới hạn

- Không chạy Light/Strong trên Arc, Wolt hoặc bất kỳ host ngoài nào; không kiểm chính sách H1 thật.
- Không đo timeout nmap thật bằng cách treo dịch vụ; timeout wrapper và cancel chỉ được bộ test phủ.
- Không chạy tất cả test integration/Docker E2E; chạy test batch probe được nêu trên và bộ unit. Các flow apex/repo/schedule/export có test unit trong 445 pass nhưng chưa tái hiện đầy đủ qua UI/API trong vòng này.
- Bản sao repair chứa toàn bộ DB nhưng chỉ targets Arc; ảnh hưởng Wolt trong bản sao không phản ánh dữ liệu gốc. Mọi DB/targets và ảnh thử nghiệm đều nằm ngoài worktree nguồn.
- Không xác minh số template nuclei **thực thi** bằng scan trên #65; dữ liệu #65 chỉ được đọc và code mới được audit tĩnh.

## Gợi ý chuyển Claude Local

Đọc báo cáo này trên nhánh `test/v160-host-audit`, đối chiếu source `e456029`. Ưu tiên sửa tính idempotent của repair khi mất `subjack.txt`; sau đó cô lập tool discovery trong test. Với nuclei, trước tiên quyết định semantics và bộ đếm độ phủ, rồi mới thiết kế chạy phân lô. Không merge nhánh QA vào code sản phẩm bằng cách thay thế source; chọn lọc finding và test cần thiết.
