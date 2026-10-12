# BBASM — Bug Bounty Attack Surface Management Dashboard
## BUILD SPEC / INSTRUCTION cho agent triển khai

> **Mục đích tài liệu:** Đây là bản kịch bản thi công đầy đủ. Agent triển khai đọc file này + các file nguồn được tham chiếu, rồi build ra sản phẩm. Mỗi phần có **tiêu chuẩn (standard)** và **test case**. Không tự ý đổi quyết định kiến trúc đã chốt ở §1. Nếu thiếu thông tin, hỏi người dùng (`vinhtqk5@gmail.com`) chứ không đoán.

> **Ngôn ngữ:** Mô tả tiếng Việt, code/định danh/đường dẫn giữ tiếng Anh.

---

## 0. TL;DR cho agent triển khai

Bạn sẽ build một **web dashboard ASM** (FastAPI + React, đóng Docker) ngồi *trên* framework `~/claude-bug-bounty` đã có. Dashboard:

1. Nhận input: **HackerOne handle/URL** *hoặc* **raw scope** (domain/IP/CIDR/file).
2. Chạy recon với **depth tùy chỉnh** (passive / light-active / strong-active) bằng cách **gọi lại** `tools/recon_engine.sh` + `tools/scope_aggregator.sh` có sẵn — KHÔNG viết lại recon.
3. Lưu kết quả vào **SQLite**, hiển thị realtime (WebSocket) trên UI: multi-program portfolio, ranked attack surface, diff theo thời gian, JS/secret + takeover monitor.
4. **Sinh ra per-target folder + `AGENT_BRIEF.md`** để người dùng `cd` vào và chạy `claude` — agent hunt chỉ đọc 1 brief gọn (~0 token setup). **Đây là mục tiêu cốt lõi: tiết kiệm token.**

Dashboard KHÔNG tự spawn agent hunt. KHÔNG tự submit. Con người bấm nút scan, con người chạy agent khi muốn.

---

## 1. QUYẾT ĐỊNH KIẾN TRÚC ĐÃ CHỐT (không đổi)

| # | Hạng mục | Lựa chọn đã chốt |
|---|---|---|
| 1 | Hình thức | **Web dashboard ASM** (không phải CLI/TUI) |
| 2 | Recon depth | **Tùy chỉnh**: `passive` / `light` (passive + httpx + nuclei nhẹ) / `strong` (full active: + nmap + ffuf + param) |
| 3 | Input | **HackerOne** (handle/URL) **+ raw scope** (domain / IP / CIDR / file hosts). *Các platform khác (BC/IT/YWH/IMF) KHÔNG bắt buộc phase 1* nhưng scope_aggregator đã hỗ trợ sẵn → để sau. |
| 4 | Portability | **Docker image** (`docker run` là xong trên máy mới) |
| 5 | Agent bridge | **Dashboard chuẩn bị folder + `AGENT_BRIEF.md`; người dùng tự chạy `claude`.** Không spawn agent, không full-auto. |
| 6 | ASM features | **Cả 4**: (a) multi-program portfolio, (b) continuous re-scan + diff, (c) ranked attack surface, (d) JS/secret + takeover monitor |
| 7 | Stack | **FastAPI + WebSocket (backend)** + **React (frontend)** |

---

## 2. NGUYÊN TẮC THIẾT KẾ (standards toàn cục)

1. **Reuse > Rebuild.** Mọi khả năng recon/scope/intel đã có trong `~/claude-bug-bounty/tools/`. Dashboard là **orchestrator + store + UI**, gọi lại script cũ qua subprocess. Chỉ viết mới phần còn thiếu (job runner, DB, API, UI, diff engine, brief generator).
2. **Deterministic setup = 0 token.** Toàn bộ scaffold + recon + brief do code làm, không cần LLM. LLM (agent hunt) chỉ vào sau khi brief đã sẵn sàng.
3. **Scope safety là bắt buộc.** Mọi request ra ngoài phải qua scope gate (xem §8.4). Raw scope có IP/CIDR phải được check đúng (scope_checker.py hiện KHÔNG hỗ trợ IP — xem §8.4, phải vá).
4. **Idempotent & resumable.** Scan lại một target không phá dữ liệu cũ; mỗi lần scan là một `scan_run` có timestamp để diff.
5. **Fail-soft.** Thiếu một tool (vd amass) thì skip + log warning, không crash cả pipeline (recon_engine.sh đã theo nguyên tắc này — giữ nguyên).
6. **Không chạy nền vô hạn.** Mọi job có timeout. Mọi job ghi trạng thái vào DB để UI/agent biết.
7. **Portable-first.** Mọi đường dẫn config qua ENV, không hardcode `/home/kali`. Chạy được trong container với volume mount.
8. **Mọi thứ có log.** Audit log mọi scan + mọi outbound host vào `audit.jsonl` (tái dùng pattern của autopilot).

---

## 3. MAP TÁI SỬ DỤNG — interface thật của tool có sẵn

> Agent triển khai: đây là các interface đã verify. Gọi đúng như sau, đừng tự dò lại.

### 3.1 `tools/recon_engine.sh` — recon pipeline chính
```
Usage: tools/recon_engine.sh <target> [--quick]
  <target> = FQDN | IP | CIDR | đường dẫn file (one host/line, # comment OK)  → "list mode"
ENV điều khiển:
  RECON_OUT_DIR   override thư mục output (mặc định $BASE_DIR/recon/<target>)
  BB_THREADS      (default 50)
  BB_RATE_LIMIT   req/s (default 150)
  BBHUNT_DASHBOARD=1   bật log marker để parse tiến độ
  WILDCARD_DNS_IP  (optional)
  NUC_SEV          severity nuclei (vd low,medium,high,critical)
  NUC_TIMEOUT      timeout nuclei (giây)
Output (nested) trong $RECON_DIR/:
  subdomains/  live/  ports/  urls/  js/  dirs/  params/  exposure/  nuclei/
  live/httpx_full.txt      (status,title,tech,content-length)
  live/urls.txt            (chỉ URL)
  live/status_200.txt  status_3xx.txt  status_403.txt  status_401.txt
  js/endpoints.txt
  urls/all.txt
  nuclei/ (kết quả nuclei)
```
- `--quick` = bản rút gọn. Dùng cho depth `passive`/`light`.
- **Tiêu chuẩn mapping depth → cờ:** xem §8.2.

