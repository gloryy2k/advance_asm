# N2 live check — HackerOne public_page

Ngày 2026-10-15, Windows + Docker Linux, nguồn `claude/upbeat-thompson-b7bb23` tại `a9b8cc6`, nhánh kết quả `test/n2-live-check`. Chỉ đọc metadata công khai qua `hackerone.com`; không đăng nhập, không token, không Launch/scan target. Stack QA `bbasm-v12` tại `127.0.0.1:18765` chạy image được build lại từ `a9b8cc6` (`sha256:e92cbba26b3f...`). `GET /api/health`: `ok=true`, `h1_api=false`.

## Kết quả

| Mã | Hành động | PASS/FAIL | Bằng chứng |
|---|---|---|---|
| N2-0 | `git fetch origin`; switch/pull nhánh nguồn; `git submodule update --init --recursive`; tạo `test/n2-live-check`; rebuild stack | PASS | HEAD `a9b8cc6`; submodule update thành công khi chạy quyền phù hợp; `docker compose -p bbasm-v12 up -d --build --force-recreate` hoàn tất, health OK. |
| N2-1 | Chromium headless mở `https://hackerone.com/verisk_vdp`, bắt POST `/graphql` của trang | PASS | GET trang 200; 3 POST GraphQL đều 200: `AppQuery`, `CurrentUser`, `LayoutDispatcher`. Không dùng storage state/login. `LayoutDispatcher` trả `data.resource.__typename=Team`; `me=null`. |
| N2-2 | Chromium headless mở `https://hackerone.com/gitlab` | FAIL | `Page.goto: net::ERR_FAILED` do bộ chặn giới hạn 24 request H1 của harness đã đạt trần khi tải JS/CSS Verisk; **không phải** chứng cứ H1 chặn GitLab. Không nới trần để giữ ngân sách request. |
| N2-3 | `POST /api/scope/resolve` với URL Verisk `?type=team`, không token; `GET /api/scans/21/review` | PASS | `policy_source=public_page`; attempts: `api` bỏ qua vì thiếu token, `public_page` OK. 2 IN, 0 OUT, 0 chưa phân loại; policy dài 3.109 ký tự; `allowed_depths=[passive,light,strong]`. Không fallback dump. |
| N2-4 | Resolve tương tự GitLab; `GET /api/scans/22/review` | PASS | `policy_source=public_page`; attempts tương tự. 10 IN, 22 OUT đã phân loại; 12 chưa phân loại (9 IN, 3 OUT), lý do `Định dạng không nhận diện được` hoặc `Loại asset không rõ`; policy dài 26.067 ký tự; `allowed_depths=[passive]`, thiếu `OUT chưa phân loại`. Tổng raw asset suy từ 32 classified + 12 unclassified = 44. |
| N2-5 | Kiểm schema `PAGE_QUERY` trên H1 thật | PASS | Hai Resolve trên đã gọi POST `https://hackerone.com/graphql` bằng `PAGE_QUERY` và nhận dữ liệu policy + structured scope hợp lệ. Không có HTTP 403/CSRF/Cloudflare; không cần cookie phiên hay token. Response được provider chấp nhận ở `data.team.handle/name/policy/structured_scopes.edges/pageInfo`. |
| N2-6 | Đối chiếu `structured_scope_stats` qua `opportunities_search` | FAIL | Chưa có số liệu đáng tin để so. Hai POST cuối với truy vấn đếm scope trả HTTP 200 nhưng GraphQL syntax error `Expected VAR_SIGN, actual: BANG` do PowerShell mở rộng mất `$handle` trong lệnh test. Đã chạm ngân sách 30 request H1, không thử tiếp. Đây là lỗi harness, không phải lỗi BBASM/H1. |
| N2-7 | Playwright desktop 1366px mở Review hai draft, không Launch | PASS | [Verisk](review_evidence/n2_live/verisk_vdp_review_1366.png), [GitLab](review_evidence/n2_live/gitlab_review_1366.png). `document.scrollWidth=innerWidth=1366`. Verisk: radio Light/Strong `disabled=false`; GitLab: cả hai `disabled=true`, Passive được chọn. Nội dung policy trong ảnh đã che. |

## Schema quan sát được

