import { ApiError } from "../api/client";

const BY_CODE: Record<string, string> = {
  scope_empty: "Scope chưa có mục IN hợp lệ. Thêm ít nhất một asset cần kiểm tra.",
  no_completed_scan: "Chưa có scan hoàn tất. Chạy scan đầu tiên để tạo brief.",
  metadata_unavailable:
    "Không lấy được dữ liệu scope từ HackerOne (mạng hoặc dịch vụ lỗi). Thử lại sau, hoặc dùng Raw scope.",
  metadata_denied: "Địa chỉ lấy dữ liệu bị chặn bởi scope gate.",
  framework_missing:
    "Thiếu framework recon. Chạy `git submodule update --init --recursive` rồi thử lại.",
  aggregator_failed: "Công cụ lấy scope (scope_aggregator) lỗi hoặc quá thời gian.",
  program_not_found: "Không tìm thấy program.",
  scan_not_found: "Không tìm thấy scan (có thể đã bị xoá).",
  invalid_state: "Thao tác không hợp lệ ở trạng thái hiện tại của scan.",
  slug_collision: "Tên program bị trùng với program khác; đặt tên khác.",
};

/** Turn any thrown value into a sentence the user can act on. */
export function explain(error: unknown): string {
  if (error instanceof ApiError) {
    return BY_CODE[error.code] || error.message;
  }
  const message = error instanceof Error ? error.message : String(error);
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return "Không kết nối được backend. Kiểm tra ứng dụng còn chạy rồi tải lại trang.";
  }
  return message;
}
