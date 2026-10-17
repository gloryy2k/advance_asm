# Chọn kết quả theo lần scan — ghi chú review

Trang Program có bộ chọn scan hoàn tất ở đầu trang. Lựa chọn được giữ khi chuyển tab Dữ liệu, Phát hiện, Lịch sử và Hướng dẫn. Các liên kết từ Run mang theo scan hiện tại.

| Mục | Khi chọn scan cũ |
| --- | --- |
| URL | Danh sách URL đã biết **tới** scan đó, theo API URL hiện có; bảng URL có bộ lọc riêng `Tất cả scan`. |
| Cổng / Đường dẫn ffuf | Đọc file output trong đúng thư mục của scan đó. |
| Diff | Đọc `diff_event` của scan đó. |
| Host / Xếp hạng / Finding | Lọc theo khoảng `first_seen_scan` → `last_seen_scan`. Đây là ước tính vì DB chỉ giữ status/tech/rank/severity hiện hành, không lưu snapshot từng lần. Giao diện cảnh báo và dẫn tới file gốc trong Run. |
| Tổng quan | Hiện thống kê của scan đã chọn ở đầu trang; inventory, biểu đồ và lịch bên dưới ghi rõ là hiện hành. |
| Brief / ZIP | Chỉ có bản hiện hành của program. Khi chọn scan cũ, giao diện ghi rõ giới hạn này và dẫn tới Run để xem file gốc. |

API `assets`, `surface`, `findings` nhận thêm `scan=latest|all|<id>`. Mặc định `all` giữ tương thích với client cũ; UI gửi `latest` khi không chọn scan cũ. ID draft, không thuộc program hoặc không tồn tại bị từ chối. `scan-options` trả danh sách gọn của tất cả scan hoàn tất, tránh giới hạn 100 record của API detail.

**Điểm Claude cần đánh giá:** nếu cần tái hiện chính xác Host/Finding/Brief ở mọi thời điểm, cần thiết kế snapshot theo scan và migration DB. Bộ chọn này không giả vờ rằng dữ liệu hiện hành là snapshot lịch sử.
