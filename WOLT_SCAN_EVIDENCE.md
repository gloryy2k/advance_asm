# Wolt Passive #29 và Light #31 — bằng chứng để review

Ngày 2026-10-15. Code của stack `bbasm-v12`: `59d752a` trên `claude/upbeat-thompson-b7bb23`. Dữ liệu lấy chỉ đọc từ DB, log và output của stack QA `advance_asm-v12test`. Không chạy lại target, không sửa code sản phẩm. Nhánh bằng chứng: `test/wolt-scan-evidence`.

## File kèm theo

- [Log #29](review_evidence/wolt_scans/logs/29.jsonl), [output #29](review_evidence/wolt_scans/29/0/subdomains/subfinder.txt).
- [Log #31](review_evidence/wolt_scans/logs/31.jsonl), [output #31](review_evidence/wolt_scans/31/0/subdomains/all.txt), [Brief #31](review_evidence/wolt_scans/31/AGENT_BRIEF.md), [PROGRAM.md](review_evidence/wolt_scans/31/PROGRAM.md) và `.scope`. Toàn bộ file output của hai scan nằm trong `review_evidence/wolt_scans/{29,31}/` và giữ nguyên nội dung từ stack QA.
- [Hàng scan và cấu hình trích từ DB](review_evidence/wolt_scans/scan_rows.json), không kèm DB SQLite gốc.
- Không đưa `.env`, SQLite DB, token, cookie, key hoặc toàn bộ thư mục `data/` và `targets/` vào Git. Các file được đưa lên đã được dò mẫu credential/token; chỉ có một URL lịch sử chứa tham số `token` với giá trị rỗng. Phép dò này không bảo đảm phát hiện mọi loại dữ liệu nhạy cảm.

## Kết quả thực tế

| Scan | Cấu hình | Trạng thái | Diễn tiến và dữ liệu sau nhập |
|---|---|---|---|
| #29 | Passive, timeout 300s, 50 luồng, 150 req/s | `failed`: `Scan hard timeout exceeded` | 19:23:52–19:28:53 UTC ngày 14/10. Subfinder 720; crt.sh 64; log dừng tại `Querying Wayback Machine for subdomains...` từ 19:24:39. File `subfinder.txt` và `crtsh.txt` có dữ liệu, nhưng chưa có `subdomains/all.txt`; DB ghi `observed=0`, `subs=0`, `urls=0`. |
| #31 | Light, timeout 900s, 50 luồng, 150 req/s; nuclei low/medium bật | `done_partial`: `Scan hard timeout exceeded` | 02:11:56–02:27:45 UTC ngày 15/10. Lượt discovery: subfinder 706, crt.sh 64, Wayback 48, hợp nhất 720. Wayback mất gần 11 phút 47 giây. `gau` bị timeout 60 giây ở cả hai lượt nhưng có file dữ liệu. Lượt host tường minh có 4 host phản hồi; scan hết giờ sau khi bắt đầu `katana` lúc 02:26:48. DB ghi `subs=753`, `live=4`, `urls=227`, `findings=0`, `observed=980`; Brief 9.304 byte. |

`subs=753` là số asset/host được ghi nhận, **không phải 753 host đã probe HTTP**. #31 có 4 host phản hồi trong lượt host tường minh; không có output lượt probe cho 720 host từ wildcard. URL funnel của các nguồn URL: `raw=4422`, `in_scope=223`, `out_of_scope=4182`, `invalid=17`; DB có thêm 4 URL từ kết quả HTTP probe. Trong nhóm ngoài scope, `wolt.com=4107`, `links.wolt.com=61`, `restaurant-api.wolt.com=6`, `merchant.wolt.com=5`, `press.wolt.com=3`. Diff #31: `new=753`, `changed=0`, `gone=0`, không có baseline hoàn tất trước đó (`baseline_scan_id=null`). Đây là kết quả một phần, không dùng số 0 finding để kết luận target an toàn.

## Finding cần xử lý

1. **P1 — Wayback subdomain không có timeout riêng.** `vendor/claude-bug-bounty/tools/recon_engine.sh:347` gọi `curl -s` không giới hạn thời gian. #29 bị hard timeout tại đây; #31 mất phần lớn ngân sách Light tại đây. Chia ngân sách theo nguồn, ghi trạng thái timeout/lỗi riêng và tiếp tục với dữ liệu đã có.
2. **P1 — Mất dữ liệu dở dang của #29.** Script chỉ tạo `subdomains/all.txt` sau Wayback (`recon_engine.sh:353`); adapter chỉ đọc file này (`tools/recon_adapter.py:235`). Khi bị hard timeout, 720+64 dòng nguồn còn trên đĩa nhưng DB/UI ghi 0. Gộp theo từng nguồn hoặc cho ingester đọc các file nguồn khi scan dở dang; xác minh scope trước khi nhập.
3. **P1 — OUT dạng URL bị biến thành cấm cả host.** `backend/scope_gate.py:74` chuẩn hóa `https://wolt.com/en/wolt-for-work-contact-request` thành `wolt.com`; tương tự với URL OUT thuộc `merchant.wolt.com` và `restaurant-api.wolt.com`. #31 loại 4.107 URL trên `wolt.com` khỏi funnel. Review vẫn hiển thị host này ở IN. Cần biểu diễn và cưỡng chế URL/path OUT chính xác trước request; nếu chưa hỗ trợ, báo rõ và fail closed, không âm thầm đổi nghĩa quy tắc.
4. **P1 — 720 host wildcard chưa được probe trong #31.** `backend/jobs/runner.py:371` chạy toàn bộ command ban đầu trước `discovered_commands()`, nên lượt host tường minh (gồm crawl) có thể dùng hết ngân sách trước khi probe host khám phá được. Đưa probe host đã khám phá vào pipeline sớm hơn hoặc giới hạn từng pha, lưu `discovered/probed/unprobed` riêng.
5. **P1 — Header theo policy H1 chưa đi vào recon.** Policy được lưu ở Review yêu cầu `X-HackerOne-Research: [H1 username]` cho request thử nghiệm. `backend/jobs/recon_orch.py:69` dựng môi trường lệnh theo allowlist không có `BBHUNT_AUTH_HEADERS`; helper của vendor chỉ thêm header nếu biến đó được truyền vào. Cần UI/API cấu hình header phù hợp policy và xác minh trên mock localhost, không ghi giá trị header nhạy cảm vào log.
6. **P2 — Trạng thái và log dễ gây hiểu nhầm.** Trong lượt discovery của Light, `httpx`/`nuclei` được skip đúng thiết kế; dòng `ffuf not installed or no live hosts` xuất hiện dù Light không dùng ffuf. `dnsx` được UI/health nêu là công cụ Light nhưng `recon_engine.sh` không gọi nó. Tách nhãn `discovery`/`active`, trạng thái `skipped by depth`/`missing`/`timed out` và số host đã probe.
7. **P2 — Brief/dữ liệu có thể trông như kết quả hiện hành khi scan đang chạy.** Runner chỉ ingest và sinh Brief sau pipeline (`backend/jobs/runner.py:337-350`). Run có thể xem file thô theo pha trong lúc chạy, nhưng Program/Brief có thể đang hiển thị lần hoàn tất trước. Gắn scan ID, thời gian và trạng thái dữ liệu vào Brief/Program; không trình bày dữ liệu cũ như kết quả scan đang chạy.

## Tiêu chí kiểm lại sau khi sửa

- Dùng mock và `127.0.0.1`, không quét Wolt: một nguồn Wayback treo phải timeout theo pha; file subfinder/crt.sh được nhập như kết quả một phần; process được dọn.
- Light trên fixture có wildcard và host tường minh phải probe được host khám phá trong ngân sách; báo riêng `discovered`, `probed`, `unprobed`; không suy ra `gone` từ scan partial.
- URL OUT chặn đúng đường dẫn trước khi request, không vô tình loại cả host; header yêu cầu bởi policy đi vào HTTP tool được bật, có kiểm thử bằng server localhost.
- Run/Brief nêu rõ scan ID và phần nào chưa chạy; `ffuf` không bị báo là thiếu trong Light.

## Giới hạn

- Chưa thấy dữ liệu scan #32 trong bản sao QA này; bằng chứng kèm theo chỉ cho #29 và #31. Review #32 người dùng gửi qua văn bản, không được coi là output scan #32.
- Không kết luận policy Wolt cho phép mọi bước Light/Strong. `PROGRAM.md` kèm theo chứa bản policy công khai tại thời điểm Resolve; cần kiểm chính sách chính thức trước khi quét lại.
