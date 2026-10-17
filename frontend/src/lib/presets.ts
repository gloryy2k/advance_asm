import type { Config, Depth } from "../api/types";

export type Preset = {
  depth: Depth;
  title: string;
  tagline: string;
  detail: string;
  touches: boolean;
  eta: string;
  tools: string[];
};

export const PRESETS: Preset[] = [
  {
    depth: "passive",
    title: "Passive",
    tagline: "Không chạm vào target",
    detail:
      "Chỉ dùng nguồn công khai (DNS/certificate/lịch sử URL). Không probe, không crawl, không nuclei. An toàn nhất; brief sẽ thiếu tech/trạng thái live.",
    touches: false,
    eta: "dưới ~5 phút",
    tools: ["subfinder", "gau"],
  },
  {
    depth: "light",
    title: "Light",
    tagline: "Khuyến nghị cho phần lớn program",
    detail:
      "Probe HTTP + nhận diện tech, crawl nhẹ, nuclei mức low/medium. Không quét cổng, không brute thư mục.",
    touches: true,
    eta: "~5–15 phút",
    tools: ["subfinder", "gau", "httpx", "katana", "nuclei"],
  },
  {
    depth: "strong",
    title: "Strong",
    tagline: "Ồn ào — chỉ khi policy cho phép active scan",
    detail:
      "Thêm quét cổng nmap, fuzz thư mục ffuf, nuclei tới critical. Dễ chạm rate limit/WAF và bị coi là tấn công nếu program cấm.",
    touches: true,
    eta: "~15–45 phút",
    tools: ["subfinder", "gau", "httpx", "katana", "nuclei", "nmap", "ffuf", "amass"],
  },
];

export const TIMEOUT: Record<Depth, number> = { passive: 300, light: 900, strong: 7200 };
export const SEVERITY_LEVELS = ["info", "low", "medium", "high", "critical"] as const;

/** One place that knows what each preset sets, so Review never shows a half-changed config. */
export function applyPreset(config: Config, depth: Depth): Config {
  return {
    ...config,
    depth,
    scan_timeout: TIMEOUT[depth],
    skip_nmap: depth !== "strong",
    skip_nuclei: depth === "passive",
    skip_active_crawl: depth === "passive",
    nuclei_severity: {
      passive: "",
      light: "low,medium",
      strong: "low,medium,high,critical",
    }[depth],
  };
}
