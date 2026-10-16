# QA v1.6.1 — ba commit sau bàn giao

Ngày 2026-10-17. Nguồn `claude/upbeat-thompson-b7bb23` tại `f20a636` (`7428043`, `1e26cfe` ngay trước; nền cũ `d89ae6d`, `e456029`). Submodule `vendor/claude-bug-bounty` tại `1e9a1e3`, nhánh `claude/nuclei-stats-coverage`. Chạy trên worktree QA riêng, chỉ fixture HTTP `127.0.0.1`; không scan Arc/Wolt/H1, không dùng token, không sửa dữ liệu người dùng hay code sản phẩm. Test Phase 9 dùng **nuclei thật** trong container `--network none`; image/stack QA là `bbasm-v161qa`, cổng 18793.

| Mã | Kiểm | Kết quả | Bằng chứng ngắn |
| --- | --- | --- | --- |
| C0 | Checkout và submodule | PASS | Log đúng thứ tự `f20a636 → 7428043 → 1e26cfe → d89ae6d → e456029`; submodule `1e9a1e3`. Nhánh nguồn đang ở worktree Claude Local nên QA checkout đúng commit bằng detached HEAD rồi tạo nhánh báo cáo. |
| C1 | Repair thiếu `subjack.txt` gọi hai lần | PASS | `test_without_the_original_file_nothing_stays_high`: 1 passed. Lần đầu đổi thành `subjack:unverifiable`/info; lần hai `run_repairs()==[]`, `stats_json` không đổi, chỉ một backup. |
| C2 | Test cô lập discovery của nuclei/ffuf | PASS | Image có cả binary thật: 450 passed; giấu hai binary chỉ trong container tạm: 450 passed. Cả hai 33 deselected. Đây là số **tại `f20a636`** (445 cũ + 5 test mới), không chạy riêng snapshot commit trung gian `1e26cfe`. |
| C3 | Frontend | PASS | `npm ci`; `npx vitest run`: 89 passed; `npx tsc --noEmit`: pass; `npm run build`: pass. Vite cảnh báo bundle 511 KB. |
| C4 | Phase 9 bình thường với nuclei v3.11.1 | PASS | 2/2 URL localhost được đưa vào; `coverage.json.last_stats={templates:1,requests:2,hosts:2,...}`; stats file 352 byte. |
| C5 | Quick 60 URL localhost | PASS | `given_urls=50`, `live_urls=60`, `limit=50`; log “only 50 of 60”; nuclei báo 50 request; không đổi giới hạn 50/200 hay severity/tag. |
| C6 | Timeout thật, rút ngắn bằng wrapper QA | PASS | Fixture chậm, wrapper giới hạn 1 giây thay cho cấu hình 1800 giây: `timed_out=true`, `last_stats=null`, log “stopped after 1800s (timeout)” (số trên log là **ngân sách cấu hình**, không phải thời gian QA đã chờ). |
| C7 | Docker image/runtime | PASS | `docker compose -p bbasm-v161qa up -d --build --force-recreate`; `/api/health` `ok=true`, `h1_api=false`; image có nuclei v3.11.1, ffuf 2.3.0, Phase 9 `-stats-json`; `bash -n recon_engine.sh` pass. |
| C8 | Hai lượt nuclei thật, reader gộp | FAIL | Gộp hai output thật: 52/62 URL, 52 request, `truncated=true`; Run ghi **“giới hạn 200 URL mỗi lượt”** dù lượt quick thứ hai bị cắt ở **50/60**. |
| C9 | Nuclei thoát lỗi không có template hợp lệ | FAIL | Dùng `-t` trỏ file không tồn tại: stderr gồm một dòng stats JSON và `[FTL] Could not run nuclei...`; `coverage.json.last_stats` nhận nguyên `[FTL]`, khiến file **không parse được**. Log engine lại nói “nuclei: no findings”; reader bỏ qua coverage này. |
| C10 | Kích thước `stats.jsonl` | PARTIAL | Fixture chậm 12 giây tạo 4 dòng, 692 byte; chưa chạy 1800 giây. Chưa thấy dấu hiệu phình lớn trong trường hợp sạch, nhưng output lỗi có thể khác. |
| C11 | Toàn bộ Strong với hơn một lượt nuclei trong một scan | SKIP | Đã chạy hai lượt Phase 9 thật và gộp output, nhưng chưa chạy orchestration Strong đầy đủ với 14.036 template. Không coi phép gộp này là xác nhận scan Strong end-to-end. |

## Finding mới

**P2 — `coverage.json` hỏng và trạng thái sai khi nuclei thất bại.** Trong `vendor/.../recon_engine.sh` Phase 9, `tail -n1 stats.jsonl` được chèn thẳng vào JSON mà không kiểm dòng đó là JSON. Nuclei có thể ghi thông báo lỗi sau dòng stats; với template không hợp lệ, file không parse được, `read_nuclei_coverage()` trả `None`, và engine ghi “no findings” dù công cụ thất bại. Cần lấy dòng stats JSON hợp lệ cuối cùng, ghi `last_stats:null` nếu không có, và phân biệt exit code lỗi với “chạy xong, không có finding”. Tái hiện bằng `review_evidence/v161_qa/check_nuclei_phase.py badtemplate` trong image QA offline.

**P2 — Mô tả giới hạn sai khi gộp quick/full.** `summarize_nuclei()` trả `limit=runs[0]['limit']`; `structured_result()` gọi đó là “giới hạn N URL mỗi lượt”. Hai lượt thật (full 2/2 rồi quick 50/60) hiển thị giới hạn 200 cho cả hai. Nên hiện giới hạn theo từng lượt hoặc nói chính xác “mỗi lượt có giới hạn riêng”; giữ tổng X/Y và số URL bị cắt. Tái hiện bằng output `check_nuclei_phase.py normal`, `quick60`, rồi `check_aggregate.py`.

## Giới hạn và quyết định tiếp theo

- Không đổi `NUC_LIMIT` 50/200, severity/tag, hay số template đã cài. `stats.nuclei_templates` vẫn là số **đã cài**, khác với số tự báo từ nuclei.
- `stats.jsonl` chưa được đo suốt 1800 giây; số 692 byte/12 giây không phải chứng nhận dung lượng tối đa.
- Chưa thực hiện một scan Strong trọn luồng với nhiều command trên stack QA. Các thử nghiệm nuclei thật đều trong container không có mạng ngoài, chỉ có HTTP fixture localhost.
- Lượt chạy pytest đầu khi chỉ mount thư mục test bị lỗi vì thiếu `/app/vendor` và `/app/scripts`; sau khi mount toàn repo read-only cùng bản sao vendor LF, hai môi trường đều đạt 450. Đây là lỗi setup QA, không phải regression.
