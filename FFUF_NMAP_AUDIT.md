# Audit ffuf và nmap — `arc-bbp` Strong #65

**Phạm vi:** chỉ đọc file output, log #65 và code tại v1.5.5 `42e3a0d` (2026-10-16). Không chạy lại scan, không gửi request tới asset. Scan #65 là `done_partial`; mọi số dưới đây là bằng chứng của lần chạy đó, không xác nhận lỗ hổng trên target.

| Mục | Kết quả từ #65 | Đánh giá |
| --- | --- | --- |
| nmap trên 2 host nêu trực tiếp | `65/4/ports/nmap_results.txt` có marker `Nmap done`, 2 host, 10 cặp host/cổng `open`, 232,8 giây. Cả hai IP trả dịch vụ Cloudflare. | Đã chạy xong; kết quả là cổng trên IP CDN, không chứng minh cổng origin/app của program. |
| nmap trên 126 host khám phá | `65/5/ports/nmap_results.txt` bắt đầu `nmap -sV --top-ports 1000 -T4 --open -sT -iL .../hosts-5.txt`; có 19 báo cáo host, 90 dòng cổng mở, 99 dòng DNS resolve thất bại, **không có marker `Nmap done`**. Stage `probe` timeout sau 1.554 giây. | Chỉ là output dở dang; không thể gọi là quét cổng hoàn tất. |
| ffuf | Hai file `65/4/dirs/ffuf_*.json` đọc được, lần lượt 2 kết quả HTTP 200 và 24 kết quả HTTP 403. Stage discovery không có live host nên ffuf bỏ qua; stage main quét 2 host, stage deep không chạy. | Công cụ đã chạy, nhưng 24 phản hồi 403 cùng `length=4547`, `words=656` rất có thể là trang chặn chung; chưa xác minh từng đường dẫn tồn tại. |

## Finding cần sửa

### FN1 — P1: lệnh `probe_only` vẫn quét nmap 1.000 cổng, góp phần làm stage probe hết ngân sách

**Tái hiện:** Trong `backend/jobs/recon_orch.py::recon_env`, nhánh `probe_only` ép tắt historical/crawl/nuclei/ffuf nhưng không ép `BBASM_SKIP_NMAP=1`. Với Strong #65, lệnh `probe` trên 126 host đã chạy nmap `-sV --top-ports 1000`; log `data/logs/65.jsonl` có `Running nmap ... hosts-5` lúc 07:55:21 và stage timeout 08:21:03. File nmap dừng giữa chừng, không có `Nmap done`. `coverage.batches_done=0`, giai đoạn deep `empty`. Đây là nguyên nhân có bằng chứng trực tiếp của việc probe tốn thời gian; chưa thể khẳng định là tác nhân duy nhất của timeout.

**Hướng sửa:** ép tắt nmap cho `probe_only`, gồm batch host khám phá và host có OUT theo path. Chạy nmap riêng ở stage deep trên số host live đã chọn, có ngân sách và giới hạn host/port rõ ràng. Nếu hết thời gian, ghi trạng thái nmap `partial/timeout` theo lệnh và vẫn dùng HTTP output đã có để tiếp tục ưu tiên host. Regression: Strong `probe_only` phải có `BBASM_SKIP_NMAP=1`, không sinh file nmap; stage deep mới được gọi nmap khi được phép.

### FN2 — P2: `open_ports.txt` bỏ sót cổng vì regex chỉ lấy cổng cuối mỗi host

**Tái hiện:** `65/4/ports/nmap_greppable.txt` liệt kê 10 cặp host/cổng mở, thuộc 6 số cổng khác nhau: 80, 443, 1720, 5060, 8080, 8443. `65/4/ports/open_ports.txt` chỉ có `8080/open` và `8443/open`; log báo `Open ports: 2`. Trong `vendor/claude-bug-bounty/tools/recon_engine.sh`, chuỗi `grep "open" | sed -nE 's/.*[^0-9]([0-9]+)\/open.*/\1\/open/p' | sort -u` dùng `.*` tham lam nên bắt match cuối trên mỗi dòng `Host:`.

**Hướng sửa:** parse mọi phần tử `Ports:` thành từng cặp host/port/protocol, rồi đếm `host-port` và `unique port` riêng. Giữ liên hệ với host; đừng chỉ lưu tập số cổng, vì hai host cùng port là hai quan sát khác nhau. Test greppable có nhiều port trên cùng một dòng, nhiều host, và scan dở dang.