### 3.2 `tools/scope_aggregator.sh` — pull scope từ platform
```
Usage: tools/scope_aggregator.sh <program-handle> [--platform h1|bc|it|ywh|imf|all]
                                  [--out <file>] [--include-oos] [--no-cache]
  - Dùng bbscope nếu có token, else bounty-targets-data dump (public, no cred).
  - Output: one host/line ra stdout (hoặc --out file). Status ra stderr.
  - Phase 1 chỉ cần --platform h1.
```

### 3.3 `tools/scope_checker.py` — scope gate deterministic
```python
from tools.scope_checker import ScopeChecker
sc = ScopeChecker(domains=["*.target.com","api.target.com"],
                  excluded_domains=[...], excluded_classes=[...])
sc.in_scope(url) -> bool   # anchored suffix match, chống subdomain confusion
# CLI: python3 tools/scope_checker.py (xem --help)
```
> **LIMITATION đã biết (phải xử lý):** class này KHÔNG hỗ trợ IP/CIDR (trả False + warning). Raw scope dạng IP phải dùng bộ check bổ sung bằng `ipaddress` (xem §8.4).

### 3.4 `tools/recon_adapter.py` — đọc output recon chuẩn hoá
```python
from tools.recon_adapter import load_recon
data = load_recon("target.com", recon_dir="recon")
# data.subdomains, data.live_hosts, data.urls, data.nuclei, data.technologies ...
```
> Dùng cái này để nạp kết quả recon vào DB thay vì tự parse từng file.

### 3.5 `tools/intel_engine.py` — intel/CVE/disclosed reports
```
python3 tools/intel_engine.py --target <d> --tech <csv> --program <h1handle> \
        --memory-dir <dir> [--json]
```
> Dùng để làm giàu `AGENT_BRIEF.md` (CVE theo tech stack, disclosed reports gần đây).

### 3.6 Ranking — tái dùng logic `surface` / agent `recon-ranker`
Có sẵn logic chấm điểm attack surface (API surface, tech match lịch sử, feature mới, nuclei hits). Agent triển khai: tìm hàm chấm điểm trong `tools/` (grep `rank`, `surface`, `target_selector.py`) và gọi lại; nếu chỉ tồn tại ở dạng agent prompt thì port công thức sang `bbasm/backend/ranking.py` (xem §12.3 cho công thức chuẩn).

### 3.7 Tool recon đã cài trên máy (đã verify có mặt)
`subfinder, httpx, dnsx, nuclei, katana, gau, amass, ffuf` = **yes**. Docker = yes.
Takeover: `tools/takeover_scanner.sh`. Secrets: `tools/secrets_hunter.sh`. JS: trong recon_engine (`js/`).

---

## 4. KIẾN TRÚC TỔNG THỂ

```
                    ┌─────────────────────────────────────────────┐
                    │                 BROWSER (React)             │
                    │  Portfolio · Target view · Surface · Diff   │
                    │  Scan form (H1 handle / raw scope + depth)  │
                    └───────────────▲──────────────┬──────────────┘
                           WebSocket │ (scan log)   │ REST (CRUD/query)
                    ┌───────────────┴──────────────▼──────────────┐
                    │              FastAPI backend                │
                    │  /api/*  +  /ws/scan/{id}                   │
                    │  ┌────────────┐  ┌───────────┐  ┌─────────┐ │
                    │  │ JobRunner  │  │ DiffEngine│  │ Brief   │ │
                    │  │ (asyncio)  │  │           │  │ Gen     │ │
                    │  └─────┬──────┘  └─────┬─────┘  └────┬────┘ │
                    └────────┼───────────────┼─────────────┼──────┘
                             │ subprocess     │ read DB     │ write files
              ┌──────────────▼───────┐   ┌────▼────┐   ┌────▼─────────────────┐
              │ ~/claude-bug-bounty/ │   │ SQLite  │   │ targets/<slug>/      │
              │  tools/recon_engine  │   │ bbasm.db│   │  AGENT_BRIEF.md      │
              │  tools/scope_aggreg. │   └─────────┘   │  recon/  findings/   │
              │  tools/scope_checker │                 │  CLAUDE.md  .scope   │
              │  tools/recon_adapter │                 └──────────────────────┘
              │  tools/intel_engine  │
              └──────────────────────┘
```

**Luồng chính:**
1. User nhập `h1:acme` (hoặc dán raw scope) + chọn depth trên UI → POST `/api/scans`.
2. Backend tạo `scan_run` (status=queued), trả `scan_id`. UI mở WS `/ws/scan/{scan_id}`.
3. JobRunner: (a) resolve scope → ghi `.scope` + allowlist; (b) chạy recon_engine với depth đã chọn, stream log qua WS; (c) `load_recon` → ghi asset/url/finding vào SQLite với `scan_run_id`; (d) DiffEngine so với `scan_run` trước → đánh dấu NEW/CHANGED/GONE; (e) ranking; (f) BriefGen ghi `AGENT_BRIEF.md` + scaffold folder.
4. UI cập nhật portfolio + surface + diff. User mở terminal: `cd targets/acme && claude`.

---

## 5. CẤU TRÚC THƯ MỤC SẢN PHẨM (phải tạo đúng)

