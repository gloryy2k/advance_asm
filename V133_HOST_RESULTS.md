# BBASM v1.3.3 — kết quả kiểm thử host

Nguồn `9e6af8d` (`claude/upbeat-thompson-b7bb23`), nhánh kết quả `test/v133-host-results`. Ngày 15/10/2026, Windows + Docker Desktop Linux. Stack QA `bbasm-v12` ở `127.0.0.1:18765`; chỉ scan fixture `127.0.0.1:80` trong chính container, không gọi H1 hoặc target ngoài. Data/targets QA được giữ nguyên; không đụng DB người dùng.

| Mã | Lệnh / hành động | PASS/FAIL/SKIP | Bằng chứng ngắn |
|---|---|---|---|
| T0 | `git checkout --detach 9e6af8d`; `docker compose -p bbasm-v12 up -d --build --force-recreate` | PASS | Image `sha256:75f4460bc0a6...`, build phần backend còn lại cached; container healthy ở `127.0.0.1:18765`. |
| T1 | `docker run --rm --network none --entrypoint python -v <QA worktree>:/src:ro -w /src bbasm-v12-bbasm -m pytest -m 'not integration' -q --disable-warnings` | PASS | **363 passed**, 32 deselected, 4 warnings; 33.34 giây. |
| P2-1 | Health trước scan, Light #41/#42 với nuclei bật và không có template | PASS | `nuclei=true`, `nuclei-templates=false`; cả hai scan `done`, phase Nuclei=`missing_tool`, reason nói “không được chạy”. `stats_json.tool_notes` ghi rõ BBASM chặn nuclei tự tải template. Sau scan `/root/nuclei-templates` vẫn **0 YAML**. |
| P2-2 | Playwright headless Chrome 1366px mở `http://127.0.0.1:18765/#/scan/41` | PASS | `data-testid=tool-note` hiện ghi chú “KHÔNG được chạy… BBASM chặn việc nuclei tự tải template”; không còn “chạy nhưng không kiểm tra gì” trong body. |
| M1 | Fixture HTTP localhost; raw `127.0.0.1`, `skip_historical=true`; Passive #40 → Light #41 → Light #42 | PASS | Cả 3 `done`. #40 diff `new=1`; #41 `baseline_scan_id=40`, `changed=1` (host nhận HTTP 200); #42 `baseline_scan_id=41`, `new=changed=gone=0`. Diff API trả lần lượt 1/1/0 event. |
| M5-A | WebSocket `/ws/scan/41`: ngắt client rồi nối lại với `after=1`; GET status qua REST | PASS | Sự kiện đầu ID 1; kết nối mới phát lại 71 sự kiện từ ID 2 đến `done`; REST status=`done`. Đây là kiểm reconnect ở mức client. |
| M5-B | Ngắt mạng thật của máy đang chạy scan rồi khôi phục | SKIP | Không điều khiển mạng/desktop người dùng. Trường hợp này chưa được xác nhận end-to-end trên máy người dùng. |
| M3 | H1 thật: đọc policy/scope và chạy scan theo quyền program | SKIP | Vòng QA này chỉ được scan `127.0.0.1`, không token, không H1. Không suy rộng kết quả fixture sang program thật. |
| M6 | Test clone/hunt command trong distro WSL2 người dùng | SKIP | `wsl --status` cho thấy WSL2; `wsl --list --quiet` chỉ có `docker-desktop`, không có distro phát triển để chạy bài này. |

## Kết luận và giới hạn

- **P2 về câu chữ nuclei: đã xác nhận sửa trên image và UI thật.** Không thấy hồi quy trong unit hoặc chuỗi scan localhost.
- Diff Passive → Light → Light và phát lại WebSocket đã qua trên localhost. M5-B vẫn cần một lần thử khi mạng thật gián đoạn; M3 vẫn cần đối chiếu policy/scope và quyền scan của program H1 thật.
- HTTP fixture và ba script QA tạm đã dọn. Giữ container/image `bbasm-v12` chạy để người dùng xem scan #40–#42; không prune, không xoá data/targets QA.

## Hướng test tay còn lại

- ☐ **M3 H1 thật — PASS/FAIL:** chọn program cho phép mức scan dự định, đọc policy chính thức; Resolve URL trong BBASM, đối chiếu từng IN/OUT, hướng dẫn riêng asset và policy với H1. Chỉ chạy Light khi policy cho phép và rate limit không vượt quy định. Ghi URL program, scan ID và chỗ lệch nếu có. Không đưa token vào báo cáo/repo.
- ☐ **M5-B mạng thật — PASS/FAIL:** trong một scan được phép và đủ lâu, refresh trang rồi ngắt mạng máy vài giây, nối lại. Log cũ phải phát lại, trạng thái cuối phải thành “hoàn tất” thay vì kẹt “đang chạy”.
- ☐ **M6 WSL2 — PASS/FAIL/N/A:** nếu dùng WSL2 cho việc hunt, clone trong filesystem của distro đó; chạy Docker, mở UI từ Windows, bấm “Sao chép lệnh hunt” và chạy trong WSL2. `pwd` phải vào đúng `targets/<slug>`.
