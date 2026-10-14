export type Depth = "passive" | "light" | "strong";
export type Category =
  | "web"
  | "wildcard"
  | "ip"
  | "cidr"
  | "source_code"
  | "mobile"
  | "other";

export type Config = {
  depth: Depth;
  threads: number;
  rate_limit: number;
  scan_timeout: number;
  nuclei_severity: string;
  skip_nmap: boolean;
  skip_nuclei: boolean;
  skip_active_crawl: boolean;
  categories_enabled: string[];
  excluded_hosts: string[];
};

export type ScopeEntry = {
  pattern: string;
  kind: "in" | "out";
  asset_type: string;
  category: Category;
  instruction?: string;
};

export type PreviewLine = {
  box: "in" | "out";
  line: number;
  raw: string;
  status: "ok" | "warn" | "error" | "skip";
  kind: "in" | "out";
  category: string;
  normalized: string;
  note: string;
};

export type Preview = {
  mode: "raw" | "h1";
  ok: boolean;
  message: string;
  handle?: string | null;
  summary: { in: number; out: number; errors: number; warnings: number };
  lines: PreviewLine[];
};

export type ScanRow = {
  id: number;
  depth: Depth;
  status: string;
  trigger?: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

export type ReviewData = {
  scan: ScanRow;
  slug: string;
  source: string;
  handle: string | null;
  target_path: string;
  hunt_command: string;
  hunt_note: string;
  scope: ScopeEntry[];
  warnings: string[];
  automation_ack: string | null;
  policy: {
    text: string;
    source: string | null;
    fetched_at: string | null;
    user_text: string;
  };
  stats: Record<string, any>;
};

export type Health = {
  ok: boolean;
  tools: Record<string, boolean>;
  missing_by_depth: Record<string, string[]>;
  h1_api: boolean;
};

export type ProgramCard = {
  id: number;
  slug: string;
  source: string;
  asset_count: number;
  new_count: number;
  finding_count: number;
  draft_count: number;
  monitoring: boolean;
  latest_scan: ScanRow | null;
};

export type Draft = {
  id: number;
  slug: string;
  source: string;
  depth: Depth;
  created_at: string | null;
  in: number;
  out: number;
};

export type Asset = {
  id: number;
  host: string;
  title?: string | null;
  status_code?: number | null;
  tech?: string[];
  reasons?: string[];
  rank_score?: number | null;
  category?: string | null;
  state?: string;
};

export type Summary = {
  slug: string;
  source: string;
  handle: string | null;
  target_path: string;
  hunt_command: string;
  hunt_note: string;
  latest_scan: ScanRow | null;
  last_completed_scan: ScanRow | null;
  changes: { new: number; changed: number; gone: number };
  findings_by_severity: Record<string, number>;
  assets_active: number;
  top_surface: Asset[];
  draft_count: number;
  schedule: {
    interval: string;
    depth: Depth;
    enabled: number;
    next_run_at: string | null;
  } | null;
};