```
bbasm/
├── BUILD_SPEC.md                 # file này
├── README.md                     # quickstart (docker run ...)
├── docker-compose.yml
├── Dockerfile                    # multi-stage: build React → runtime python+tools
├── .env.example
├── pyproject.toml | requirements.txt
├── backend/
│   ├── main.py                   # FastAPI app, mount static React build
│   ├── config.py                 # đọc ENV (§14)
│   ├── db.py                     # SQLite init + connection + migrations
│   ├── models.py                 # dataclasses/pydantic cho API
│   ├── schema.sql                # DDL (§6)
│   ├── jobs/
│   │   ├── runner.py             # JobRunner: queue, subprocess, stream log
│   │   ├── scope_resolver.py     # H1 handle | raw scope → allowlist + host list
│   │   ├── recon_orch.py         # map depth → recon_engine flags, chạy + parse
│   │   └── ingest.py             # load_recon → DB
│   ├── asm/
│   │   ├── diff_engine.py        # so sánh scan_run → NEW/CHANGED/GONE
│   │   ├── ranking.py            # chấm điểm attack surface (§12.3)
│   │   ├── monitors.py           # JS/secret + takeover (gọi script có sẵn)
│   │   └── scheduler.py          # continuous re-scan (APScheduler)
│   ├── brief/
│   │   ├── generator.py          # sinh AGENT_BRIEF.md + scaffold folder (§9,§10)
│   │   └── templates/            # Jinja2 templates cho brief, CLAUDE.md, .scope
│   ├── scope_gate.py             # wrapper scope_checker + IP/CIDR (§8.4)
│   ├── api/
│   │   ├── programs.py  targets.py  scans.py  surface.py  diff.py  ws.py
│   └── tests/                    # pytest (§16)
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx  routes
│       ├── pages/ Portfolio.tsx  Target.tsx  Surface.tsx  Diff.tsx  ScanNew.tsx
│       ├── components/ AssetTable  RankBadge  DiffBadge  ScanLog  TechChip ...
│       └── api/ client.ts  ws.ts
├── targets/                      # OUTPUT: mỗi target 1 folder (§10) — gitignore
│   └── <slug>/
│       ├── AGENT_BRIEF.md
│       ├── CLAUDE.md
│       ├── .scope                # allowlist 1 host/line (+ out-of-scope phần riêng)
│       ├── recon/                # RECON_OUT_DIR trỏ vào đây
│       ├── findings/  reports/  notes/
│       └── audit.jsonl
└── data/
    └── bbasm.db                  # SQLite (volume mount)
```

> **Tiêu chuẩn slug:** `slug = program-handle` (H1) hoặc domain apex (raw). Lowercase, chỉ `[a-z0-9.-]`, thay ký tự khác bằng `-`. Dùng làm tên folder + khoá target.

---

## 6. DATA MODEL — SQLite schema (`backend/schema.sql`)

> Tiêu chuẩn: SQLite, WAL mode. Mọi bảng có `created_at`/`updated_at` ISO-8601 UTC. Dùng `scan_run_id` để diff theo thời gian.

```sql
CREATE TABLE program (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,          -- "acme"
  source TEXT NOT NULL,              -- "h1" | "raw"
  handle TEXT,                       -- h1 handle / URL (nếu h1)
  platform TEXT DEFAULT 'h1',
  created_at TEXT, updated_at TEXT
);

CREATE TABLE scope_rule (            -- allowlist / denylist cho program
  id INTEGER PRIMARY KEY,
  program_id INTEGER REFERENCES program(id),
  pattern TEXT NOT NULL,             -- "*.acme.com" | "1.2.3.0/24" | "api.acme.com"
  kind TEXT NOT NULL,                -- "in" | "out"
  asset_type TEXT                    -- "domain" | "ip" | "cidr" | "url" | "other"
);

CREATE TABLE scan_run (
  id INTEGER PRIMARY KEY,
  program_id INTEGER REFERENCES program(id),
  depth TEXT NOT NULL,               -- "passive" | "light" | "strong"
  status TEXT NOT NULL,              -- queued|running|done|failed|cancelled
  started_at TEXT, finished_at TEXT,
  error TEXT,
  stats_json TEXT                    -- {"subs":318,"live":110,"new":4,...}
);

CREATE TABLE asset (                 -- host/subdomain
  id INTEGER PRIMARY KEY,
  program_id INTEGER REFERENCES program(id),
  host TEXT NOT NULL,                -- "api.acme.com"
  ip TEXT, status_code INTEGER,
  title TEXT, tech_json TEXT,        -- ["nginx","php"]
  first_seen_scan INTEGER,           -- scan_run.id khi xuất hiện lần đầu
  last_seen_scan INTEGER,
  state TEXT,                        -- "active" | "gone"
  rank_score REAL,                   -- điểm attack surface (§12.3)
  UNIQUE(program_id, host)
);

CREATE TABLE url (
  id INTEGER PRIMARY KEY,
  program_id INTEGER, asset_id INTEGER,
  url TEXT NOT NULL, source TEXT,    -- "katana"|"gau"|"wayback"|"js"
  first_seen_scan INTEGER, last_seen_scan INTEGER,
  UNIQUE(program_id, url)
);

CREATE TABLE finding (               -- nuclei / takeover / secret / js-endpoint
  id INTEGER PRIMARY KEY,
  program_id INTEGER, asset_id INTEGER,
  type TEXT,                         -- "nuclei"|"takeover"|"secret"|"js-endpoint"
  severity TEXT, name TEXT, detail_json TEXT,
  first_seen_scan INTEGER, last_seen_scan INTEGER,
  UNIQUE(program_id, type, name, asset_id)
);

CREATE TABLE diff_event (            -- log NEW/CHANGED/GONE cho continuous ASM
  id INTEGER PRIMARY KEY,
  program_id INTEGER, scan_run_id INTEGER,
  entity TEXT,                       -- "asset"|"url"|"finding"
  entity_ref TEXT,                   -- host/url/name
  change TEXT,                       -- "new"|"changed"|"gone"
  detail_json TEXT, created_at TEXT
);
```

**Test case schema:** `pytest` tạo DB tạm, insert 1 program + 2 scan_run, assert diff_event sinh đúng khi asset mới xuất hiện ở scan thứ 2. (chi tiết §16.2)

---

## 7. BACKEND API (FastAPI) — spec endpoint

