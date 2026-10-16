# QA path OUT với công cụ thật trên loopback

Ngày 2026-10-16. Code `audit/input-output-flow` tại `bd8405b` (phần xử lý IN/OUT ở `2d540fd`). Không gọi HackerOne, không scan host ngoài, không dùng token. Container QA riêng `bbasm-path-audit` chạy `--network none`, mount `backend/` của commit này vào image `bbasm-v12-bbasm` (`sha256:8b64ef90486449482a07a8bb3ae3ece522efea84ccc975bffaf7e3442708e8fb`); DB và targets tạm nằm ngoài checkout. Stack người dùng `bbasm-v12` cổng 18765 không bị thay đổi.

**Cách đọc kết quả:** fixture đặt các URL `/admin` là OUT **không kèm hướng dẫn theo phương thức HTTP**. FAIL dưới đây là FAIL so với cam kết hiện tại của BBASM rằng active tool không gửi request tới path OUT. Đây không phải bằng chứng rằng những GET đó vi phạm policy của Wolt.

Fixture ghi mọi GET trên `127.0.0.1:80` và `127.0.0.2:80`; `/jump` trả `302 Location: http://restricted.qa.test/admin`. Trong container, `restricted.qa.test -> 127.0.0.1`, `free.qa.test -> 127.0.0.2`. Trang `/` có link `/safe`, `/jump`, `/admin`. Template nuclei duy nhất `qa-redirect-out.yaml` có `redirects: true`, GET `{{BaseURL}}/jump`. Công cụ trong image: httpx v1.12.0, gau v2.2.4, subfinder v2.17.0, nuclei v3.11.1. Mỗi case launch Light với `threads=1`, `rate_limit=5`, crawl và nuclei bật, `automation_ack=true`.

## Kết quả

| Case | Scope và cờ | Scan | Tổng GET fixture | GET `/admin*` trên OUT | Kết luận |
| --- | --- | --- | ---: | ---: | --- |
| 1 | IN `restricted.qa.test`, `free.qa.test`; OUT `http://restricted.qa.test/admin`; `BBASM_SCOPE_CRAWL=1`, `BBASM_NO_REDIRECT=1` | #1 `done` | 21 | **1** | **FAIL**: nuclei trên host tự do theo redirect sang OUT. |
| 2 | IN `127.0.0.0/31`; OUT `http://127.0.0.1/admin`; cùng cờ mặc định | #2 `done` | 20 | **1 trực tiếp**, thêm **1 qua alias** | **FAIL**: CIDR đi qua katana trên `127.0.0.1/admin`; nuclei theo redirect tới alias cùng IP. |
| 3 | IN/OUT như case 1; `BBASM_SCOPE_CRAWL=0`, `BBASM_NO_REDIRECT=0` | #3 `done` | 23 | **3** | **FAIL**: katana theo redirect hai lần; nuclei một lần. |
| Bổ sung | IN thêm `*.qa.test` để bắt buộc nhánh subfinder, OUT như case 1; cờ mặc định | #4 `done_partial` | 21 | **1** | subfinder thật được gọi; nguồn crt.sh/Wayback lỗi vì `--network none`. Nuclei vẫn tới OUT. |

`/admin` trên `free.qa.test` không phải OUT trong các case host; vẫn ghi dưới đây để báo **mọi** request tới `/admin*`.

| Case | Listener | Host header | Path | Nguồn theo log và finding | Thuộc OUT? |
| --- | --- | --- | --- | --- | --- |
| 1 | 127.0.0.2 | `free.qa.test` | `/admin` | katana, URL từ link trên `/` | Không |
| 1 | 127.0.0.1 | `restricted.qa.test` | `/admin` | nuclei `qa-redirect-out`, `matched-at` đúng URL này | **Có** |
| 2 | 127.0.0.1 | `127.0.0.1` | `/admin` | katana, URL từ link trên `/` | **Có** |
| 2 | 127.0.0.1 | `restricted.qa.test` | `/admin` | nuclei theo redirect; alias trỏ cùng IP | Cùng endpoint OUT, khác hostname |
| 3 | 127.0.0.2 | `free.qa.test` | `/admin` | katana | Không |
| 3 | 127.0.0.1 | `restricted.qa.test` | `/admin` | katana theo redirect từ `/jump` | **Có** |
| 3 | 127.0.0.1 | `restricted.qa.test` | `/admin` | katana theo redirect thêm một lần | **Có** |
| 3 | 127.0.0.1 | `restricted.qa.test` | `/admin` | nuclei `qa-redirect-out` | **Có** |
| 4 | 127.0.0.2 | `free.qa.test` | `/admin` | katana | Không |
| 4 | 127.0.0.1 | `restricted.qa.test` | `/admin` | nuclei `qa-redirect-out` | **Có** |

