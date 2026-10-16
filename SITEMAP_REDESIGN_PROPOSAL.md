# Đề xuất thiết kế lại Cây sitemap

Ngày 2026-10-16. Đây là tài liệu thiết kế để Claude đánh giá và triển khai; chưa thay đổi code sản phẩm. Mẫu dùng toàn bộ dữ liệu giả `demo.local`.

## Vấn đề cần giải quyết

Ở `Program → Dữ liệu → URL → Cây sitemap`, các dòng cây hiện chứa quá nhiều badge và metadata. Cấp cha/con khó nhận ra, còn bộ lọc, thống kê và thao tác mở cây cạnh tranh sự chú ý. Người dùng muốn đường nối nhánh dễ đọc như lệnh `tree`, nhưng các ký tự `│ ├─ └─` bản thử đầu trông nặng và rối.

## Phương án trực quan đã được người dùng đồng ý để Claude xem xét

1. Cây và chi tiết: hàng cây chỉ gồm nút mở/thu, biểu tượng loại node, tên và số URL căn phải. Dùng **đường dẫn mảnh, liên tục bằng CSS** ở các cấp lồng nhau; không dùng ký tự vẽ cây Unicode. Chọn một node thì nền xanh nhạt và panel bên phải hiện URL đại diện, đường dẫn đầy đủ, nguồn, mức kiểm chứng, số biến thể và scan gần nhất.
2. Khi tìm kiếm, ưu tiên danh sách kết quả phẳng theo host với breadcrumb đầy đủ. Chọn kết quả để xem panel chi tiết; có nút quay về vị trí của URL trong cây. Tránh tự mở hàng trăm nhánh khi truy vấn rộng.
3. Thanh công cụ gọn: tìm kiếm, nguồn, sắp xếp/mức mở. Bộ lọc nâng cao và các thống kê funnel giữ ở phần URL chung, không lặp trong mỗi hàng cây.
4. Mobile: panel chi tiết xếp dưới danh sách, không cuộn ngang.

Ảnh tham chiếu: [cây + chi tiết](review_evidence/sitemap_redesign/tree-detail.png), [tìm kiếm ưu tiên](review_evidence/sitemap_redesign/search-first.png), [390px](review_evidence/sitemap_redesign/tree-detail-390.png). [HTML mẫu](review_evidence/sitemap_redesign/preview-fragment.html) là **mockup dữ liệu giả**, không phải component production.

Đối chiếu với [ảnh sitemap hiện tại của `arc-bbp`](review_evidence/arc_bbp_strong/sitemap-current.png), chụp read-only trên localhost sau Strong #65.

## Ràng buộc triển khai đề nghị

- Giữ API phân trang của `/api/programs/{slug}/urls/tree`; chỉ tải node khi mở và vẫn hỗ trợ “Xem thêm”. Không dựng toàn bộ 5.000+ URL ở DOM.
- Giữ `scan=latest/all`, lọc nguồn/tag/điểm và nút chuyển sang bảng URL. Phân biệt URL lịch sử với URL đã quan sát được.
- Nút mở/thu có nhãn trợ năng và `aria-expanded`; hỗ trợ ↑ ↓ ← →, Enter, focus rõ khi dùng bàn phím. Đường nối chỉ để định hướng, không truyền tải trạng thái một mình.
- Panel chi tiết phải hiển thị đường dẫn đầy đủ mà không phá layout; ở màn hẹp cho phép xuống dòng tại dấu `/`.
- Đối chiếu mockup với component hiện tại `frontend/src/components/SitemapTree.tsx` và style hiện tại trước khi sửa. Claude quyết định phạm vi và kiểm thử với dữ liệu thật lớn.

Kiểm tra mẫu: Chrome headless, desktop 1100px và mobile 390px, không lỗi JavaScript hoặc cuộn ngang; chọn node và đổi hai phương án cập nhật panel chi tiết.
