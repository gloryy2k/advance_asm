# BBASM v1.5.5 xử lý các loại asset trong scope như thế nào

Kiểm tra read-only trên source `42e3a0d`, không chạy scan. File này dành cho Claude khi đánh giá phạm vi chức năng tiếp theo. Nguồn chính: `backend/jobs/scope_resolver.py`, `backend/jobs/recon_orch.py`, `backend/jobs/ingest.py`, `backend/jobs/h1_scope.py`, `frontend/src/pages/Review.tsx`.

| Category | Resolve/Review | Passive | Light/Strong | Output |
| --- | --- | --- | --- | --- |
| `wildcard` (`*.example.com`) | Chọn được; chỉ subdomain, không tự thêm apex. | Liệt kê subdomain từ nguồn công khai, lọc qua scope gate. | Sau discovery, probe host hợp lệ; host sống có thể vào bước quét sâu theo ngân sách. | Host/URL/finding; có thể chỉ một phần nếu timeout. |
| `web` (domain, URL, host cụ thể) | Chọn được; URL IN có path hiện được quy về **host để recon**, path không giới hạn quyền quét. | Nguồn công khai, không probe HTTP. | HTTP probe, crawl, nuclei; Strong còn nmap/ffuf tùy cấu hình và policy. | Host/URL/finding. OUT theo path khiến host chỉ probe, trừ khi người dùng cho phép active trên host đó. |
| `ip` | Chọn được. | Không dùng nguồn lịch sử cho IP. | Chạy engine trên IP theo depth; Light không nmap, Strong có thể nmap/ffuf. | IP/HTTP/finding nếu có bằng chứng. |
| `cidr` | Chọn được; engine nhận `TARGET_TYPE=cidr`. | Không dùng nguồn lịch sử. | Xử lý dải theo depth và ngân sách; có thể rất tốn thời gian nếu dải lớn. | Một asset đại diện dải; IP rời không có phản hồi/bằng chứng bị gộp bỏ. |
| `source_code` (`repo:https://...`) | Chọn được mặc định, không đưa vào HTTP recon. | Ghi scope, cảnh báo chưa tự fetch repo. | GitHub: `secrets_hunter.sh --git` gọi trufflehog/noseyparker/gitleaks nếu có; URL tổ chức GitHub có `--github-org`. Repo ngoài GitHub: cảnh báo và làm tay. | Finding dạng secret candidate gắn repo; không có SAST, dependency scan, mobile analysis hay cây source code trong UI. Kết quả chưa xác minh mặc định. |
| `mobile` (`app:...`, Android/iOS asset type nhận diện) | Hiện nhãn “Mobile — làm tay”; checkbox tự động bị khóa. | Không chạy. | Không chạy. | Chỉ ghi scope/instruction vào `PROGRAM.md`, Brief và log `Manual asset`; không có APK/IPA download hay dynamic mobile test. |
| `other` | Raw scope: “Khác — làm tay”, checkbox khóa. H1: identifier OTHER có hình dạng host rõ có thể được phân loại lại thành web/wildcard; còn mô tả mơ hồ nằm ở “chưa phân loại”, không vào scope gate. | Không chạy. | Không chạy. | Ghi để người dùng đánh giá thủ công; OUT chưa phân loại nhưng giống host có thể khóa launch, tránh quét nhầm. |

## Lưu ý cho quyết định sản phẩm

1. UI Review nên ghi **độ phủ theo loại asset**: “quét tự động”, “chỉ kiểm tra secret của repo”, “chỉ lưu để làm tay”, “không phân loại được”. Một preset Strong không có nghĩa mọi asset trong program đã được Strong scan.
2. Với source code có hướng dẫn chỉ cho phép một phần repo, luồng hiện tại truyền cả URL repo vào scanner. Đây là finding F2/P1 trong `ARC_BBP_STRONG_AUDIT.md`; cần cưỡng chế giới hạn trước khi chạy hoặc khóa tự động và chuyển sang làm tay.
3. Với URL IN có đường dẫn cụ thể, parser hiện cảnh báo “recon vẫn chạy trên cả host”. Cần Review nhấn mạnh điều này và cân nhắc chế độ path-constrained thật nếu muốn tự động quét loại asset này.
4. Mobile hiện thiếu pipeline riêng: metadata H1 vẫn hữu ích cho người hunt, nhưng người dùng không nên hiểu “Scan xong” là đã kiểm tra app. Nếu phát triển tiếp, ưu tiên workflow tách biệt, yêu cầu package/build có quyền sử dụng, kết quả và trạng thái riêng; không ép mobile vào các tool HTTP.
5. Các loại `other` như hardware, executable, smart contract, cloud account, ASN hoặc Open Scope không thể suy ra quyền gửi request từ một chuỗi mô tả. Cần adapter riêng cho từng loại và gate cụ thể trước khi tự động hóa.