> Tiêu chuẩn: tất cả trả JSON, lỗi theo `{"error": {"code","message"}}`, HTTP status đúng. Pydantic model cho request/response. CORS mở cho origin của frontend (config).

| Method & Path | Mục đích | Request | Response |
|---|---|---|---|
| `POST /api/scans` | Tạo scan mới | `{input:"h1:acme"\|"raw", scope?:["a.com","1.2.3.0/24"], depth:"passive\|light\|strong"}` | `{scan_id, program_slug}` |
| `GET  /api/scans/{id}` | Trạng thái scan | — | `{status, stats, started_at, finished_at, error}` |
| `POST /api/scans/{id}/cancel` | Huỷ scan | — | `{ok}` |
| `WS   /ws/scan/{id}` | Stream log realtime | — | lines: `{ts, level, phase, msg}` + event `{type:"phase", phase, state, note}` + `{type:"done", stats}` |
| `GET  /api/programs` | Portfolio list | — | `[{slug, source, last_scan, assets, live, new, top_rank}]` |
| `GET  /api/programs/{slug}` | Chi tiết 1 program | — | `{program, latest_scan, counts}` |
| `GET  /api/programs/{slug}/assets` | Bảng asset | `?state=&min_rank=&q=` | `[asset...]` sorted by rank desc |
| `GET  /api/programs/{slug}/surface` | Ranked surface | `?limit=25` | `[{host, rank, reasons[], tech, status}]` |
| `GET  /api/programs/{slug}/diff` | Diff mới nhất | `?scan_id=` | `{new:[], changed:[], gone:[]}` |
| `GET  /api/programs/{slug}/findings` | findings | `?type=&severity=` | `[finding...]` |
| `POST /api/programs/{slug}/brief` | Regen brief + folder | `{}` | `{path, bytes}` |
| `GET  /api/programs/{slug}/brief` | Lấy nội dung brief | — | `text/markdown` |
| `POST /api/programs/{slug}/schedule` | Bật continuous re-scan | `{interval:"6h\|daily\|weekly", depth}` | `{ok}` |
| `GET  /api/health` | healthcheck | — | `{ok, tools:{subfinder:true,...}}` |

**Test case API:** §16.3 — dùng `httpx.AsyncClient`/`TestClient`, mock JobRunner, assert status code + schema + thứ tự sort.

---

## 8. RECON ORCHESTRATION

### 8.1 Scope resolver (`jobs/scope_resolver.py`)
Input `POST /api/scans`:
- Nếu `input` bắt đầu `h1:<handle>` **hoặc** là URL `https://hackerone.com/<program>`:
  1. Parse ra `<handle>`.
  2. Gọi `tools/scope_aggregator.sh <handle> --platform h1 --out <tmp>`.
  3. Đọc `<tmp>` → list host in-scope. (Nếu rỗng → trả lỗi rõ ràng "scope empty, kiểm tra handle".)
  4. Lưu `program(source=h1, handle=...)` + `scope_rule(kind=in)`.
- Nếu `input == "raw"`: đọc `scope[]` (mỗi phần tử là domain/IP/CIDR hoặc path file). Phân loại `asset_type` (domain/ip/cidr) bằng `ipaddress` + regex. Lưu scope_rule.
- **Output:** ghi `targets/<slug>/.scope` (in-scope 1 host/line; phần out-of-scope trong section `# OUT` comment) + build allowlist cho scope gate.

**Standard:** slug hoá, chống trùng (nếu program đã tồn tại → tạo scan_run mới, không tạo program mới).

**Test:** `h1:acme` → mock aggregator trả 3 host → `.scope` có 3 dòng. `raw` với `["1.2.3.0/24","*.x.com"]` → phân loại cidr+domain đúng.

### 8.2 Depth → cấu hình recon (`jobs/recon_orch.py`)

> **Tiêu chuẩn mapping (bắt buộc đúng):**

| Depth | recon_engine flags/ENV | Các bước | Thời gian kỳ vọng |
|---|---|---|---|
| `passive` | `--quick`, `NUC_SEV=""` (skip nuclei), bỏ httpx-heavy | subfinder/crt.sh/amass passive + gau/wayback. KHÔNG chạm target nhiều. | < 2 phút |
| `light` *(default)* | `--quick`, `NUC_SEV=low,medium`, `NUC_TIMEOUT=300` | passive + httpx (live+tech) + nuclei nhẹ (safe templates). Không nmap/ffuf. | 3–8 phút |
| `strong` | full (không `--quick`), `NUC_SEV=low,medium,high,critical` | + nmap port scan + ffuf dir + param discovery + nuclei full. | 10–30+ phút |

- Set `RECON_OUT_DIR=targets/<slug>/recon`, `BBHUNT_DASHBOARD=1`, `BB_THREADS`, `BB_RATE_LIMIT` từ config.
- Với scope dạng **file list / nhiều host** (H1 không wildcard, hoặc raw nhiều host): ghi list ra file tạm và truyền file đó làm `<target>` (recon_engine "list mode") → bỏ qua subdomain brute vô ích.
- Với 1 apex domain có wildcard: truyền domain trực tiếp để enum subdomain.

**Standard:** recon_orch phải tôn trọng scope — chỉ feed host in-scope vào recon_engine.

**Test:** gọi với depth=light trên `example.com` (mock subprocess) → assert lệnh chứa `--quick` và ENV `NUC_SEV=low,medium`. depth=strong → không có `--quick`.

### 8.3 Ingest (`jobs/ingest.py`)
Sau khi recon xong: `load_recon(slug, recon_dir="targets/<slug>/recon")` → upsert `asset`, `url`, `finding` với `last_seen_scan = scan_run.id`; asset mới set `first_seen_scan`. Parse `live/httpx_full.txt` cho status/title/tech. Parse `nuclei/` cho findings. Gọi monitors (§12.4) cho takeover/secret/js.

**Test:** chuẩn bị fixture recon dir giả → ingest → DB có đúng số asset/url/finding.

