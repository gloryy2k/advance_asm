# N2 — asset chưa phân loại từ HackerOne public_page

Ngày 2026-10-15. Nguồn `claude/upbeat-thompson-b7bb23` commit `aae0cbe`; nhánh kết quả `test/n2-unclassified`. Stack QA `bbasm-v12` được build lại từ commit này (image `sha256:43224f648cba...`) và giữ chạy tại `127.0.0.1:18765`. Chỉ đọc metadata H1 công khai, không token/cookie, không Launch/scan asset. Tổng **4 POST GraphQL H1**: Resolve GitLab, phép đo GitLab, Resolve Shopify, Resolve Uber; mỗi handle có dưới 100 asset nên một trang, `public_page` thành công và không retry/fallback.

## Kết quả

| Mã | Hành động | Kết quả | Bằng chứng |
|---|---|---|---|
| N2-U1 | Resolve GitLab; đọc `policy.classification.unclassified`, `completeness`, `launch_gate` | PASS | Draft #23; IN **19/19**, OUT **25/25**; 32 classified, **12 unclassified** (9 IN, 3 OUT); chỉ cho Passive vì có OUT chưa phân loại. Danh sách nguyên văn trong [JSON](review_evidence/n2_live/gitlab_unclassified.json). |
| N2-U2 | Resolve hai handle công khai đa dạng khác | PASS | Shopify #24: IN 21/21, OUT 9/9; 22 classified, 8 unclassified. Uber #25: IN 4/4, OUT 20/20; 17 classified, 7 unclassified. Cả hai vẫn chỉ cho Passive. JSON có identifier chưa phân loại và pattern parser nhận theo `asset_type`. |
| N2-U3 | Playwright headless Review GitLab, 1366px, mask policy | PASS | [Ảnh](review_evidence/n2_live/gitlab_review_after.png). Dòng `Đối chiếu số lượng với trang: IN 19/19 · OUT 25/25 ✓`; radio Light/Strong `disabled=true`; `document.scrollWidth=innerWidth=1366`. Không Launch. |
| N2-U4 | Đo policy và GraphQL response GitLab trong **cùng một POST** | PASS | HTTP 200, `errors=0`; policy raw **26.068 ký tự Unicode**, `strip()` **26.066**; response **35.876 ký tự / 35.883 byte**; 44 edges, IN 19, OUT 25. Provider Review cũng cho **26.066 Unicode code point**; PowerShell `.Length` trước đó là 26.067 UTF-16 code unit. Ước lượng Burp 17–18 nghìn thấp hơn số đo thực. Không lưu nội dung policy. |

## Dạng cần xử lý trong parser

- **GitLab 12 mục:** 9 `SOURCE_CODE` là URL repo trên `gitlab.com` (6 IN, 3 OUT); parser hiện chỉ chấp nhận URL GitHub cho `SOURCE_CODE`. 3 `OTHER` IN là nhãn mô tả (`Your Own GitLab Instance`, `Other non-production infrastructure`, `GitLab for Jira Cloud`), không chỉ ra host cụ thể. Đừng tự biến nhãn này thành quyền quét host.
- **Shopify 8 mục:** 1 `SOURCE_CODE` IN là `https://github.com/Shopify/*`; 5 `OTHER` IN là nhãn nhóm/mobile; 2 `OTHER` OUT gồm `Other` và hostname `supplier-portal.shopifycloud.com`. Có thể nhận hostname OUT nếu xác thực cú pháp chặt, nhưng phải giữ OUT ngay cả khi loại H1 là `OTHER`.
- **Uber 7 mục:** `OTHER` gồm nhãn `Recon Data`, các wildcard/domain có nội dung cụ thể và `Fraud Reports`; 2 `WILDCARD` OUT đặt dấu `*` giữa/đầu nhãn (`*scaledsolutions.uber.com`, `scaledsolutions*.uber.com`) nên parser hiện từ chối. Không mở rộng chúng thành `*.uber.com`; cần biểu diễn loại trừ đúng hoặc tiếp tục khóa active scan.
- JSON nhóm mọi pattern **đã nhận diện** theo `asset_type` (GitLab: URL 25, WILDCARD 7; Shopify: URL 15, WILDCARD 7; Uber: URL 17). Pattern nhóm này là dạng BBASM đã chuẩn hóa; danh sách `unclassified.identifier` giữ nguyên văn từ Review. Kiểm tra độ dài xác nhận không mục nào chạm giới hạn cắt 200 ký tự của API.

Không sửa code sản phẩm. Không có policy đầy đủ, token, cookie hay response GraphQL thô trong file kết quả.