## Bằng chứng công cụ và giới hạn

- Case 1/3 chạy `httpx` thật (`live/httpx_full.txt`), `gau` thật (`urls/gau.txt` rỗng vì không có egress); host-list target **cố ý bỏ qua subfinder** trong `recon_engine.sh`. Không tính các case này là bằng chứng subfinder đã chạy.
- Case 4 dùng wildcard để vào nhánh discovery: `.source_status.tsv` ghi `subfinder ok 0 0`, `crt.sh error 0 6`, `web.archive.org error 0 6`. `done_partial` là do hai nguồn public không tới được trong container cách ly, không phải vì fixture.
- Nuclei finding ở case 1 và case 4 có `matched-at: http://restricted.qa.test/admin`. Case 2 còn có request trực tiếp với `Host: 127.0.0.1`, đủ để xác nhận OUT theo URL đã bị chạm.
- Không chạy exploit hay template bên ngoài; template QA chỉ gửi GET và kiểm status. Log JSON đầy đủ và template nằm ở thư mục QA tạm ngoài repo. Bảng trên liệt kê tất cả request có path bắt đầu `/admin` trong cả bốn lượt.

## Diễn giải policy Wolt: cần phân biệt OUT và phương thức request

Trong bản `review_evidence/wolt_scans/31/PROGRAM.md` đã lưu, **ba** URL OUT có instruction `Do not POST data here, as it will be sent to a third-party system that is also out of scope.`; **hai** URL OUT khác (`wolt-for-work-contact-request`, `partner-with-wolt`) không có instruction đó. Fixture này chỉ ghi GET. Vì thế không thể từ bảng trên kết luận rằng GET tới cả năm URL Wolt đều bị cấm, cũng không thể suy từ instruction của ba URL rằng hai URL còn lại cho phép GET.

Nếu policy chính thức xác nhận GET được phép ở một URL nhưng POST bị cấm, cách chặn mọi GET của BBASM là quá bảo thủ và giảm dữ liệu hữu ích. Tuy nhiên `eligible_for_submission=false`/OUT vẫn là nhãn phạm vi báo cáo; nó không tự động đồng nghĩa với quy tắc HTTP GET/POST. Cần giữ hai khái niệm riêng: (1) asset có được coi là IN cho finding/brief hay không; (2) phương thức, path và kiểu request nào được phép gửi. Chỉ cho GET khi instruction/policy của **chính asset đó** rõ ràng cho phép; trường hợp không rõ giữ giới hạn an toàn và báo lý do ở Review.

## Finding mới và hướng kiểm tra sửa

**P1 đối với cam kết chặn mọi request tới OUT hiện tại — không phải kết luận vi phạm policy Wolt.** `recon_orch.py` đánh dấu probe-only cho host nằm trực tiếp trong `path_rule_hosts`, nhưng CIDR đi qua `_recon(..., target_type="cidr")` mà không chia host bị giới hạn. Nuclei template có redirect riêng vẫn vượt OUT khi bắt đầu từ host tự do, ngay cả khi `BBASM_NO_REDIRECT=1`. Khi `BBASM_NO_REDIRECT=0`, katana cũng theo redirect sang OUT.

Đề nghị Claude phân tách hai lỗi: (a) CIDR cần tách/loại host có path OUT khỏi các bước crawl/template khi path đó cấm request; (b) kiểm soát redirect ở **từng request của mọi công cụ**, kể cả redirect do template nuclei quyết định và redirect sang hostname khác trỏ cùng IP. Nếu product hỗ trợ policy chỉ cấm POST, test hồi quy cần khẳng định GET được phép theo rule riêng nhưng POST/PUT/PATCH/DELETE và request có body không tới endpoint đó, kể cả sau redirect. Với OUT không có hướng dẫn cho phép GET, test phải khẳng định không có request nào tới path OUT. Chỉ kiểm DB hoặc output là không đủ.