### 8.4 SCOPE GATE (`scope_gate.py`) — BẮT BUỘC
Mọi host trước khi đưa vào recon_engine **và** mọi host agent định test phải qua gate.
- Domain/URL → dùng `ScopeChecker.in_scope()` (anchored suffix match).
- **IP/CIDR → scope_checker.py KHÔNG hỗ trợ.** Viết bổ sung dùng `ipaddress`: `ip in ip_network(cidr)`. Gộp thành `scope_gate.in_scope(target) -> bool` xử lý cả domain, IP, CIDR.
- Ghi mọi quyết định (allow/deny) vào `targets/<slug>/audit.jsonl`: `{ts, host, decision, rule}`.

**Test (quan trọng):**
- `evil-acme.com` KHÔNG match `*.acme.com` → deny. `sub.acme.com` → allow.
- `1.2.3.45` match rule `1.2.3.0/24` → allow; `1.2.4.1` → deny.
- host out-of-scope → deny + ghi audit.

---

## 9. AGENT_BRIEF.md — GENERATOR (lõi tiết kiệm token)

> **Tiêu chuẩn vàng:** Brief là **thứ DUY NHẤT** agent hunt cần đọc để bắt đầu. Phải self-contained, ≤ ~400 dòng / ~8KB. Không bắt agent đọc lại thư mục recon trừ khi đào sâu. Mọi con số là dữ liệu thật từ DB, không placeholder.

Template (`brief/templates/agent_brief.md.j2`) — các section:

```markdown
# HUNT BRIEF — {{slug}}   (depth={{depth}}, scan #{{scan_id}} @ {{finished_at}})

## 1. SCOPE (đọc trước khi gửi bất kỳ request nào)
IN  ({{n_in}}):  {{in_scope_patterns}}      # link .scope để full list
OUT ({{n_out}}): {{out_scope_patterns}}
Scope gate: targets/{{slug}}/.scope  — mọi target phải qua `bbasm.scope_gate`.

## 2. SỐ LIỆU
Subdomains: {{subs}}  | Live: {{live}}  | URLs: {{urls}}
Findings: nuclei {{n_nuclei}} (crit {{c}}/high {{h}}/med {{m}}), takeover {{n_to}}, secrets {{n_sec}}
Thay đổi so với scan trước: +{{new}} asset mới, {{gone}} mất.

## 3. TOP ATTACK SURFACE (ranked — bắt đầu từ đây)
| # | host | status | tech | rank | lý do |
|---|------|--------|------|------|-------|
{{#each top25}} ... {{/each}}

## 4. ASSET MỚI (ưu tiên — ít người test)
{{new_assets_table}}

## 5. SIGNALS
- nuclei hits đáng chú ý: {{nuclei_highlights}}
- takeover candidates: {{takeover_list}}
- secrets/JS endpoints thú vị: {{secret_js_highlights}}
- Intel (CVE theo tech / disclosed reports): {{intel_summary}}   # từ intel_engine.py

## 6. HƯỚNG TEST ĐỀ XUẤT (theo tech + lịch sử)
{{suggested_vuln_classes}}   # map tech→bug class, vd Flask→SSTI, GraphQL→introspection

## 7. CÁCH LÀM VIỆC
- Skills: /bug-bounty, /surface, /hunt, /validate, /report (framework ~/claude-bug-bounty).
- Recon data: ./recon/  (dùng nếu cần đào sâu, KHÔNG cần đọc hết).
- Validate trước khi report: 7-Question Gate + 4 gates.
- Mọi outbound qua scope gate. Log vào audit.jsonl.
```

**Standard:**
- Toàn bộ số liệu query từ SQLite, section 3/4 từ ranking + diff.
- Section 5 gọi monitors; section 5 intel gọi `intel_engine.py --json` (timeout, fail-soft nếu offline).
- Ghi file `targets/<slug>/AGENT_BRIEF.md`. Báo `{path, bytes}`.

**Test:** seed DB 1 program có 30 asset + 5 nuclei + 2 takeover → generate → assert file tồn tại, có đủ 7 section, `bytes < 12000`, top table ≤ 25 dòng, số liệu khớp DB.

---

## 10. SCAFFOLD PER-TARGET FOLDER (`brief/generator.py`)

Khi scan xong lần đầu, tạo (idempotent):
```
targets/<slug>/
  AGENT_BRIEF.md     # §9
  CLAUDE.md          # trỏ agent tới brief + skills + scope (template riêng)
  .scope             # §8.1
  recon/             # đã có (RECON_OUT_DIR)
  findings/ reports/ notes/   # rỗng, sẵn cho agent
  audit.jsonl        # scope decisions
```
`CLAUDE.md` template (ngắn, để agent vào là hiểu ngay):
```markdown
# {{slug}} — bug bounty target
ĐỌC `AGENT_BRIEF.md` TRƯỚC. Nó có scope, surface ranked, hướng test.
Scope gate: `.scope`. Recon thô: `recon/`. Ghi finding vào `findings/`.
Dùng skills framework: /bug-bounty /surface /hunt /validate /report.
KHÔNG test ngoài scope. Validate trước khi report.
```

**Standard:** không ghi đè `findings/`, `notes/` nếu đã có nội dung. `AGENT_BRIEF.md` + `CLAUDE.md` + `.scope` thì regenerate mỗi scan.

**Test:** scaffold 2 lần → lần 2 không xoá file người dùng đã thêm trong `notes/`.

---

## 11. FRONTEND (React + Vite + TS)

> Tiêu chuẩn: Vite build ra static, FastAPI serve. State qua React Query (REST) + native WebSocket (log). Responsive, chạy tốt ở phone width. Không cần đẹp cầu kỳ — rõ ràng, nhanh.

