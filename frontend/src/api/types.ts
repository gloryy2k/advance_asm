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
  skip_ffuf: boolean;
  nuclei_allow_intrusive?: boolean;
  nuclei_auto_select?: boolean;
  ffuf_confirmed?: boolean;
  nuclei_custom?: string[];
  skip_historical: boolean;
  skip_takeover: boolean;
  skip_secrets: boolean;
  max_js_files: number;
  url_exclude_patterns: string[];
  brief_budget_kb: number;
  brief_top_assets: number;
  brief_top_urls: number;
  /** "Name: value" headers the program's policy requires on requests to the target. Per program, never part of a profile. */
  request_headers?: string[];
  allow_active_on_path_rules?: boolean;
  skipped_headers?: string[];
  skip_required_headers?: boolean;
  nmap_timeout?: number | null;
  ffuf_maxtime?: number | null;
  nuclei_timeout?: number | null;
  deep_hosts?: number | null;
  source_full_repo_ok?: string[];
  include_apex?: string[];
  apex_confirmed?: boolean;
};

export const RECIPE_FIELDS = [
  "depth", "threads", "rate_limit", "scan_timeout", "nuclei_severity", "skip_nmap", "skip_nuclei",
  "skip_active_crawl", "skip_ffuf", "nmap_timeout", "ffuf_maxtime", "nuclei_timeout", "deep_hosts", "nuclei_allow_intrusive", "nuclei_auto_select", "skip_historical", "skip_takeover", "skip_secrets", "max_js_files",
  "url_exclude_patterns", "brief_budget_kb", "brief_top_assets", "brief_top_urls",
] as const;
export type Recipe = Partial<Pick<Config, (typeof RECIPE_FIELDS)[number]>>;

export type Profile = {
  id: number | string;
  name: string;
  description: string;
  based_on: string;
  builtin: boolean;
  config: Required<Recipe>;
};

export type PlanPhase = {
  key: string;
  title: string;
  what: string;
  touches: boolean;
  status: "on" | "off" | "missing_tool";
  reason: string | null;
  forced?: boolean;
  view: { kind: string; label: string; filter?: Record<string, string> };
};

export type PhaseFile = { path: string; name: string; label: string; bytes: number; lines: number | null };
export type PhaseReport = {
  key: string;
  title: string;
  what: string;
  touches: boolean;
  status: "ran" | "partial" | "empty" | "skipped" | "missing_tool" | "no_output" | "timeout" | "pending";
  status_label: string;
  reason: string | null;
  detail?: string | null;
  partial?: boolean;
  count: number;
  count_label: string;
  files: PhaseFile[];
  view: { kind: string; label: string; filter?: Record<string, string> };
};
export type StageRecord = { key: string; label: string; status: string; budget_s: number; used_s: number; commands: number; commands_ok?: number; commands_timeout?: number; commands_skipped?: number };
export type SourceRecord = { source: string; status: "ok" | "timeout" | "error"; seconds: number; stage?: string };
export type Coverage = {
  discovered: number; probed: number; unprobed: number; explicit: number; batches: number; batches_done: number;
  attempted?: number; responded?: number; completed?: number; unreached?: number; batches_timeout?: number;
};
export type AssetCoverage = {
  pattern: string; category: string; mode: "recon" | "recon_host" | "secrets_only" | "manual_confirm" | "manual" | "passive_only" | "off";
  label: string; detail: string; instruction?: string; needs_confirmation?: boolean;
};
export type DataNote = { fix: string; at: string; note: string };
export type ScanProgressData = {
  stages?: StageRecord[];
  coverage?: Coverage | null;
  sources?: SourceRecord[];
  partial_inputs?: { command: string; found: number; in_scope: number; files: string[] }[];
  path_rule_hosts?: Record<string, string[]>;
  missing_needed?: string[];
  tool_notes?: { tool: string; note: string }[];
  asset_coverage?: AssetCoverage[];
  repairs?: DataNote[];
};
export type ScanPhases = ScanProgressData & {
  scan_id: number;
  slug: string;
  status: string;
  depth: string;
  phases: PhaseReport[];
  funnel: UrlFunnel | null;
  missing_tools: string[];
};

export type UrlFunnel = {
  raw: number;
  in_scope: number;
  from_probe?: number;
  stored?: number;
  out_of_scope: number;
  invalid: number;
  excluded_by_rule?: number;
  path_rule_blocked?: number;
  by_path_rule?: { rule: string; count: number }[];
  by_tag?: Record<string, number>;
  by_verification?: Record<string, number>;
  out_of_scope_hosts?: { host: string; count: number }[];
};
export type UrlRow = {
  id: number;
  url: string;
  host: string | null;
  source: string;
  score: number;
  verification: string;
  shape: string | null;
  tags: string[];
  first_seen_scan: number;
  last_seen_scan: number;
  is_new: boolean;
};
export type UrlSummary = {
  scan_id: number | null;
  scope?: string;
  latest?: { id: number; depth: string; status: string; finished_at: string | null } | null;
  history_total: number;
  total: number;
  funnel: UrlFunnel | null;
  by_tag: Record<string, number>;
  top_shapes: { shape: string; count: number; max_score: number; example: string }[];
  hosts: { host: string; count: number }[];
};
export type Trust = {
  level: "manual" | "api" | "public_page" | "public";
  verified: boolean;
  label: string;
  detail: string;
  missing: string[];
  checklist: string[];
  official_url: string | null;
  source?: string | null;
  fetched_at?: string | null;
};