- POST do **trang thật** gửi: `AppQuery` (`maintenance_banner`, `session`, `me`), `CurrentUser` (`organizations_admin`, `features`, `me`), `LayoutDispatcher($url: URI!)`. `LayoutDispatcher` dùng `resource(url: $url)` và fragment `Team`, trong đó có `assets_in_scope: structured_scopes_search(eligible_for_submission: true) { total_count }`. Response Verisk có `data.resource` kiểu `Team`, `handle`, `policy_setting.has_policy`, `assets_in_scope.total_count`; request công khai không có `me`.
- JS chunk `team_profile_router-D8W5Rti4.js` do trang thật tải có `team(handle: $handle) { structured_scopes_search(group_names, search_string, eligible_for_submission, eligible_for_bounty, min_severity_score, asm_tag_ids, from, size, sort) { nodes, pageInfo, total_count } }`. Biến phân trang quan sát được là `from`/`size`; truy vấn nhóm dùng `grouped: true` và `aggs`.
- BBASM `PAGE_QUERY` hiện dùng `team(handle: $handle) { handle name policy structured_scopes(first: 100, after: $cursor, archived: false) { pageInfo { hasNextPage endCursor } edges { node { asset_type asset_identifier eligible_for_submission eligible_for_bounty instruction max_severity } } } }`. Hai lời gọi thực tế qua Resolve **thành công**, nên các field này hiện hợp lệ dù UI H1 dùng query khác. `policy` trả chuỗi có cú pháp Markdown (Verisk bắt đầu `#Disclosure Policy`; GitLab bắt đầu `# Rewards`), không phải HTML. Chỉ ghi prefix dưới 200 ký tự; không lưu full query response/policy/cookie/header.
- Prefix policy Verisk (dưới 200 ký tự): `#Disclosure Policy\n\n* As this is a private program, please do not discuss this program or any vulnerabilities (even resolved ones) outside of the program without express consent from the organization.`
- Prefix policy GitLab (dưới 200 ký tự): `# Rewards\nWe have different rewards depending on the business impact of each asset. A more complete description of each asset will be in the scope section, but in general GitLab.com and all our produc`

**PAGE_QUERY đề xuất:** giữ query hiện tại; không có bằng chứng cần đổi field/header. Có thể bổ sung phép kiểm tổng `structured_scopes_search.total_count` cho IN/OUT để phát hiện thiếu trang/phân loại, nhưng cần thử lại trong ngân sách request riêng. `User-Agent` hiện tại và `Accept: application/json`, `Content-Type: application/json` đủ cho hai handle. Không cần CSRF từ HTML trong thử nghiệm này.

## Finding mới

- **P2 — Trạng thái “mở khóa Light/Strong” dễ bị hiểu là policy đã cho phép active scan.** Tái hiện: Resolve Verisk không token, Review #21 có policy không rỗng và 2 IN rõ ràng, radio Light/Strong mở; `launch_gate` chỉ kiểm policy hiện diện, không diễn giải điều khoản automation/rate limit. Hướng sửa: phân biệt “đủ dữ liệu để cấu hình” và “đã xác nhận policy cho phép”; đặt nhãn ngay cạnh Light/Strong, giữ bước xác nhận của người dùng và tránh diễn đạt như hệ thống đã cấp quyền. Không Launch trong vòng test này.

## Giới hạn và vệ sinh

- Tổng H1 request outbound ước tính **30**: 24 request được Playwright cho phép (GET trang/asset và 3 POST GraphQL Verisk), 2 POST provider khi Resolve, 2 GET JS chunk công khai, 2 POST đếm scope lỗi cú pháp. Request bị `route.abort()` không tính là outbound. Không truy cập host target, không dùng token/cookie phiên, không đổi UA/IP để vượt chặn.
- Không quan sát được POST policy/scope mà chính UI GitLab phát, cũng chưa bắt được POST policy/scope của UI Verisk: trang tải nhiều asset trước khi hết trần 24. Khẳng định về `PAGE_QUERY` dựa trên hai lời gọi provider thật thành công, không phải bản capture request UI. `opportunities_search`/`structured_scope_stats` chưa kiểm chéo; con số raw asset ở trên là từ dữ liệu provider, chưa phải phép xác nhận độc lập.
- Ảnh chỉ từ localhost. Không có policy đầy đủ trong repo; vùng policy được mask. Hai draft #21/#22 chưa chạy scan; stack `bbasm-v12` được giữ để người dùng xem.
