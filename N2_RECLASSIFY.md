# N2 reclassify — kiểm trên host

Ngày 2026-10-15; nguồn `claude/upbeat-thompson-b7bb23` commit `59d752a`, nhánh `test/n2-reclassify`. Rebuild QA stack bằng `docker compose -p bbasm-v12 up -d --build --force-recreate` (image `sha256:444ebbe9937f...`, health `ok=true`, `h1_api=false`). Chỉ đọc metadata công khai: **3 POST H1** để Resolve GitLab, Shopify, Uber; mỗi handle dưới 100 asset nên một trang, không retry/fallback. Không token, cookie, Launch hoặc scan.

| Mã | Hành động | Kết quả | Bằng chứng |
|---|---|---|---|
| T0 | Checkout/rebuild | PASS | HEAD `59d752a`; submodule update xong; container `bbasm-v12` chạy commit này. |
| T1 | `docker run --rm --network none --entrypoint python --workdir /src --mount type=bind,source=<checkout>,target=/src,readonly bbasm-v12-bbasm -m pytest -m "not integration" -q` | PASS | **334 passed**, 25 deselected, 5 warnings trong Linux image. Mount repo chỉ đọc để test thấy `scripts/` và `vendor/`; chạy pytest trực tiếp trong runtime image thiếu các đường dẫn nguồn này và dừng khi thu thập test. |
| T2 | `cd frontend && npm test -- --run` | PASS | **48 passed**. Docker build frontend cũng thành công. |
| T3 | Resolve ba handle; đọc `GET /api/scans/<id>/review` | PASS | Cả ba `policy_source=public_page`, completeness khớp, không còn mục `unclassified.blocking=true`, `launch_gate.allowed_depths=[passive,light,strong]`. Chi tiết dưới đây. |
| T4 | Playwright desktop 1366px, mask `.policy-text`, không Launch | PASS | [GitLab](review_evidence/n2_live/gitlab_review_reclassify_1366.png), [Shopify](review_evidence/n2_live/shopify_review_reclassify_1366.png), [Uber](review_evidence/n2_live/uber_review_reclassify_1366.png). Light/Strong `enabled=true` ở cả ba; `document.scrollWidth=innerWidth=1366`. |
| T5 | Gọi trực tiếp `ScopeGate.in_scope` với scope draft | PASS | Uber: `scaledsolutions.uber.com=false`, `x-scaledsolutions.uber.com=false`, `repo:https://gitlab.com/gitlab-org/cli=false`. GitLab: repo `cli=false`. Thử thêm IN rộng `*.uber.com`: `example.uber.com=true` nhưng hai host `scaledsolutions` vẫn `false`; thử IN repo tổ chức GitLab rộng thì `cli` vẫn `false`. Không gửi request tới target. |

## Metadata sau phân loại lại

| Handle (draft) | Đối chiếu từ H1 | Classified | Unclassified | `by_shape` | Allowed depths |
|---|---:|---:|---:|---|---|
| GitLab (#26) | IN 19/19 · OUT 25/25 | 41 | 3 | không có | Passive, Light, Strong |
| Shopify (#27) | IN 21/21 · OUT 9/9 | 24 | 6 | `supplier-portal.shopifycloud.com` (OUT) | Passive, Light, Strong |
| Uber (#28) | IN 4/4 · OUT 20/20 | 21 | 3 | `*.uberinternal.com` (IN), `*.ubercarshare.com` (OUT) | Passive, Light, Strong |

Tất cả mục dưới đây có `blocking=false` và vẫn hiển thị trong danh sách chưa phân loại của Review:

| Handle | Identifier | Kind | Blocking | Reason |
|---|---|---|---|---|
| GitLab | `Your Own GitLab Instance` | IN | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| GitLab | `Other non-production infrastructure` | IN | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| GitLab | `GitLab for Jira Cloud` | IN | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| Shopify | `Shopify Mobile Applications` | IN | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| Shopify | `Authentication & ATO` | IN | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| Shopify | `Shopify Developed Apps` | IN | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| Shopify | `Shopify Third Party Apps` | IN | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| Shopify | `Shopify Third Party Store` | IN | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| Shopify | `Other` | OUT | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| Uber | `Recon Data` | IN | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |
| Uber | `*ubereats.com` | IN | false | Loại asset không rõ (ví dụ Open Scope/OTHER): không suy diễn thành quyền quét |
| Uber | `Fraud Reports` | OUT | false | Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy |

**Giới hạn:** completeness xác nhận số node metadata đã đọc, không tự chứng minh policy cho phép active scan. Các mục mô tả/`*ubereats.com` không trở thành rule quét; người dùng vẫn phải đọc policy và xác nhận trước khi Launch. Không sửa code sản phẩm; ảnh đã che policy đầy đủ.