### FN3 — P2: ffuf 403 nhiễu do không tự hiệu chuẩn phản hồi chặn chung

**Tái hiện:** `65/4/dirs/ffuf_rpc.testnet.arc.network.json` có 24 kết quả HTTP 403; tất cả cùng `length=4547`, `words=656`. Config ghi `autocalibration=false`, matcher chấp nhận `403`, không có filter kích thước; command dùng `-sf`. Không có bằng chứng 24 path đó thực sự tồn tại. File của host còn lại có 2 kết quả HTTP 200, cũng chỉ là đường dẫn tìm thấy, chưa phải lỗ hổng.

**Hướng sửa:** gửi một path ngẫu nhiên an toàn để lấy baseline 403/404 trước ffuf, bật hiệu chuẩn phù hợp hoặc lọc phản hồi đồng nhất theo host. Báo rõ “bị WAF/chặn chung” và số path đáng xem sau lọc; không nâng HTTP 403 thành finding. Giữ raw JSON để chuyên gia kiểm tra. Test fixture trả cùng 403 cho mọi path và một 200 riêng biệt.

### FN4 — P2: Run đếm file thay vì kết quả ffuf/cổng, và nhận file nmap dở dang là “Đã chạy”

**Tái hiện:** `backend/asm/phases.py::build_report` đếm số dòng của file khớp mẫu đầu tiên. Với ffuf, mỗi JSON chỉ tính thành 1 dòng dù `results` là 2 và 24; thêm nữa, mẫu `dirs/*.json` không bằng nhãn file cụ thể nên `count` thực tế về 0. Với nmap, hai `ports/nmap_greppable.txt` có 6 + 39 = **45 dòng**, đúng nhãn Run nhưng không phải số cổng hay host; file stage probe có dữ liệu nhưng không có `Nmap done`, vẫn có thể được đánh dấu `ran`.

**Hướng sửa:** parse `ffuf.results` để đếm theo host và status; parse nmap thành host/cổng mở, phân biệt output hoàn tất với dở dang bằng marker/exit/stage status. Hiện nhãn “26 phản hồi (24 cần lọc 403)”, “2 host, 10 cặp host/cổng” thay vì số dòng file; giữ link tới raw artifact.

## Cải thiện sau khi sửa lỗi

- **Ưu tiên P2:** phát hiện IP CDN/shared edge trước khi diễn giải nmap. Nếu kết quả là Cloudflare như #65, nêu “cổng trên CDN, chưa xác minh origin”, tránh đưa 1720/5060 vào danh sách cổng của ứng dụng.
- **Ưu tiên P3:** ffuf và nmap hiện chủ yếu là raw artifact; `backend/jobs/ingest.py` không có nhánh nhập `dirs/ffuf_*.json` hoặc `ports/nmap_*` vào bảng dữ liệu có cấu trúc. Thêm tab/section “Đường dẫn dò được” và “Cổng/Dịch vụ”, kèm nguồn scan, host, HTTP status, mức tin cậy và trạng thái partial; chỉ đưa vào Findings khi có xác minh riêng.
- **Ưu tiên P3:** tách cảnh báo “ffuf không cài” với “không có host live” trong log. Scan #65 stage discovery ghi `ffuf not installed or no live hosts` dù công cụ đã được cài và chạy ở stage main.

## Bằng chứng tái hiện offline

```text
targets/arc-bbp/recon/scans/65/4/ports/nmap_results.txt
targets/arc-bbp/recon/scans/65/4/ports/nmap_greppable.txt
targets/arc-bbp/recon/scans/65/4/ports/open_ports.txt
targets/arc-bbp/recon/scans/65/5/ports/nmap_results.txt
targets/arc-bbp/recon/scans/65/4/dirs/ffuf_rpc.drpc.testnet.arc.network.json
targets/arc-bbp/recon/scans/65/4/dirs/ffuf_rpc.testnet.arc.network.json
data/logs/65.jsonl: event id 238, 265–267, 286, 289, 314, 417, 641
```

Các file raw nằm trên máy chạy stack, không nằm trong nhánh QA; báo cáo ghi số liệu cần thiết để Claude đánh giá qua repo. Không sửa code sản phẩm hoặc output #65.