**Pages:**
1. **Portfolio** (`/`) — bảng các program: slug, source, last scan, #assets, #live, **#NEW** (badge), top rank. Nút "New scan". Click → Target.
2. **ScanNew** (`/scan/new`) — form: ô input (`h1:handle` / URL / textarea raw scope), radio depth (passive/light/strong), nút Start. Sau khi start → chuyển sang panel log realtime (WS): từng phase tick `[ ]→[⠹]→[✓]` + "Latest:" line (parse marker giống dashboard.py TUI).
3. **Target** (`/t/:slug`) — tabs: Overview (stats + stats diff), **Surface** (bảng ranked, cột lý do), **Assets** (filter state/rank/search), **Diff** (NEW/CHANGED/GONE), **Findings** (nuclei/takeover/secret), **Brief** (render AGENT_BRIEF.md + nút "Regen" + nút copy path để `cd`).
4. Nút "Enable monitoring" (schedule re-scan) trên Target.

**Components:** `AssetTable`, `RankBadge` (màu theo điểm), `DiffBadge` (NEW xanh / GONE xám / CHANGED vàng), `ScanLog`, `TechChip`, `SeverityTag`.

**Standard màu/skin:** theo dataviz nếu vẽ chart (phân bố severity, growth assets theo scan). Dark + light. (Nếu làm chart → đọc skill `dataviz` trước.)

**Test:** Vitest + React Testing Library cho components; Playwright e2e cho luồng "new scan → thấy log → thấy surface" (mock backend hoặc backend thật với target `example.com`).

---

## 12. ASM FEATURES NÂNG CAO (cả 4)

### 12.1 Multi-program portfolio
`GET /api/programs` gom mọi program + số liệu scan mới nhất + đếm diff NEW từ `diff_event`. UI Portfolio hiển thị. Sort theo #NEW desc (cái gì mới → đáng nhìn trước).

### 12.2 Continuous re-scan + diff (lõi ASM thật)
- `asm/scheduler.py` dùng **APScheduler**: mỗi program có thể bật interval (6h/daily/weekly). Scheduler enqueue scan_run mới (depth chọn lúc bật, mặc định `light`).
- `asm/diff_engine.py`: sau ingest, so `last_seen_scan == current` vs asset có `first_seen_scan == current` → NEW; asset không xuất hiện scan này nhưng active trước → mark `gone` + diff_event GONE; tech/status đổi → CHANGED. Ghi `diff_event`.
- **Standard:** diff phải ổn định (không báo NEW giả do thứ tự). So theo set host, không theo dòng file.

**Test:** 2 scan_run, scan2 thêm `new.acme.com`, bỏ `old.acme.com` → diff_event có đúng 1 NEW + 1 GONE.

### 12.3 Ranked attack surface — công thức chuẩn
Nếu không tìm thấy hàm rank sẵn, implement `asm/ranking.py` với công thức (0–10):
```
score = 0
+ api_surface:    host chứa api/graphql/v1/v2/rest, hoặc có path /api  → +2.5
+ auth_surface:   login/sso/oauth/admin/account                        → +2.0
+ fresh:          asset NEW ở scan này (first_seen == current)         → +1.5
+ tech_risk:      tech ∈ {graphql, flask, express, wordpress, jenkins,
                   gitlab, grafana, s3, firebase}                      → +1.5
+ nuclei_hit:     có finding nuclei (med+ → +2, low → +1)              → +2.0
+ status:         200 → +0.5 ; 401/403 (có gì đó bảo vệ) → +1.0
+ nonstd_port/odd title (dev,staging,test,internal)                    → +1.0
clamp 0..10. reasons[] = list lý do cộng điểm (để hiển thị cột "lý do").
```
Lưu `asset.rank_score`. Surface API sort desc.

**Test:** asset `api.acme.com` tech graphql status 200 NEW → score cao (≥7) + reasons chứa "api","graphql","fresh". Asset tĩnh `www` 200 không tech → score thấp.

### 12.4 JS/secret + takeover monitor (`asm/monitors.py`)
- Takeover: gọi `tools/takeover_scanner.sh` trên `subdomains/` → parse candidate → `finding(type=takeover)`.
- Secrets: gọi `tools/secrets_hunter.sh --js-bundle targets/<slug>/recon` → `finding(type=secret)`.
- JS endpoints: đã có `recon/js/endpoints.txt` → nạp thành `finding(type=js-endpoint)` (hoặc url source=js).
- **Standard:** fail-soft nếu tool thiếu. Mỗi finding gắn `asset_id` nếu map được host.

**Test:** fixture takeover output có 1 dangling CNAME → 1 finding type=takeover severity high.

---

## 13. DOCKER / PORTABILITY

> Mục tiêu: trên **máy mới chỉ cần Docker** là chạy được, tool recon đồng bộ 100%.

**Dockerfile (multi-stage):**
```
# stage 1: build frontend
FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package*.json ./ && RUN npm ci
COPY frontend/ . && RUN npm run build        # -> /fe/dist

# stage 2: runtime
FROM kalilinux/kali-rolling  (hoặc debian:bookworm + cài Go tools)
# cài: python3, pip, go, git, nmap, và Go recon tools:
#   subfinder httpx dnsx nuclei katana gau amass ffuf
# TÁI DÙNG ~/claude-bug-bounty/install_tools.sh để cài đúng bộ tool.
COPY backend/ /app/backend
COPY --from=fe /fe/dist /app/backend/static
# COPY hoặc git clone claude-bug-bounty vào /opt/claude-bug-bounty (ENV BBROOT)
RUN pip install -r requirements.txt
ENV BBASM_BBROOT=/opt/claude-bug-bounty
EXPOSE 8000
CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8000"]
```

**docker-compose.yml:**
```yaml
services:
  bbasm:
    build: .
    ports: ["8000:8000"]
    volumes:
      - ./data:/app/data          # SQLite bền
      - ./targets:/app/targets    # output folder cho agent cd vào
      - ~/.config/subfinder:/root/.config/subfinder:ro   # API keys (optional)
    env_file: .env
```