export type LaunchGate = { allowed_depths: Depth[]; reasons: string[]; missing: string[] };
export type SourceAttempt = { source: "api" | "public_page" | "public_dump"; ok: boolean; reason?: string };
export type Unclassified = { identifier: string; kind: "in" | "out"; asset_type: string; reason: string; blocking?: boolean };

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
  shadowed_by?: string;
};

export type Preview = {
  mode: "raw" | "h1";
  ok: boolean;
  message: string;
  handle?: string | null;
  summary: { in: number; out: number; effective_in?: number; errors: number; warnings: number };
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
  trust: Trust;
  scan: ScanRow;
  slug: string;
  source: string;
  handle: string | null;
  target_path: string;
  hunt_command: string;
  hunt_note: string;
  scope: ScopeEntry[];
  request_header_hints?: string[];
  archived?: boolean;
  policy_newer?: boolean;
  newest_draft?: number | null;
  warnings: string[];
  automation_ack: string | null;
  policy: {
    text: string;
    source: string | null;
    fetched_at: string | null;
    user_text: string;
    attempts?: SourceAttempt[];
    completeness?: { in: { fetched: number; total: number }; out: { fetched: number; total: number } } | null;
    classification?: { classified?: number; unclassified_count?: number; unclassified?: Unclassified[] };
  };
  launch_gate?: LaunchGate;
  stats: Record<string, any>;
};

export type Health = {
  ok: boolean;
  tools: Record<string, boolean>;
  missing_by_depth: Record<string, string[]>;
  h1_api: boolean;
  runtime?: { os: string; recon_supported: boolean; reason: string };
  optional_tools?: string[];
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
  archived_at?: string | null;
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
  trust?: Trust;
  default_profile_id?: number | null;
  request_headers?: string[];
  request_header_hints?: string[];
  archived_at?: string | null;
  data_notes?: DataNote[];
  assets_live?: number;
  assets_gone?: number;
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
    paused_by_archive?: number | null;
    last_error?: string | null;
    last_error_at?: string | null;
    config?: { depth: Depth; threads: number; rate_limit: number; request_header_names: string[]; skipped_headers: string[] };
  } | null;
};

export type TreeNode = {
  name: string;
  display: string;
  kind: "host" | "dir" | "file";
  host: string;
  path: string;
  count: number;
  self_count: number;
  variants: number;
  has_children: boolean;
  max_score: number;
  tags: string[];
  verification: string;
  is_new: boolean;
  first_seen_scan: number | null;
  last_seen_scan: number | null;
  url: string | null;
  sources?: string[];
  children: TreeNode[] | null;
  children_total?: number;
};
export type TreeLevel = { scan: string; scan_id: number | null; host: string | null; prefix: string; nodes: TreeNode[]; total: number; matched?: number; truncated: boolean };

export type ToolRow = {
  id: string;
  kind: "binary" | "data" | "framework";
  label: string;
  purpose: string;
  state: "ready" | "missing_binary" | "missing_data" | "wrong_binary";
  detail: string;
  required_for: Depth[];
  optional: boolean;
  used_by: { key: string; title: string }[];
  pinned_version: string | null;
  version: string | null;
  checked_at: string | null;
  remedy: string;
  impact: Record<Depth, string>;
  templates?: TemplateInfo;
};
export type ToolsReport = {
  tools: ToolRow[];
  depths: Depth[];
  runtime: { os: string; recon_supported: boolean };
  summary: { ready: number; missing_required: string[]; missing_optional: string[]; missing_framework: string[] };
};
export type TemplateInfo = {
  installed: boolean;
  count: number;
  managed?: boolean;
  dir?: string;
  updated_at: string | null;
  source: string | null;
  version: string | null;
  job: { state: "idle" | "running" | "ok" | "failed"; started_at: string | null; finished_at: string | null; message: string; count: number | null } | null;
  custom: { id: string; name: string; enabled: boolean; bytes: number; added_at: string }[];
};

export type DeletePreview = {
  slug: string;
  archived: boolean;
  counts: Record<string, number>;
  has_schedule: boolean;
  folder: { path: string; files: number; bytes: number };
  blockers: string[];
};

export type ChartsData = {
  trend: { id: number; depth: Depth; status: string; finished_at: string | null; hosts: number | null; live: number | null; urls: number | null; findings: number | null; new: number; changed: number; gone: number }[];
  truncated: boolean;
  status: { classes: Record<string, number>; codes: { code: number; count: number }[]; total: number };
  tech: { name: string; count: number }[];
  hosts_by_urls: { host: string; urls: number; top_score: number }[];
  severity_matrix: { severities: string[]; hosts: ({ host: string } & Record<string, number | string>)[] };
};
