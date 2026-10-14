export const TERMINAL = new Set(["done", "done_partial", "failed", "cancelled"]);

export const STATUS_LABEL: Record<string, string> = {
  draft: "bản nháp",
  queued: "đang chờ",
  running: "đang chạy",
  done: "hoàn tất",
  done_partial: "hoàn tất một phần",
  failed: "lỗi",
  cancelled: "đã huỷ",
};

export function cidrSize(pattern: string): number | null {
  const m = /^([0-9a-f:.]+)\/(\d{1,3})$/i.exec(pattern);
  if (!m) return null;
  const bits = Number(m[2]);
  const total = m[1].includes(":") ? 128 : 32;
  if (bits > total) return null;
  const size = 2 ** (total - bits);
  return Number.isFinite(size) ? size : null;
}

export function formatCount(n: number): string {
  return n.toLocaleString("vi-VN");
}

export function durationLabel(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds)} giây`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} phút`;
  return `${(seconds / 3600).toFixed(1)} giờ`;
}

export function when(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("vi-VN");
}