**Standard portability:**
- KHÔNG hardcode `/home/kali`. Dùng ENV `BBASM_BBROOT` (đường dẫn claude-bug-bounty), `BBASM_DATA`, `BBASM_TARGETS`.
- `nuclei -update-templates` chạy ở entrypoint lần đầu (hoặc build time).
- `/api/health` trả trạng thái từng tool → UI cảnh báo nếu thiếu.
- Nuclei/subfinder cần API key (Chaos, v.v.) → mount config hoặc ENV, fail-soft nếu không có.

**Test:** `docker build` thành công; `docker run` → `curl localhost:8000/api/health` trả `ok:true` + liệt kê tool; chạy scan `example.com` depth=passive trong container ra được brief.

---

## 14. CONFIG (`.env` / `backend/config.py`)
```
BBASM_BBROOT=/opt/claude-bug-bounty   # nơi có tools/
BBASM_DATA=/app/data
BBASM_TARGETS=/app/targets
BB_THREADS=50
BB_RATE_LIMIT=150
BBASM_DEFAULT_DEPTH=light
BBASM_MAX_CONCURRENT_SCANS=2
CORS_ORIGINS=http://localhost:5173,http://localhost:8000
# optional API keys
CHAOS_KEY=  GITHUB_TOKEN=  H1_USER= H1_TOKEN=   # bbscope
```
**Standard:** mọi giá trị có default an toàn; thiếu key → fail-soft.

---

## 15. BUILD PHASES — thứ tự thi công (từng bước)

> Agent triển khai làm tuần tự; cuối mỗi phase phải pass test của phase đó mới sang phase sau.

- **P0 — Khung & reuse check (0.5 ngày)**
  1. Tạo cấu trúc §5. `requirements.txt` (fastapi, uvicorn, pydantic, apscheduler, jinja2, pytest, httpx).
  2. `config.py` đọc ENV. Verify `BBASM_BBROOT/tools/recon_engine.sh` tồn tại. `/api/health` list tool.
  - *Test:* `pytest backend/tests/test_health.py` — health trả danh sách tool đúng.

- **P1 — DB + scope (1 ngày)**
  3. `schema.sql` + `db.py` (init, WAL). 4. `scope_resolver.py` (H1 + raw). 5. `scope_gate.py` (domain + IP/CIDR).
  - *Test:* §6, §8.1, §8.4.

- **P2 — Recon orchestration + ingest (1.5 ngày)**
  6. `recon_orch.py` (depth mapping). 7. `runner.py` (asyncio queue, subprocess, stream log ra WS, timeout, cancel). 8. `ingest.py` (`load_recon` → DB).
  - *Test:* §8.2, §8.3; integration scan thật `example.com` depth=passive.

- **P3 — ASM core (1.5 ngày)**
  9. `diff_engine.py`. 10. `ranking.py`. 11. `monitors.py`. 12. `scheduler.py`.
  - *Test:* §12.2, §12.3, §12.4.

- **P4 — Brief + scaffold (1 ngày)**
  13. `generator.py` + templates. 14. API `brief`.
  - *Test:* §9, §10.

- **P5 — API đầy đủ (1 ngày)**
  15. Tất cả endpoint §7 + WS.
  - *Test:* §16.3.

- **P6 — Frontend (2 ngày)**
  16. Pages + components §11. 17. Build static, FastAPI serve.
  - *Test:* Vitest components + Playwright e2e.

- **P7 — Docker + portability (1 ngày)**
  18. Dockerfile + compose + entrypoint (update templates). 19. README quickstart.
  - *Test:* §13.

- **P8 — Acceptance (0.5 ngày)** — chạy toàn bộ §17.

---

## 16. TEST CASES ĐẦY ĐỦ

> Tiêu chuẩn: `pytest` backend, `vitest`/Playwright frontend. CI chạy `pytest -q`. Coverage lõi (scope_gate, diff, ranking, brief) ≥ 90%.

### 16.1 Scope resolver
- TC-SR-1: `input="h1:acme"`, mock aggregator trả 3 host → program.source=h1, 3 scope_rule(in), `.scope` 3 dòng.
- TC-SR-2: `input="https://hackerone.com/acme"` → parse handle=acme.
- TC-SR-3: raw `["*.x.com","1.2.3.0/24","10.0.0.5"]` → asset_type = domain/cidr/ip đúng.
- TC-SR-4: aggregator trả rỗng → HTTP 422 "scope empty".
- TC-SR-5: scan lại program đã tồn tại → KHÔNG tạo program mới, tạo scan_run mới.

### 16.2 Scope gate (quan trọng — an toàn)
- TC-SG-1: `sub.acme.com` vs `*.acme.com` → allow.
- TC-SG-2: `evil-acme.com` vs `*.acme.com` → **deny** (chống subdomain confusion).
- TC-SG-3: `acme.com` vs `acme.com` → allow; vs `*.acme.com` → tuỳ quy ước (phải test & khớp doc).
- TC-SG-4: `1.2.3.45` vs `1.2.3.0/24` → allow; `1.2.4.1` → deny.
- TC-SG-5: host out-of-scope → deny + 1 dòng audit.jsonl `decision:deny`.
- TC-SG-6: URL có port/path → chuẩn hoá host rồi check.

### 16.3 API
- TC-API-1: `POST /api/scans` body hợp lệ → 200 + scan_id; body thiếu depth → 422.
- TC-API-2: `GET /api/scans/{id}` khi running → status running.
- TC-API-3: `GET /programs/{slug}/surface?limit=10` → ≤10 item, sort rank desc.
- TC-API-4: WS `/ws/scan/{id}` nhận ≥1 `phase` event + 1 `done` event (mock runner).
- TC-API-5: cancel scan đang chạy → status cancelled, subprocess bị kill.

### 16.4 Recon orchestration
- TC-RO-1: depth=passive → lệnh chứa `--quick`, không set NUC_SEV.
- TC-RO-2: depth=light → `--quick` + `NUC_SEV=low,medium`.
- TC-RO-3: depth=strong → KHÔNG `--quick` + `NUC_SEV` có high,critical.
- TC-RO-4: scope nhiều host → recon chạy "list mode" (truyền file), không brute subdomain.
- TC-RO-5: tool thiếu (giả lập subfinder vắng) → warning, pipeline tiếp tục.

### 16.5 Ingest + diff
- TC-IN-1: fixture recon dir → đúng N asset/url/finding vào DB.
- TC-DF-1: scan2 thêm host → 1 diff_event NEW.
- TC-DF-2: scan2 mất host → 1 diff_event GONE, asset.state=gone.
- TC-DF-3: tech đổi nginx→apache → diff_event CHANGED.
- TC-DF-4: cùng tập host 2 lần → 0 diff_event (ổn định, không false NEW).

### 16.6 Ranking
- TC-RK-1: `api.acme.com` graphql 200 NEW → score ≥7, reasons⊇{api,graphql,fresh}.
- TC-RK-2: `www.acme.com` 200 no-tech → score thấp (<3).
- TC-RK-3: host có nuclei medium → +2 phản ánh trong score.
- TC-RK-4: score luôn trong [0,10].

### 16.7 Monitors
- TC-MN-1: takeover fixture (dangling CNAME) → finding type=takeover.
- TC-MN-2: secret fixture → finding type=secret.
- TC-MN-3: tool vắng → 0 finding, không crash.

### 16.8 Brief + scaffold
- TC-BR-1: seed 30 asset/5 nuclei/2 takeover → brief tồn tại, đủ 7 section, bytes<12000.
- TC-BR-2: top table ≤25 dòng, số liệu khớp DB.
- TC-BR-3: section SCOPE liệt kê đúng in/out.
- TC-BR-4: scaffold 2 lần → `notes/` người dùng không bị xoá.
- TC-BR-5: brief viết bằng dữ liệu thật, grep không còn placeholder `{{`/`TODO`.

### 16.9 Frontend
- TC-FE-1: Portfolio render N program từ mock API, badge #NEW đúng.
- TC-FE-2: ScanNew submit → gọi POST /api/scans, mở WS, hiển thị phase tick.
- TC-FE-3: Surface tab sort theo rank, cột "lý do" hiển thị reasons.
- TC-FE-4: Diff tab tô màu NEW/GONE/CHANGED đúng.
- TC-FE-5 (Playwright e2e): new scan `example.com` passive → trong ≤X giây thấy surface + nút Brief.

### 16.10 Docker / portability
- TC-DK-1: `docker build` exit 0.
- TC-DK-2: container `curl /api/health` → ok, list tool đủ (subfinder/httpx/nuclei/...).
- TC-DK-3: scan passive `example.com` trong container → `targets/example.com/AGENT_BRIEF.md` xuất hiện trên volume host.
- TC-DK-4: không có biến `/home/kali` nào bị hardcode (grep source).

---

## 17. ACCEPTANCE CRITERIA (Definition of Done)

Sản phẩm được coi là HOÀN THÀNH khi **tất cả** đúng:

1. ✅ `docker compose up` → mở `http://localhost:8000`, UI load.
2. ✅ Nhập `h1:<program>` (program public thật) + depth=light → scan chạy, log realtime, kết thúc không lỗi.
3. ✅ Nhập raw scope (vd `example.com` + 1 CIDR) → scan chạy, scope gate chặn host ngoài list.
4. ✅ Portfolio hiển thị program; Surface có bảng ranked + lý do; Diff hiển thị NEW sau lần scan thứ 2.
5. ✅ `targets/<slug>/AGENT_BRIEF.md` sinh ra, ≤12KB, đủ 7 section, số liệu thật. `cd targets/<slug> && claude` → agent đọc brief là đủ để bắt đầu hunt (verify thủ công: agent không cần đọc lại recon để biết scope + surface).
6. ✅ Continuous monitoring bật được, lần re-scan tạo diff_event.
7. ✅ JS/secret + takeover monitor cho ra finding khi có.
8. ✅ `pytest -q` pass toàn bộ; coverage lõi ≥90%.
9. ✅ Chạy được trên **máy mới chỉ có Docker** (TC-DK-*), không sửa code.
10. ✅ Không test/scan ra ngoài scope ở bất kỳ đâu (audit.jsonl chứng minh).

**Tiêu chí token (mục tiêu gốc):** đo thủ công — so với flow cũ (dán link H1 + nhờ agent scaffold + recon thủ công), flow mới agent chỉ đọc 1 file brief. Ghi lại số token của bước "khởi động hunt" trước/sau vào README để chứng minh cải thiện.

---

## 18. GUARDRAILS (bảo mật & phạm vi)

- Chỉ hoạt động trên target **có trong scope** người dùng cung cấp. Scope gate chặn cứng. Không có chức năng "scan internet".
- Không tự khai thác, không tự submit report, không spray/credential attack trong dashboard này (những thứ đó thuộc framework gốc, do con người quyết định).
- Depth `strong` (nmap/ffuf) phải có cảnh báo UI "ồn ào, chỉ dùng khi scope cho phép active scan".
- Rate limit tôn trọng `BB_RATE_LIMIT`. Có nút cancel.
- Audit mọi outbound host.

## 19. NON-GOALS (phase 1 KHÔNG làm)

- Không spawn agent hunt / không full-auto pipeline (đã chốt).
- Không hỗ trợ BC/IT/YWH/IMF ở UI (aggregator sẵn sàng, để phase 2).
- Không auth/multi-user (chạy local 1 người). Nếu cần public → thêm auth sau.
- Không viết lại recon tool — chỉ orchestrate.

---

## 20. BÀN GIAO

Khi xong, agent triển khai để lại trong `bbasm/`:
- `README.md`: cách build/run (docker + dev), cách thêm target, cách `cd` chạy agent.
- Kết quả `pytest` + coverage.
- Ảnh/GIF demo luồng scan → brief (optional).
- Ghi chú lệch so với spec (nếu có) + lý do.

> Nếu gặp quyết định không có trong spec này, HỎI người dùng (`vinhtqk5@gmail.com`), không tự đoán.
