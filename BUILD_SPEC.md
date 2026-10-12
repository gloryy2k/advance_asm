# BBASM — Bug Bounty Attack Surface Management Dashboard
## BUILD SPEC / INSTRUCTION cho agent triển khai — **v2.3**

> **Mục đích tài liệu:** Đây là bản kịch bản thi công đầy đủ. Agent triển khai đọc file này + các file nguồn được tham chiếu, rồi build ra sản phẩm. Mỗi phần có **tiêu chuẩn (standard)** và **test case**. Không tự ý đổi quyết định kiến trúc đã chốt ở §1. Nếu thiếu thông tin, hỏi người dùng (`vinhtqk5@gmail.com`) chứ không đoán.

> **Ngôn ngữ:** Mô tả tiếng Việt, code/định danh/đường dẫn giữ tiếng Anh.

### 📌 CHANGELOG v1 → v2 (sau review đối chiếu code thật)
- **[C1]** Sửa lại §8.2 depth mapping: `recon_engine.sh` tính `NUC_SEV` nội bộ theo `--quick` (KHÔNG đọc ENV) và luôn chạy nmap/httpx/katana/nuclei → không có "passive only". Yêu cầu **patch `recon_engine.sh`** thêm toggle ENV (hướng A) — xem §8.2.
- **[C2]** §8.1: scope rule phải giữ **pattern wildcard** (`*.acme.com`), không chỉ resolved host. + test TC-SG-7.
- **[C3]** §13: chốt `claude-bug-bounty` vào image bằng **git submodule**.
- **[C4]** §8.5 (mới): JobRunner kill **cả process group** (`os.setsid`+`killpg`).
- **[C5]** §13: `strong` depth cần `cap_add: [NET_RAW, NET_ADMIN]` cho nmap.
- **[H1]** §6 thêm bảng `schedule`; §12.2 APScheduler dùng SQLAlchemy jobstore (persist).
- **[H2]** §8.5: WebSocket log buffer + replay khi reconnect.
- **[H3]** §8.5: phân biệt `failed` vs `done-partial`, vẫn ingest phần có.
- **[H4]** §14: `BBASM_SCAN_TIMEOUT_*` hard timeout mỗi depth.
- **[H5]** §14/§18: default bind `127.0.0.1`.
- **[H6]** §8.1: raw scope = **text dán từng dòng** (+ upload optional), bỏ "path file host".
- **[H7]** §8.1: nhận dạng & parse URL `.../policy_scopes`.
- **[M1–M9]** rải rác: ingest idempotent, slug collision, severity enum, DB index, brief size chốt ≤12KB, passive degraded, health test, invalid-depth 422, schema version.
- **[§15]** +6 bước checklist. **[§16]** +13 test case.

### 📌 CHANGELOG v2 → v2.1
- **[§10.1 + API + §16]** Thêm tính năng **Export ZIP** cấu trúc folder `targets/<slug>/` (+ `MANIFEST.json`) + 6 test TC-EXP-*.
- **[§21 mới]** Ghi chú build bằng agent không-phải-Claude (Codex): fork submodule, tách unit/integration test, không phụ thuộc Claude skills lúc build.

### 📌 CHANGELOG v2.1 → v2.2 — **xem §22 (chi tiết, SUPERSEDE phần tương ứng ở §7/§8)**
- **[§22.1]** Scan 2 pha: **resolve → REVIEW CONFIG → launch**. Recon KHÔNG chạy ngay; thêm `scan_run.status=draft` + bảng `scan_config`. User chỉnh rate limit/thread/timeout/scope/toggle trước khi chạy.
- **[§22.2]** Luồng xử lý input H1 URL / `/policy_scopes` / raw — từng bước.
- **[§22.3]** Scope **cross-platform**: phân loại `asset_type` (web/wildcard/cidr/**source_code**/**mobile**/other) + routing khác nhau (source_code→secrets/git, mobile→manual). Thêm cột `asset.category`.
- **[§22.4]** Nơi lưu instruction: **`PROGRAM.md`** (bền, không ghi đè) + `AGENT_BRIEF.md` (tái sinh) + DB. Agent đọc cả hai.
- **[§22.5]** Schema/API/UI/test/checklist deltas.
- **[§21]** Submodule chốt: `gloryy2k/claude-bug-bounty` (bản `tools/` đang chạy, pin @32131c1) — vì upstream `awarexone/Agentic-Bug-Hunter` đã đổi sang layout `bughunter/`, không còn `tools/recon_engine.sh`.

### 📌 CHANGELOG v2.2 → v2.3 — review end-to-end nhất quán + upgrade path
- **Fix mâu thuẫn:** `scan_run.status` thêm `draft` (§6); §4 "Luồng" viết lại theo two-phase (resolve→review→launch).
- **Gộp schema:** `program.policy_json`, `asset.category`, bảng `scan_config` đưa thẳng vào §6 (không chỉ ở §22.5) → single source of truth.
- **`PROGRAM.md`** bổ sung vào scaffold (§10) + nội dung ZIP (§10.1) + diagram/tree.
- **Scheduler auto-launch:** scan tự động **bỏ qua review**, chạy thẳng bằng config của `schedule` (§12.2).
- **API:** thêm `GET/PUT /api/programs/{slug}/program` (đọc/sửa PROGRAM.md).
- **[§23 mới] UPGRADE PATH** sang layout `bughunter/` (bản upstream mới) — checklist nâng cấp khi cần.
- Nhỏ: path `~/claude-bug-bounty` → `vendor/claude-bug-bounty` (BBROOT); title v2.3.

---

## 0. TL;DR cho agent triển khai

Bạn sẽ build một **web dashboard ASM** (FastAPI + React, đóng Docker) ngồi *trên* framework đã có (vendored tại `vendor/claude-bug-bounty`, trỏ bởi `$BBASM_BBROOT`). Dashboard:

1. Nhận input: **HackerOne handle/URL (+ `/policy_scopes`)** *hoặc* **raw scope** (domain/IP/CIDR, dán text).
2. Chạy recon với **depth tùy chỉnh** (passive / light / strong) bằng cách **gọi lại** `recon_engine.sh` + `scope_aggregator.sh` có sẵn — KHÔNG viết lại recon (chỉ **patch nhỏ** recon_engine để bật toggle ENV, xem §8.2).
3. Lưu kết quả vào **SQLite**, hiển thị realtime (WebSocket): multi-program portfolio, ranked attack surface, diff theo thời gian, JS/secret + takeover monitor.
4. **Sinh ra per-target folder + `AGENT_BRIEF.md`** để người dùng `cd` vào và chạy `claude` — agent hunt chỉ đọc 1 brief gọn (~0 token setup). **Đây là mục tiêu cốt lõi: tiết kiệm token.**

Dashboard KHÔNG tự spawn agent hunt. KHÔNG tự submit. Con người bấm nút scan, con người chạy agent khi muốn.

---

## 1. QUYẾT ĐỊNH KIẾN TRÚC ĐÃ CHỐT (không đổi)

| # | Hạng mục | Lựa chọn đã chốt |
|---|---|---|
| 1 | Hình thức | **Web dashboard ASM** (không phải CLI/TUI) |
| 2 | Recon depth | **Tùy chỉnh**: `passive` / `light` / `strong` (định nghĩa chính xác ở §8.2) |
| 3 | Input | **HackerOne** (handle/URL + policy_scopes) **+ raw scope** (domain / IP / CIDR, dán text). *Platform khác (BC/IT/YWH/IMF) để phase 2.* |
| 4 | Portability | **Docker image** (`docker run` là xong trên máy mới) |
| 5 | Agent bridge | **Dashboard chuẩn bị folder + `AGENT_BRIEF.md`; người dùng tự chạy `claude`.** Không spawn agent, không full-auto. |
| 6 | ASM features | **Cả 4**: (a) multi-program portfolio, (b) continuous re-scan + diff, (c) ranked attack surface, (d) JS/secret + takeover monitor |
| 7 | Stack | **FastAPI + WebSocket (backend)** + **React (frontend)** |

---

## 2. NGUYÊN TẮC THIẾT KẾ (standards toàn cục)

1. **Reuse > Rebuild.** Mọi khả năng recon/scope/intel đã có trong `vendor/claude-bug-bounty/tools/` (= `$BBASM_BBROOT/tools/`). Dashboard là **orchestrator + store + UI**, gọi lại script cũ qua subprocess. Chỉ viết mới phần còn thiếu + **patch tối thiểu** recon_engine (§8.2).
2. **Deterministic setup = 0 token.** Toàn bộ scaffold + recon + brief do code làm, không cần LLM. LLM (agent hunt) chỉ vào sau khi brief đã sẵn sàng.
3. **Scope safety là bắt buộc.** Mọi request ra ngoài phải qua scope gate (§8.4), giữ cả wildcard pattern. Raw scope IP/CIDR phải check đúng.
4. **Idempotent & resumable.** Scan lại một target không phá dữ liệu cũ; mỗi lần scan là một `scan_run` có timestamp để diff. Ingest chạy lại không nhân đôi.
5. **Fail-soft.** Thiếu một tool thì skip + log warning, không crash cả pipeline. Recon exit ≠ 0 vẫn ingest phần có (§8.5).
6. **Không chạy nền vô hạn.** Mọi job có **hard timeout** (§14) + nút cancel (kill cả process group).
7. **Portable-first.** Mọi đường dẫn qua ENV, không hardcode `/home/kali`. Chạy trong container với volume mount. Default bind `127.0.0.1`.
8. **Mọi thứ có log.** Audit mọi scan + mọi outbound host vào `audit.jsonl`.

---

## 3. MAP TÁI SỬ DỤNG — interface thật của tool có sẵn

> Agent triển khai: đây là interface đã verify. Gọi đúng như sau, đừng tự dò lại. **Nhưng vẫn phải đọc `recon_engine.sh` một lượt** trước khi làm §8.2 (sẽ patch nó).
> **Quy ước path:** mọi `tools/<x>` dưới đây = `$BBASM_BBROOT/$BBASM_TOOLS_SUBDIR/<x>` (bản pin hiện tại: `$BBASM_TOOLS_SUBDIR=tools`; xem §14/§23). Code tuyệt đối KHÔNG hardcode `tools/`, luôn build qua 2 ENV đó.

### 3.1 `tools/recon_engine.sh` — recon pipeline chính
```
Usage: tools/recon_engine.sh <target> [--quick]
  <target> = FQDN | IP | CIDR | đường dẫn file (one host/line, # comment OK)  → "list mode"
  --quick là tham số vị trí thứ 2 ($2).
ENV điều khiển (đã verify):
  RECON_OUT_DIR   override thư mục output (mặc định $BASE_DIR/recon/<target>)
  BB_THREADS      (default 50)
  BB_RATE_LIMIT   req/s (default 150)
  BBHUNT_DASHBOARD=1   bật log marker để parse tiến độ
  WILDCARD_DNS_IP  (optional)
Output (nested) trong $RECON_DIR/:
  subdomains/  live/  ports/  urls/  js/  dirs/  params/  exposure/  nuclei/
  live/httpx_full.txt   live/urls.txt   live/status_{200,3xx,403,401}.txt
  js/endpoints.txt      urls/all.txt    nuclei/
```
> ⚠️ **HÀNH VI THẬT của `--quick` (đã đọc code — KHÁC với giả định v1):**
> - `--quick` CHỈ: skip `amass`; giảm limit (ffuf MAX_FUZZ 2 vs 5; nuclei NUC_LIMIT 50 vs 200; takeover SUB_LIMIT 100 vs 500).
> - `NUC_SEV` / `NUC_LIMIT` / `NUC_TIMEOUT` được **tính nội bộ theo `--quick`, KHÔNG đọc từ ENV** (dòng ~610-612).
> - `nmap -sV --top-ports 1000`, `httpx`, `katana`, `nuclei` **LUÔN chạy** bất kể `--quick`.
> - ⇒ Không có "passive only" sẵn. Phải patch (§8.2).

### 3.2 `tools/scope_aggregator.sh` — pull scope từ platform
```
Usage: tools/scope_aggregator.sh <program-handle> [--platform h1|bc|it|ywh|imf|all]
                                  [--out <file>] [--include-oos] [--no-cache]
  - bbscope nếu có token, else bounty-targets-data dump (public, no cred).
  - Output: one entry/line ra stdout (hoặc --out file). Status ra stderr.
  - ⚠️ Entry CÓ THỂ là wildcard pattern (vd "*.acme.com") — GIỮ NGUYÊN, đừng resolve/bỏ.
  - Phase 1 chỉ cần --platform h1.
```

### 3.3 `tools/scope_checker.py` — scope gate deterministic
```python
from tools.scope_checker import ScopeChecker
sc = ScopeChecker(domains=["*.target.com","api.target.com"],
                  excluded_domains=[...], excluded_classes=[...])
sc.in_scope(url) -> bool   # anchored suffix match, chống subdomain confusion
```
> **LIMITATION (phải xử lý):** KHÔNG hỗ trợ IP/CIDR (trả False + warning). Raw scope IP phải dùng bộ check bổ sung bằng `ipaddress` (§8.4).

### 3.4 `tools/recon_adapter.py` — đọc output recon chuẩn hoá
```python
from tools.recon_adapter import load_recon
data = load_recon("target.com", recon_dir="recon")   # .subdomains .live_hosts .urls .nuclei .technologies ...
```

### 3.5 `tools/intel_engine.py` — intel/CVE/disclosed reports
```
python3 tools/intel_engine.py --target <d> --tech <csv> --program <h1handle> --memory-dir <dir> [--json]
```

### 3.6 Ranking — tái dùng `surface`/`recon-ranker` hoặc port công thức §12.3.
### 3.7 Tool đã cài (verify): `subfinder httpx dnsx nuclei katana gau amass ffuf` = yes. Docker = yes.
Takeover: `tools/takeover_scanner.sh`. Secrets: `tools/secrets_hunter.sh`.

---

## 4. KIẾN TRÚC TỔNG THỂ

```
                    ┌─────────────────────────────────────────────┐
                    │                 BROWSER (React)             │
                    │  Portfolio · Target view · Surface · Diff   │
                    │  Scan form (H1 handle/policy_scopes / raw)  │
                    └───────────────▲──────────────┬──────────────┘
                           WebSocket │ (scan log)   │ REST (CRUD/query)
                    ┌───────────────┴──────────────▼──────────────┐
                    │              FastAPI backend                │
                    │  /api/*  +  /ws/scan/{id}  (buffer+replay)  │
                    │  ┌────────────┐ ┌───────────┐ ┌──────────┐  │
                    │  │ JobRunner  │ │ DiffEngine│ │ BriefGen │  │
                    │  │ pgroup kill│ │           │ │          │  │
                    │  └─────┬──────┘ └─────┬─────┘ └────┬─────┘  │
                    │        │  Scheduler (APScheduler + jobstore)│
                    └────────┼──────────────┼────────────┼───────┘
                             │ subprocess    │ read DB     │ write files
              ┌──────────────▼───────┐  ┌────▼────┐  ┌─────▼────────────────┐
              │ claude-bug-bounty/   │  │ SQLite  │  │ targets/<slug>/      │
              │ (git submodule)      │  │ bbasm.db│  │  PROGRAM.md (bền)     │
              │  recon_engine(+patch)│  └─────────┘  │  AGENT_BRIEF.md      │
              │  scope_aggregator    │               │  recon/ findings/    │
              │  scope_checker/adapter│              │  CLAUDE.md .scope    │
              │  intel_engine        │               │  audit.jsonl         │
              └──────────────────────┘               └──────────────────────┘
```

**Luồng (two-phase — chi tiết §22.1):** nhập `h1:acme`/URL/policy_scopes/raw → `POST /api/scope/resolve` → scan_run(**draft**) + phân loại scope + config mặc định → **UI REVIEW CONFIG** (sửa depth/threads/rate_limit/toggle/bỏ host) → `POST /api/scans/{id}/launch` → queued → WS mở (replay buffer nếu reconnect) → JobRunner: recon theo category+config (giữ wildcard scope) → `load_recon`→DB(scan_run_id) → diff → rank → monitors → BriefGen ghi `PROGRAM.md`(lần đầu)+`AGENT_BRIEF.md`+scaffold. User: `cd targets/acme && claude`.

---

## 5. CẤU TRÚC THƯ MỤC SẢN PHẨM

```
bbasm/
├── BUILD_SPEC.md  README.md  docker-compose.yml  Dockerfile  .env.example
├── requirements.txt | pyproject.toml
├── .gitmodules                   # claude-bug-bounty submodule
├── vendor/claude-bug-bounty/     # git submodule (ENV BBASM_BBROOT trỏ vào)
├── backend/
│   ├── main.py  config.py  db.py  models.py  schema.sql  scope_gate.py
│   ├── jobs/ runner.py  scope_resolver.py  recon_orch.py  ingest.py
│   ├── asm/  diff_engine.py  ranking.py  monitors.py  scheduler.py
│   ├── brief/ generator.py  templates/
│   ├── api/  programs.py targets.py scans.py surface.py diff.py ws.py health.py
│   ├── log_buffer.py             # WS replay buffer (§8.5)
│   └── tests/
├── frontend/ (Vite+TS+React)  src/pages/… src/components/… src/api/…
├── entrypoint.sh                 # migrate DB + nuclei -update-templates (§13)
├── targets/   (gitignore — output)   data/bbasm.db (gitignore)
└── .github/workflows/ci.yml      # pytest (§15 K3)
```
> **Slug:** H1 handle hoặc domain apex; lowercase, chỉ `[a-z0-9.-]`, ký tự khác → `-`. Khoá target + tên folder.

---

## 6. DATA MODEL — SQLite (`backend/schema.sql`)

> SQLite WAL. `created_at`/`updated_at` ISO-8601 UTC. `schema_version` để migrate. Index cho query nóng.

```sql
CREATE TABLE schema_meta (version INTEGER);     -- [M9] migrate tối giản

CREATE TABLE program (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL, source TEXT NOT NULL,   -- "h1"|"raw"
  handle TEXT, platform TEXT DEFAULT 'h1',
  policy_json TEXT,                  -- [v2.2] raw policy + per-asset instruction (dựng PROGRAM.md)
  created_at TEXT, updated_at TEXT
);

CREATE TABLE scope_rule (
  id INTEGER PRIMARY KEY, program_id INTEGER REFERENCES program(id),
  pattern TEXT NOT NULL,            -- GIỮ wildcard: "*.acme.com" | "1.2.3.0/24" | "api.acme.com"
  kind TEXT NOT NULL,               -- "in"|"out"
  asset_type TEXT                   -- "domain"|"wildcard"|"ip"|"cidr"|"url"|"other"
);

CREATE TABLE scan_run (
  id INTEGER PRIMARY KEY, program_id INTEGER REFERENCES program(id),
  depth TEXT NOT NULL,              -- "passive"|"light"|"strong"
  status TEXT NOT NULL,             -- draft|queued|running|done|done_partial|failed|cancelled
  trigger TEXT DEFAULT 'manual',    -- "manual"|"scheduled" (scheduled bỏ qua review, §12.2)
  started_at TEXT, finished_at TEXT, error TEXT,
  stats_json TEXT
);

CREATE TABLE asset (
  id INTEGER PRIMARY KEY, program_id INTEGER REFERENCES program(id),
  host TEXT NOT NULL, ip TEXT, status_code INTEGER,
  title TEXT, tech_json TEXT,
  category TEXT,                     -- [v2.2] web|wildcard|ip|cidr|source_code|mobile|other (§22.3)
  first_seen_scan INTEGER, last_seen_scan INTEGER,
  state TEXT,                       -- "active"|"gone"
  rank_score REAL, rank_reasons_json TEXT,
  UNIQUE(program_id, host)
);
CREATE INDEX idx_asset_prog_rank ON asset(program_id, rank_score DESC);

CREATE TABLE url (
  id INTEGER PRIMARY KEY, program_id INTEGER, asset_id INTEGER,
  url TEXT NOT NULL, source TEXT,   -- katana|gau|wayback|js
  first_seen_scan INTEGER, last_seen_scan INTEGER,
  UNIQUE(program_id, url)
);

CREATE TABLE finding (
  id INTEGER PRIMARY KEY, program_id INTEGER, asset_id INTEGER,
  type TEXT,                        -- nuclei|takeover|secret|js-endpoint
  severity TEXT,                    -- [M3] enum: info|low|medium|high|critical
  name TEXT, detail_json TEXT,
  first_seen_scan INTEGER, last_seen_scan INTEGER,
  UNIQUE(program_id, type, name, asset_id)
);

CREATE TABLE diff_event (
  id INTEGER PRIMARY KEY, program_id INTEGER, scan_run_id INTEGER,
  entity TEXT, entity_ref TEXT, change TEXT,   -- new|changed|gone
  detail_json TEXT, created_at TEXT
);
CREATE INDEX idx_diff_prog_scan ON diff_event(program_id, scan_run_id);

CREATE TABLE schedule (             -- [H1] continuous monitoring persist
  id INTEGER PRIMARY KEY, program_id INTEGER UNIQUE REFERENCES program(id),
  interval TEXT NOT NULL,           -- "6h"|"daily"|"weekly"
  depth TEXT NOT NULL, enabled INTEGER DEFAULT 1,
  config_json TEXT,                 -- config dùng cho scan scheduled (bỏ qua review)
  next_run_at TEXT, created_at TEXT
);

CREATE TABLE scan_config (          -- [v2.2] config draft duyệt ở REVIEW trước launch (§22.1)
  id INTEGER PRIMARY KEY,
  scan_run_id INTEGER UNIQUE REFERENCES scan_run(id),
  depth TEXT, threads INTEGER, rate_limit INTEGER, scan_timeout INTEGER,
  nuclei_severity TEXT, skip_nmap INTEGER, skip_nuclei INTEGER, skip_active_crawl INTEGER,
  categories_enabled_json TEXT,     -- ["web","source_code"]
  excluded_hosts_json TEXT,         -- host user bỏ bớt ở review
  created_at TEXT
);
```
> [M3] **Severity enum chuẩn:** `info|low|medium|high|critical`. Mapping: takeover→high, secret (verified)→high / unverified→medium, js-endpoint→info.
> **Lưu ý:** §22.5 mô tả thêm ngữ cảnh các cột v2.2 ở trên — schema ở §6 này là **nguồn chuẩn duy nhất**, §22.5 chỉ giải thích.

---

## 7. BACKEND API (FastAPI)

> JSON; lỗi `{"error":{"code","message"}}`; Pydantic model; CORS theo config.

| Method & Path | Mục đích | Ghi chú |
|---|---|---|
| `POST /api/scope/resolve` | **Pha 1**: resolve+phân loại scope, tạo draft | body `{input, scope?[]}` → `{scan_id, config, assets_by_category}` (§22) |
| `POST /api/scans/{id}/launch` | **Pha 2→3**: chốt config đã duyệt & chạy | body `{config}` (§22.5) |
| `POST /api/scans` | *(giữ cho auto)* one-shot resolve+launch | body `{input, scope?[], depth, config?}`; depth lạ → **422** [M8]. **Luồng chuẩn dùng resolve→launch (§22.1)** |
| `GET /api/scans/{id}` | Trạng thái | status∈queued/running/done/done_partial/failed/cancelled |
| `POST /api/scans/{id}/cancel` | Huỷ | kill process group (§8.5) |
| `WS /ws/scan/{id}` | Log realtime | **replay buffer** khi reconnect (§8.5); events `phase`/`log`/`done` |
| `GET /api/programs` | Portfolio | sort #NEW desc |
| `GET /api/programs/{slug}` | Chi tiết | |
| `GET /api/programs/{slug}/assets` | Bảng asset | `?state=&min_rank=&q=` |
| `GET /api/programs/{slug}/surface` | Ranked | `?limit=25`; trả `reasons[]` |
| `GET /api/programs/{slug}/diff` | Diff | `?scan_id=` |
| `GET /api/programs/{slug}/findings` | findings | `?type=&severity=` |
| `POST/GET /api/programs/{slug}/brief` | Regen / lấy brief | GET trả `text/markdown` |
| `GET/PUT /api/programs/{slug}/program` | Đọc/sửa `PROGRAM.md` | GET `text/markdown`; PUT lưu phần user-editable (§22.4) |
| `GET/PUT /api/scans/{id}/config` | Lấy/sửa draft config | body config (§22.5); validate ở launch |
| `GET /api/programs/{slug}/export` | **Export ZIP folder** | `?include_recon=true` (default) → `application/zip`, stream (§10.1) |
| `POST /api/programs/{slug}/schedule` | Bật monitoring | `{interval,depth,enabled}` → ghi bảng `schedule` |
| `GET /api/health` | healthcheck | `{ok, tools:{subfinder:true,...}}` [M7] |

---

## 8. RECON ORCHESTRATION

### 8.1 Scope resolver (`jobs/scope_resolver.py`)
Phân loại `input`:
- **H1:** `h1:<handle>` | `https://hackerone.com/<program>` | `https://hackerone.com/<program>/policy_scopes` [H7].
  1. Parse `<handle>` (bỏ đuôi `/policy_scopes` nếu có).
  2. Gọi `scope_aggregator.sh <handle> --platform h1 --out <tmp>` (+ `--include-oos` để lấy luôn OOS).
  3. Đọc entry. **Giữ nguyên wildcard** [C2]: entry `*.x.com`→scope_rule(kind=in, asset_type=wildcard, pattern="*.x.com"). OOS→kind=out.
  4. (Optional) nếu input là URL policy_scopes & có token H1 → gọi API `policy_scopes` để lấy asset_type/eligibility; fail-soft nếu không.
  5. Rỗng → **HTTP 422** "scope empty".
- **Raw:** `input=="raw"`, `scope[]` = **list dòng text dán** (domain/IP/CIDR, và `repo:<github>`/`app:<store-id>` — xem §22.3) [H6]. KHÔNG nhận path file host; optional cho upload file → server đọc nội dung. Phân loại bằng `ipaddress` + regex → asset_type/category (§22.3).
- **Output:** ghi `targets/<slug>/.scope` (section `# IN` + `# OUT`, giữ wildcard) + build allowlist/denylist cho scope gate (§8.4). Program đã tồn tại → chỉ tạo `scan_run` mới [TC-SR-5].
- **Pha/draft:** resolver chạy ở **Pha 1** (§22.1), tạo `scan_run(status=draft)` + `scan_config` mặc định; recon chỉ chạy sau khi `launch`.

### 8.2 Depth → cấu hình recon (`jobs/recon_orch.py`) — **ĐÃ SỬA [C1]**

Vì `recon_engine.sh` không có passive-only và `NUC_SEV` không đọc ENV, chọn **HƯỚNG A (patch tối thiểu)**:

**A1. Patch `vendor/claude-bug-bounty/tools/recon_engine.sh`** (commit vào submodule, PR ngược nếu được) — thêm các toggle ENV, mặc định giữ hành vi cũ:
```bash
# gần Phase nmap:
if [ "${BBASM_SKIP_NMAP:-0}" = "1" ]; then log_warn "nmap skipped (BBASM)"; else <nmap cũ>; fi
# gần Phase httpx:
if [ "${BBASM_SKIP_HTTPX:-0}" = "1" ]; then log_warn "httpx skipped (BBASM)"; else <httpx cũ>; fi
# gần Phase katana/ffuf/param:
if [ "${BBASM_SKIP_ACTIVE_CRAWL:-0}" = "1" ]; then ... ; fi
# nuclei block: cho ENV override
NUC_SEV="${BBASM_NUC_SEV:-$NUC_SEV}"
if [ "${BBASM_SKIP_NUCLEI:-0}" = "1" ]; then log_warn "nuclei skipped (BBASM)"; else <nuclei cũ>; fi
```

**A2. Mapping depth chuẩn (sau patch):**

| Depth | recon_engine gọi | ENV set thêm | Chạm target? | Time |
|---|---|---|---|---|
| `passive` | `--quick` | `BBASM_SKIP_NMAP=1 BBASM_SKIP_HTTPX=1 BBASM_SKIP_ACTIVE_CRAWL=1 BBASM_SKIP_NUCLEI=1` | Không (chỉ subfinder/crt.sh/gau/wayback) | <2m |
| `light`*(default)* | `--quick` | `BBASM_SKIP_NMAP=1 BBASM_NUC_SEV=low,medium` | httpx+tech, nuclei nhẹ, no nmap/ffuf | 3–8m |
| `strong` | full (no `--quick`) | `BBASM_NUC_SEV=low,medium,high,critical` | full active + nmap + ffuf + param | 10–30m+ |

> Nếu không muốn sửa recon_engine (hướng B): `passive` tự gọi subfinder/gau lẻ; `light`/`strong` dùng recon_engine. Mặc định dùng **hướng A**. Agent **phải đọc recon_engine.sh xác nhận số dòng** trước khi chèn toggle.

- Luôn set `RECON_OUT_DIR=targets/<slug>/recon`, `BBHUNT_DASHBOARD=1`, `BB_THREADS`, `BB_RATE_LIMIT`.
- Scope nhiều host / H1 không wildcard → ghi list file tạm, truyền làm `<target>` (list mode), bỏ brute subdomain. Chỉ feed host **in-scope** (§8.4).

### 8.3 Ingest (`jobs/ingest.py`) — **idempotent [M1]**
`load_recon(slug, recon_dir=...)` → **upsert** asset/url/finding theo UNIQUE key, set `last_seen_scan=current`, asset mới set `first_seen_scan`. Parse `live/httpx_full.txt` (status/title/tech), `nuclei/` (findings). Gọi monitors (§12.4). Chạy lại cùng scan_run KHÔNG tạo bản ghi trùng.

### 8.4 SCOPE GATE (`scope_gate.py`) — BẮT BUỘC
`scope_gate.in_scope(target) -> bool` xử lý cả domain/URL (dùng `ScopeChecker`, **có wildcard**), IP/CIDR (dùng `ipaddress`: `ip in ip_network(cidr)`). Denylist (OOS) ưu tiên deny. Ghi mọi quyết định vào `targets/<slug>/audit.jsonl` `{ts,host,decision,rule}`.

### 8.5 JOB RUNNER (`jobs/runner.py`) — **MỚI [C4,H2,H3,H4]**
- **Queue + concurrency:** asyncio queue, tối đa `BBASM_MAX_CONCURRENT_SCANS`; scan vượt → `queued`, chạy khi có slot.
- **Spawn:** `subprocess` với `start_new_session=True` (⇒ `os.setsid`) để tạo **process group** riêng.
- **Cancel / timeout:** kill **cả group** bằng `os.killpg(os.getpgid(pid), SIGTERM)` → chờ grace → `SIGKILL`. Hard timeout theo depth (`BBASM_SCAN_TIMEOUT_*`, §14) → timeout thì mark `failed`/`done_partial` tuỳ đã có output chưa.
- **Partial [H3]:** recon_engine exit ≠ 0 nhưng có output → `done_partial` + vẫn ingest; không có output → `failed` + lưu `error`.
- **Log streaming + replay [H2]:** đọc stdout từng dòng, parse marker **tái dùng regex của `tools/dashboard.py` (tail mode)** → đẩy event `phase`/`log` lên WS **và** append vào `log_buffer.py` (ring buffer / file per scan). Client mở/mở-lại WS → **replay buffer** rồi stream tiếp.

**Test:** §16.

---

## 9. AGENT_BRIEF.md — GENERATOR (lõi tiết kiệm token)

> **Tiêu chuẩn:** brief là thứ DUY NHẤT agent cần đọc để bắt đầu. Self-contained, **≤ 12KB** [M5 chốt 1 con số]. Số liệu thật từ DB, không placeholder. Section như v1 (SCOPE, SỐ LIỆU, TOP SURFACE ≤25, ASSET MỚI, SIGNALS, HƯỚNG TEST, CÁCH LÀM VIỆC).

- Section SCOPE in cả **wildcard pattern** (không chỉ host).
- Section SIGNALS gọi monitors + `intel_engine.py --json` (timeout, fail-soft).
- **[M6] Depth=passive:** brief không có tech/live → ghi rõ dòng cảnh báo "Depth=passive: chưa probe live/tech. Chạy lại light/strong để có surface đầy đủ." và TOP SURFACE rank theo dữ liệu passive (tên host/pattern).
- Ghi `targets/<slug>/AGENT_BRIEF.md`, báo `{path, bytes}`.

---

## 10. SCAFFOLD PER-TARGET FOLDER (`brief/generator.py`)
Tạo (idempotent): `PROGRAM.md` (bền — §22.4, chỉ sinh lần đầu), `AGENT_BRIEF.md`, `CLAUDE.md`, `.scope`, `recon/`, `findings/ reports/ notes/`, `audit.jsonl`. Regenerate `AGENT_BRIEF.md`/`CLAUDE.md`/`.scope` mỗi scan; **KHÔNG ghi đè** `PROGRAM.md` (giữ phần user-editable), `findings/`, `notes/`.

### 10.1 EXPORT ZIP — đóng gói cấu trúc folder [tính năng theo yêu cầu user]

> Mục đích: scan xong, user tải 1 file `.zip` chứa **nguyên cấu trúc `targets/<slug>/`** như lúc dashboard scaffold — bung ra là có folder sẵn-sàng để `cd && claude` trên máy khác, hoặc đưa cho agent khác. Bổ sung cho Docker portability (tool) bằng portability của **output**.

**Endpoint:** `GET /api/programs/{slug}/export?include_recon=true` → `Content-Type: application/zip`, `Content-Disposition: attachment; filename="bbasm-<slug>-scan<scan_id>-<YYYYMMDD>.zip"`.

**Nội dung zip (root = `<slug>/` để giải nén ra đúng folder):**
```
<slug>/
  PROGRAM.md       AGENT_BRIEF.md   CLAUDE.md   .scope   audit.jsonl
  findings/  reports/  notes/
  recon/                      # chỉ khi include_recon=true (default)
  MANIFEST.json               # [mới] metadata để agent/máy khác hiểu ngay
```
`MANIFEST.json` chứa: `{slug, source, handle, scan_id, depth, generated_at, stats:{subs,live,urls,findings}, scope:{in:[...wildcard...], out:[...]}, files:["PROGRAM.md","AGENT_BRIEF.md",...], bbasm_version}`.

**Standard:**
- **Stream** zip (`zipfile.ZipFile` trên `StreamingResponse`/tạm file), KHÔNG nạp hết vào RAM — `recon/` có thể vài trăm MB.
- `include_recon=false` → bỏ `recon/` (zip gọn, chỉ brief + scope + findings), dùng khi chỉ cần bàn giao brief.
- Loại trừ file rác: `.DS_Store`, `*.tmp`, lock files. KHÔNG kèm secret của hệ thống (chỉ đóng gói nội dung trong `targets/<slug>/`).
- Giải nén ra PHẢI có cấu trúc **giống hệt** §10 (verify bằng test).
- Hoạt động cả khi scan là `done_partial` (đóng gói phần đang có).

**UI:** nút **"Export ZIP"** trên Target page (tab Overview/Brief), kèm checkbox "Include raw recon (lớn hơn)". Click → tải file.

**Test:** TC-EXP-* (§16).

---

## 11. FRONTEND (React + Vite + TS)
Như v1: Pages Portfolio / ScanNew / Target(tabs Overview·Surface·Assets·Diff·Findings·Brief) + nút Enable monitoring + copy path để `cd`. Components AssetTable/RankBadge/DiffBadge/ScanLog/TechChip/SeverityTag. **Bổ sung:** empty/loading/error states cho mọi page; ScanLog hỗ trợ **reconnect** (nhận replay từ WS). Nếu vẽ chart (severity dist / asset growth) → đọc skill `dataviz` trước. Dark+light, responsive phone width.

---

## 12. ASM FEATURES NÂNG CAO (cả 4)

### 12.1 Multi-program portfolio
`GET /api/programs` gom program + số liệu scan mới nhất + đếm NEW từ `diff_event`. Sort #NEW desc.

### 12.2 Continuous re-scan + diff — **persist [H1]**
- `asm/scheduler.py` = **APScheduler với SQLAlchemyJobStore** trỏ vào SQLite (hoặc đọc bảng `schedule` lúc boot và tự add job) ⇒ lịch sống qua restart. Entrypoint khởi động scheduler + nạp lại schedule enabled.
- **Scheduled scan BỎ QUA review:** tạo `scan_run(trigger=scheduled, status=queued)` thẳng, dùng `schedule.config_json` (+ depth) — không qua pha draft/REVIEW. Chỉ scan manual mới cần duyệt config.
- `asm/diff_engine.py`: so theo **set host** (không theo dòng file) ⇒ NEW (first_seen==current), GONE (active trước, vắng scan này → state=gone), CHANGED (tech/status đổi). Ghi `diff_event`.

### 12.3 Ranked attack surface — công thức (0–10)
```
+2.5 api_surface (api/graphql/v1/v2/rest) · +2.0 auth (login/sso/oauth/admin/account)
+1.5 fresh (first_seen==current) · +1.5 tech_risk (graphql/flask/express/wordpress/jenkins/gitlab/grafana/s3/firebase)
+2.0 nuclei med+ (low→+1) · +0.5 status 200 / +1.0 status 401|403
+1.0 host dev|staging|test|internal
clamp 0..10; lưu asset.rank_score + rank_reasons_json.
```

### 12.4 JS/secret + takeover monitor (`asm/monitors.py`)
`takeover_scanner.sh` → finding(takeover,high); `secrets_hunter.sh --js-bundle` → finding(secret); `recon/js/endpoints.txt` → finding(js-endpoint,info). Fail-soft nếu tool vắng; gắn `asset_id` nếu map được.

---

## 13. DOCKER / PORTABILITY

> Máy mới chỉ cần Docker.

**Vendor framework [C3]:** `claude-bug-bounty` đưa vào bằng **git submodule** tại `vendor/claude-bug-bounty`; Dockerfile `COPY vendor/claude-bug-bounty /opt/claude-bug-bounty`. (Clone submodule lúc checkout: `git submodule update --init`.) `ENV BBASM_BBROOT=/opt/claude-bug-bounty`.

**Dockerfile (multi-stage):**
```
FROM node:20-alpine AS fe
WORKDIR /fe ; COPY frontend/package*.json ./ ; RUN npm ci
COPY frontend/ . ; RUN npm run build        # -> /fe/dist

FROM debian:bookworm   # (hoặc kalilinux/kali-rolling)
RUN apt-get update && apt-get install -y python3 python3-pip golang git nmap ca-certificates
COPY vendor/claude-bug-bounty /opt/claude-bug-bounty
RUN bash /opt/claude-bug-bounty/install_tools.sh   # subfinder httpx dnsx nuclei katana gau amass ffuf
COPY backend/ /app/backend
COPY --from=fe /fe/dist /app/backend/static
COPY entrypoint.sh /entrypoint.sh
RUN pip install --break-system-packages -r /app/backend/requirements.txt
ENV BBASM_BBROOT=/opt/claude-bug-bounty BBASM_BIND=0.0.0.0
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]   # migrate DB + nuclei -update-templates + load schedules → uvicorn
```

**docker-compose.yml:**
```yaml
services:
  bbasm:
    build: .
    ports: ["127.0.0.1:8000:8000"]     # [H5] chỉ localhost; đổi khi cố ý expose
    volumes:
      - ./data:/app/data
      - ./targets:/app/targets
      - ~/.config/subfinder:/root/.config/subfinder:ro   # API keys (optional)
    env_file: .env
    cap_add: ["NET_RAW","NET_ADMIN"]   # [C5] nmap -sV/-sS ở strong depth
```
> Nếu không thể cấp cap → recon_orch dùng nmap connect-scan (`-sT`) cho strong trong container.

**Standard:** không hardcode `/home/kali`; ENV `BBASM_BBROOT/DATA/TARGETS/BIND`. `nuclei -update-templates` ở entrypoint. `/api/health` báo tool thiếu. API key fail-soft.

---

## 14. CONFIG (`.env` / `backend/config.py`)
```
BBASM_BBROOT=/opt/claude-bug-bounty
BBASM_TOOLS_SUBDIR=tools             # [§23] "tools" (bản pin cũ) | "bughunter/tools" (upstream mới)
BBASM_DATA=/app/data   BBASM_TARGETS=/app/targets
BBASM_BIND=127.0.0.1                 # [H5] default localhost
BB_THREADS=50   BB_RATE_LIMIT=150
BBASM_DEFAULT_DEPTH=light
BBASM_MAX_CONCURRENT_SCANS=2
BBASM_SCAN_TIMEOUT_PASSIVE=300       # [H4] giây
BBASM_SCAN_TIMEOUT_LIGHT=900
BBASM_SCAN_TIMEOUT_STRONG=2700
CORS_ORIGINS=http://localhost:5173,http://localhost:8000
CHAOS_KEY=  GITHUB_TOKEN=  H1_USER=  H1_TOKEN=
```
**Standard:** mọi giá trị có default an toàn; thiếu key → fail-soft.

---

## 15. BUILD PHASES — thứ tự thi công

- **P0 — Khung & vendor (0.5 ngày)**
  1. Cấu trúc §5 + `requirements.txt`. 2. **[K1]** add submodule `vendor/claude-bug-bounty` + `.gitmodules`; verify `$BBASM_BBROOT/tools/recon_engine.sh`. 3. `config.py` ENV. 4. `/api/health` list tool.
  - *Test:* TC-HLT-1.
- **P1 — DB + scope (1 ngày)**
  5. `schema.sql`+`db.py`(WAL, schema_meta, migrate). 6. `scope_resolver.py` (H1+policy_scopes+raw, giữ wildcard). 7. `scope_gate.py` (domain/wildcard/IP/CIDR).
  - *Test:* TC-SR-*, TC-SG-*.
- **P2 — Recon orch + runner + ingest (2 ngày)**
  8. **[K6]** patch `recon_engine.sh` toggles (§8.2 A1) trong submodule. 9. `recon_orch.py` depth mapping. 10. `runner.py` (queue, pgroup kill, timeout, partial, log buffer+replay). 11. `ingest.py` idempotent.
  - *Test:* TC-RO-*, TC-RUN-*, TC-IN-*.
- **P3 — ASM core (1.5 ngày)** 12. diff_engine 13. ranking 14. monitors 15. scheduler(persist).
  - *Test:* TC-DF-*, TC-RK-*, TC-MN-*, TC-SCH-*.
- **P4 — Brief + scaffold + export (1 ngày)** 16. generator+templates (sinh **`PROGRAM.md`** bền + `AGENT_BRIEF.md`) 17. API brief + `GET/PUT program` 17b. **export ZIP** (§10.1) + MANIFEST.json. — *Test:* TC-BR-*, TC-PRG-*, TC-EXP-*.
- **P5 — API đầy đủ + WS (1 ngày)** 18. mọi endpoint §7 + WS replay. — *Test:* TC-API-*.
- **P6 — Frontend (2 ngày)** 19. pages+components+states 20. build static serve. — *Test:* TC-FE-*.
- **P7 — Docker + portability (1 ngày)** 21. **[K2]** `entrypoint.sh` (migrate+update-templates+load schedules) 22. Dockerfile+compose(cap,bind) 23. README. — *Test:* TC-DK-*.
- **P7b — Hạ tầng phụ (0.5 ngày)** 24. **[K3]** CI `.github/workflows/ci.yml` chạy `pytest -q`. 25. **[K5]** logging (structlog/logging) + request log. 26. **[K4]** smoke-test target `example.com` (script `make smoke`).
- **P8 — Acceptance (0.5 ngày)** — chạy §17.

---

## 16. TEST CASES

> `pytest` backend, Vitest/Playwright frontend. CI chạy `pytest -q`. Coverage lõi (scope_gate, diff, ranking, brief, runner) ≥ 90%.

### Health / P0
- **TC-HLT-1**: `/api/health` trả `ok` + liệt kê đúng tool có/thiếu (giả lập PATH thiếu subfinder → `subfinder:false`).

### Scope resolver
- TC-SR-1 `h1:acme` mock aggregator 3 entry → program.source=h1, 3 scope_rule(in). · TC-SR-2 URL `/acme` & `/acme/policy_scopes` → handle=acme. · TC-SR-3 raw `["*.x.com","1.2.3.0/24","10.0.0.5"]` → asset_type wildcard/cidr/ip. · TC-SR-4 rỗng→422. · TC-SR-5 scan lại program cũ → không tạo program mới. · **TC-SR-6** entry `*.acme.com` → scope_rule pattern GIỮ wildcard (không resolve).

### Scope gate (an toàn)
- TC-SG-1 `sub.acme.com` vs `*.acme.com`→allow. · TC-SG-2 `evil-acme.com` vs `*.acme.com`→**deny**. · TC-SG-3 `acme.com` vs `acme.com`→allow; vs `*.acme.com`→theo quy ước (test & khớp doc). · TC-SG-4 `1.2.3.45` vs `1.2.3.0/24`→allow; `1.2.4.1`→deny. · TC-SG-5 OOS host→deny+audit. · TC-SG-6 URL có port/path→chuẩn hoá host. · **TC-SG-7** subdomain mới `new.acme.com` khớp wildcard in-scope→allow (chống C2). · **TC-SG-8** host vừa in (wildcard) vừa out (denylist cụ thể)→**deny** (OOS ưu tiên).

### Recon orchestration
- TC-RO-1 passive → có `--quick` + `BBASM_SKIP_{NMAP,HTTPX,ACTIVE_CRAWL,NUCLEI}=1`. · TC-RO-2 light → `--quick`+`BBASM_SKIP_NMAP=1`+`BBASM_NUC_SEV=low,medium`. · TC-RO-3 strong → KHÔNG `--quick`+`BBASM_NUC_SEV` có high,critical. · TC-RO-4 nhiều host→list mode (truyền file). · TC-RO-5 tool thiếu→warning, tiếp tục. · **TC-RO-6** patch recon_engine: set `BBASM_SKIP_NMAP=1` → output KHÔNG có `ports/nmap_results.txt`.

### Job runner **[mới]**
- **TC-RUN-1** 3 scan, max_concurrent=2 → cái thứ 3 `queued` tới khi có slot. · **TC-RUN-2** cancel scan đang chạy → `os.killpg` giết cả con (giả lập child sleep; assert child chết). · **TC-RUN-3** hard timeout → job bị kill, status `failed`/`done_partial` đúng. · **TC-RUN-4** subprocess exit≠0 có output → `done_partial` + ingest phần có; không output → `failed`. · **TC-RUN-5** WS reconnect giữa scan → nhận **replay** các dòng trước đó rồi stream tiếp.

### Ingest + diff
- TC-IN-1 fixture recon dir → đúng N asset/url/finding. · **TC-IN-2** chạy ingest 2 lần cùng scan → KHÔNG nhân đôi (idempotent). · TC-DF-1 scan2 thêm host→1 NEW. · TC-DF-2 mất host→1 GONE+state=gone. · TC-DF-3 tech đổi→CHANGED. · TC-DF-4 cùng tập host→0 diff (ổn định).

### Ranking
- TC-RK-1 `api.acme.com` graphql 200 NEW→score≥7 reasons⊇{api,graphql,fresh}. · TC-RK-2 `www` 200 no-tech→<3. · TC-RK-3 nuclei medium→+2. · TC-RK-4 score∈[0,10].

### Monitors / Scheduler
- TC-MN-1 takeover fixture→finding takeover high. · TC-MN-2 secret fixture→finding secret. · TC-MN-3 tool vắng→0 finding không crash. · **TC-SCH-1** bật schedule→ghi bảng `schedule`. · **TC-SCH-2** restart (reload scheduler từ DB)→job vẫn còn, `next_run_at` hợp lệ.

### Brief + scaffold
- TC-BR-1 seed 30 asset/5 nuclei/2 takeover→brief đủ section, **bytes<12000**. · TC-BR-2 top table≤25, số liệu khớp DB. · TC-BR-3 SCOPE in cả wildcard pattern. · TC-BR-4 scaffold 2 lần→`notes/` không bị xoá. · TC-BR-5 grep không còn `{{`/`TODO`. · **TC-BR-6** depth=passive→brief có dòng cảnh báo degraded.

### Export ZIP **[mới]**
- **TC-EXP-1** export → zip có `<slug>/AGENT_BRIEF.md`, `CLAUDE.md`, `.scope`, `MANIFEST.json` ở đúng cây. · **TC-EXP-2** `include_recon=false` → zip KHÔNG có `recon/`. · **TC-EXP-3** `MANIFEST.json` parse được, field khớp DB (scan_id, depth, stats, wildcard scope). · **TC-EXP-4** recon lớn (giả lập file ~200MB) → stream, memory ổn định (không OOM). · **TC-EXP-5** giải nén zip → cấu trúc **giống hệt** §10 (so cây thư mục). · **TC-EXP-6** scan `done_partial` → vẫn export được phần đang có.

### API
- TC-API-1 POST hợp lệ→200; thiếu depth→422. · **TC-API-1b** depth lạ ("deep")→**422** [M8]. · TC-API-2 GET scan running→running. · TC-API-3 surface?limit=10→≤10 sort rank desc. · TC-API-4 WS ≥1 `phase`+1 `done`. · TC-API-5 cancel→cancelled + process chết.

### Frontend
- TC-FE-1 Portfolio render N program, badge #NEW đúng. · TC-FE-2 ScanNew submit→POST+WS+phase tick. · TC-FE-3 Surface sort rank + cột lý do. · TC-FE-4 Diff tô màu NEW/GONE/CHANGED. · **TC-FE-5** ScanLog mất kết nối rồi reconnect→thấy lại log cũ (replay). · **TC-FE-6 (Playwright e2e)** new scan `example.com` passive→≤X giây thấy Brief.

### Docker / portability
- TC-DK-1 `docker build` exit 0 (submodule có mặt). · TC-DK-2 `curl /api/health`→ok, tool đủ. · TC-DK-3 scan passive `example.com`→`targets/example.com/AGENT_BRIEF.md` trên volume host. · TC-DK-4 grep source KHÔNG có `/home/kali` hardcode. · **TC-DK-5** strong depth trong container có cap→nmap chạy; không cap→tự fallback `-sT` không crash.

---

## 17. ACCEPTANCE CRITERIA (Definition of Done)

1. ✅ `docker compose up` → `http://127.0.0.1:8000` load.
2. ✅ `h1:<program>` + light → scan chạy, log realtime (reconnect replay OK), kết thúc không lỗi.
3. ✅ Raw scope (domain + CIDR) → scan chạy, scope gate chặn host ngoài list, **subdomain khớp wildcard được allow**.
4. ✅ Portfolio + Surface(ranked+lý do) + Diff(NEW sau scan 2).
5. ✅ `AGENT_BRIEF.md` ≤12KB, đủ section, số liệu thật, có wildcard scope. `cd && claude` đủ để hunt (agent không cần đọc lại recon để biết scope+surface).
5b. ✅ **Export ZIP**: tải được zip, giải nén ra folder `<slug>/` giống hệt §10; `include_recon=false` cho zip gọn; có `MANIFEST.json`.
6. ✅ Monitoring bật được & persist qua restart; re-scan tạo diff_event.
7. ✅ JS/secret + takeover ra finding khi có.
8. ✅ `pytest -q` pass; coverage lõi ≥90%; CI xanh.
9. ✅ Chạy trên máy chỉ có Docker (TC-DK-*), không sửa code.
10. ✅ Không scan/test ngoài scope (audit.jsonl chứng minh); cancel kill sạch process.

**Tiêu chí token:** đo & ghi vào README số token "khởi động hunt" flow cũ vs mới (agent chỉ đọc 1 brief).

---

## 18. GUARDRAILS
- Chỉ scan target trong scope người dùng cấp; scope gate chặn cứng (wildcard + IP/CIDR). Không "scan internet".
- Không tự khai thác / submit / spray trong dashboard này.
- Default bind `127.0.0.1` [H5]; expose ra ngoài phải cố ý + cảnh báo UI.
- `strong` depth cảnh báo UI "ồn ào, chỉ khi scope cho active scan".
- Tôn trọng `BB_RATE_LIMIT` + hard timeout + nút cancel. Audit mọi outbound.

## 19. NON-GOALS (phase 1)
Không spawn agent / full-auto · không BC/IT/YWH/IMF ở UI · không multi-user/auth (local 1 người) · không viết lại recon (chỉ orchestrate + patch tối thiểu).

## 20. BÀN GIAO
Trong `bbasm/`: `README.md` (build/run docker+dev, thêm target, cd chạy agent, **export ZIP**), kết quả `pytest`+coverage, demo GIF (optional), ghi chú lệch spec + lý do. Quyết định ngoài spec → **hỏi** `vinhtqk5@gmail.com`, không đoán.

---

## 21. GHI CHÚ KHI DÙNG AGENT KHÔNG-PHẢI-CLAUDE (vd Codex) ĐỂ BUILD

Repo này build được bằng agent bất kỳ (code là FastAPI/React/SQLite/Docker chuẩn), nhưng lưu ý:

1. **Submodule đã chốt (ĐÃ LÀM):** `vendor/claude-bug-bounty` → `https://github.com/gloryy2k/claude-bug-bounty.git`, **pin @32131c1** (bản layout `tools/` đang chạy thật trên máy Kali).
   ```
   git submodule update --init          # clone về khi mới checkout advance_asm
   ```
   ⚠️ KHÔNG đổi sang upstream `awarexone/Agentic-Bug-Hunter` — upstream đã restructure sang package `bughunter/`, KHÔNG còn `tools/recon_engine.sh` mà spec này tham chiếu. Giữ đúng bản pin.
   Vì §8.2 **patch `recon_engine.sh`**, agent commit patch vào submodule này rồi `git push` lên `gloryy2k/claude-bug-bounty`, sau đó bump con trỏ submodule trong `advance_asm`.
2. **Tách UNIT vs INTEGRATION test.** Sandbox Codex thường **không có** subfinder/nuclei/httpx/amass và **không có mạng** → chỉ chạy được unit test (scope_gate, diff, ranking, brief, runner-mock, export, API-mock). Các test cần tool/mạng thật — **integration/e2e** — đánh dấu `@pytest.mark.integration` và chỉ chạy trên Kali/Docker của bạn:
   - Integration: TC-RO-6 (patch recon_engine thật), TC-MN-* (tool thật), TC-DK-*, TC-FE-6 (e2e example.com), mọi test "scan thật".
   - Unit (chạy mọi nơi): phần còn lại.
   CI (K3) chạy `pytest -m "not integration"`; acceptance (§17) chạy full trên máy có tool.
3. **Không cần Claude skills để build.** `AGENT_BRIEF.md`/`CLAUDE.md` nhắc `/bug-bounty`,`/hunt`... là *output cho giai đoạn hunt* (chạy bằng Claude Code sau này), không phải phụ thuộc lúc build.
4. **Tool recon trong Docker:** agent dựa vào `install_tools.sh` của framework để cài Go tools lúc build image — cần mạng ở build stage.

---

## 22. LUỒNG CHI TIẾT & YÊU CẦU BỔ SUNG (v2.2)

> Mục này **chi tiết hoá & SUPERSEDE** phần scan-flow đơn giản ở §7/§8. Trả lời 4 yêu cầu: (1) xử lý input, (2) nơi lưu instruction, (3) scope cross-platform, (4) bước review config trước recon.

### 22.1 SCAN LIFECYCLE — 2 pha, có REVIEW CONFIG

Recon **KHÔNG** chạy ngay khi submit. Vòng đời `scan_run.status`:
```
draft ──(launch)──> queued ──> running ──> done | done_partial | failed | cancelled
                                   └─(cancel)─> cancelled
```
**Pha 1 — RESOLVE (nhanh, không chạm target):** `POST /api/scope/resolve {input, scope?[]}`
→ parse input (§22.2) → pull/parse scope → **phân loại asset_type** (§22.3) → tạo `program` (nếu mới) + `scan_run(status=draft)` + `scan_config` mặc định (từ ENV default) → trả `{scan_id, config, assets_by_category}`.

**Pha 2 — REVIEW CONFIG (UI):** user xem & sửa config draft:
- `depth` (passive/light/strong)
- `threads` (BB_THREADS), `rate_limit` (BB_RATE_LIMIT), `scan_timeout`
- `nuclei_severity`, các toggle `skip_nmap/skip_nuclei/skip_active_crawl`
- **bật/tắt từng nhóm asset** (web/api/source_code/mobile/ip) — nhóm tắt thì không recon
- danh sách scope đã phân loại: **bỏ bớt** host/entry không muốn test
- cảnh báo nếu depth=strong (ồn ào)

**Pha 3 — LAUNCH:** `POST /api/scans/{id}/launch {config}` → validate config (threads/rate_limit trong khoảng cho phép) → `status=queued` → JobRunner chạy (§8.5) theo config đã duyệt → ingest → diff → rank.

**Pha 4 — BRIEF:** sinh folder + `PROGRAM.md` (§22.4, lần đầu) + `AGENT_BRIEF.md`.

> **Standard:** config có giới hạn an toàn (vd threads ≤ 200, rate_limit ≤ 500) — validate ở launch, 422 nếu vượt. Draft chưa launch có thể xoá/ghi đè.

### 22.2 XỬ LÝ INPUT (từng bước)

**HackerOne** — nhận 3 dạng: `h1:<handle>` · `https://hackerone.com/<program>` · `https://hackerone.com/<program>/policy_scopes`:
1. Chuẩn hoá → `<handle>`.
2. `scope_aggregator.sh <handle> --platform h1 --include-oos --out <tmp>` → list entry (giữ wildcard).
3. (Nếu có `H1_TOKEN`) gọi API `/<handle>/policy_scopes` lấy thêm `asset_type`, `instruction`, `eligible_for_submission` mỗi asset → lưu để dựng `PROGRAM.md`. Fail-soft nếu không có token.
4. Lưu `program(source=h1, handle, policy_json)` + `scope_rule` (in/out, kèm asset_type).

**Raw scope** — `input=="raw"`, `scope[]` = list dòng text (hoặc upload file, server đọc nội dung). Mỗi dòng: domain / wildcard / IP / CIDR / `repo:<github-url>` / `app:<store-id>` → phân loại (§22.3). Không có policy → `PROGRAM.md` tạo khung tối thiểu cho user điền.

### 22.3 SCOPE CROSS-PLATFORM — phân loại & routing

Thêm cột **`asset.category`** và `scope_rule.asset_type`. Phân loại (ưu tiên dùng H1 asset_type nếu có, else suy luận):

| category | nguồn / nhận dạng | Routing khi recon |
|---|---|---|
| `web` | URL, domain | `recon_engine.sh` (subdomain enum nếu wildcard) |
| `wildcard` | `*.x.com` | `recon_engine.sh` enum |
| `cidr`/`ip` | CIDR/IP, H1 `CIDR` | `recon_engine.sh` list/CIDR mode |
| `source_code` | H1 `SOURCE_CODE`, `repo:<github>` | `secrets_hunter.sh --github-org/--git`, trufflehog, cicd scan → finding type=secret/cicd; asset type=repo. KHÔNG httpx/nuclei. |
| `mobile` | H1 `GOOGLE_PLAY_APP_ID`/`APPLE_STORE_APP_ID`, `app:<id>` | **Manual** — không auto-recon (cần APK/IPA). Ghi vào PROGRAM.md + brief, gắn skill `mobile-pentest`. |
| `other` | còn lại | liệt kê, đánh dấu manual. |

- `recon_orch.py` lặp theo category **đang bật**, gọi tool tương ứng, ingest vào cùng DB (asset.category để UI lọc/nhóm).
- Scope gate áp cho mọi category có outbound (web/ip/source_code→github host).

### 22.4 NƠI LƯU INSTRUCTION (agent đọc & dùng)

Trong `targets/<slug>/`:

| File | Vòng đời | Nội dung |
|---|---|---|
| **`PROGRAM.md`** | **Bền** — sinh lần scan đầu, **KHÔNG ghi đè** sau đó (có marker `<!-- user-editable -->` giữ phần user thêm) | Instruction cấp program: tóm tắt policy, scope theo category, asset mobile/source cần làm tay, rule đặc biệt, auth/credentials note, OOS, severity guideline của program. Nguồn: `policy_json` + phân loại scope. |
| **`AGENT_BRIEF.md`** | Tái sinh mỗi scan (≤12KB) | Trạng thái hunt: số liệu, top surface ranked, asset mới, signals (§9). |
| `CLAUDE.md` | Tái sinh | "Đọc `PROGRAM.md` rồi `AGENT_BRIEF.md` trước. Scope `.scope`..." |
| `.scope` | Tái sinh | allowlist (wildcard) + OOS. |
| DB `program.policy_json` | Bền | Bản gốc để dashboard hiển thị + export MANIFEST. |

Agent flow: `cd targets/<slug> && claude` → `CLAUDE.md` chỉ sang `PROGRAM.md` (hiểu luật chơi + category) → `AGENT_BRIEF.md` (hunt gì ngay). Cả `PROGRAM.md` + `AGENT_BRIEF.md` nằm trong ZIP export (§10.1) + liệt kê trong `MANIFEST.json`.

### 22.5 SCHEMA / API / UI / TEST / CHECKLIST DELTAS

**Schema:** các cột/bảng v2.2 (`program.policy_json`, `asset.category`, `scan_run.trigger`, bảng `scan_config`, `schedule.config_json`) **đã nằm trong §6** (nguồn chuẩn). Ở đây chỉ nhắc ý nghĩa: `scan_config` lưu config đã duyệt ở REVIEW; `categories_enabled_json`/`excluded_hosts_json` phản ánh lựa chọn user; `scan_run.trigger` phân biệt manual vs scheduled.

**API (bổ sung §7):** `POST /api/scope/resolve`, `POST /api/scans/{id}/launch`, `GET/PUT /api/scans/{id}/config` (lấy/sửa draft config).

**UI (bổ sung §11):** page **ReviewConfig** (`/scan/:id/review`) giữa ScanNew và log: form config + bảng assets_by_category có checkbox bật/tắt nhóm & bỏ host; nút "Launch scan". Target page thêm tab/panel hiển thị `PROGRAM.md` (render + nút Edit lưu lại phần user-editable).

**Test (bổ sung §16):**
- **TC-LC-1** resolve → `scan_run.status=draft`, chưa có process recon chạy. · **TC-LC-2** launch với threads>200 → 422. · **TC-LC-3** category `source_code` tắt → recon bỏ qua repo, không gọi secrets_hunter. · **TC-LC-4** sửa config draft rồi launch → recon dùng đúng threads/rate_limit đã sửa.
- **TC-CAT-1** H1 scope có `SOURCE_CODE` + `GOOGLE_PLAY_APP_ID` → phân loại category source_code/mobile đúng. · **TC-CAT-2** `source_code` route tới secrets_hunter (mock), KHÔNG tới recon_engine httpx. · **TC-CAT-3** `mobile` → không auto-recon, có mục trong PROGRAM.md + brief đánh dấu manual.
- **TC-PRG-1** scan đầu sinh `PROGRAM.md` với policy + category. · **TC-PRG-2** scan lần 2 **KHÔNG ghi đè** PROGRAM.md (phần user-editable giữ nguyên). · **TC-PRG-3** `PROGRAM.md` + `AGENT_BRIEF.md` có trong ZIP export + liệt kê trong MANIFEST.

**Checklist (bổ sung §15):** P1 thêm `scan_config` + phân loại asset_type/category; P2 thêm routing theo category trong recon_orch; P4 thêm sinh `PROGRAM.md` (bền); P5 thêm resolve/launch/config endpoints; P6 thêm page ReviewConfig + panel PROGRAM.md.

**Acceptance (bổ sung §17):**
- ✅ Submit input → ra **màn review config**, recon chưa chạy; sửa threads/rate_limit/bỏ host rồi Launch → recon chạy đúng thông số.
- ✅ Scope có source_code/mobile → phân loại & route đúng; mobile đánh dấu manual.
- ✅ `PROGRAM.md` sinh ra, không bị ghi đè ở scan sau, có trong ZIP; agent đọc PROGRAM.md + AGENT_BRIEF.md là đủ ngữ cảnh.

---

## 23. UPGRADE PATH — nâng framework sang layout `bughunter/` (bản upstream mới)

> **Mặc định v1 dùng bản pin cũ** (`gloryy2k/claude-bug-bounty @32131c1`, layout `tools/`) để build chắc, zero rework. Khi v1 đã chạy ổn và muốn bám bản upstream được maintain (`awarexone/Agentic-Bug-Hunter`, layout package `bughunter/`, update thường xuyên, ~5k sao), theo checklist này. **Chỉ làm sau khi v1 pass §17.**

**Khác biệt chính:** script cùng tên nhưng **đổi đường dẫn**: `tools/recon_engine.sh` → `bughunter/tools/recon_engine.sh` (tương tự scope_aggregator, scope_checker, recon_adapter, intel_engine). Có thêm `pyproject.toml`, `go.mod`, `.claude-plugin`.

**Checklist nâng cấp (mỗi bước có cổng test):**
1. **Fork & pin bản mới:** fork `awarexone/Agentic-Bug-Hunter` về `gloryy2k`, đổi submodule `vendor/claude-bug-bounty` trỏ sang fork đó, **pin 1 commit cụ thể** (không để trôi theo upstream).
2. **Abstraction hoá path:** đưa prefix tool vào 1 biến config `BBASM_TOOLS_SUBDIR` (cũ=`tools`, mới=`bughunter/tools`). `recon_orch.py`/`ingest.py`/`monitors.py` build path = `$BBASM_BBROOT/$BBASM_TOOLS_SUBDIR/<script>`. ⇒ đổi layout chỉ là đổi 1 ENV. (Nên làm NGAY ở v1 để sau nâng cấp rẻ.)
3. **RE-VERIFY `recon_engine.sh` mới:** đọc lại — kiểm `--quick` còn skip gì, `NUC_SEV`/`NUC_LIMIT` còn tính nội bộ không, nmap/httpx/katana/nuclei còn luôn chạy không. **Cập nhật §8.2 patch cho khớp** (toggle ENV có thể chèn chỗ khác). KHÔNG giả định giống bản cũ.
4. **RE-VERIFY các interface khác:** `scope_aggregator` (flags, output format), `scope_checker.ScopeChecker` (signature, IP support — có thể đã thêm?), `recon_adapter.load_recon` (tên field), `intel_engine` (args). Sửa §3 nếu lệch.
5. **Chạy lại test:** toàn bộ integration (`pytest -m integration`) trên Kali/Docker + acceptance §17 với bản mới. Đặc biệt TC-RO-* (depth mapping), TC-DK-* (Docker build với `install_tools.sh` mới), TC-MN-*.
6. **Docker:** `install_tools.sh` bản mới có thể khác (go.mod/pyproject) → build lại image, verify `/api/health` đủ tool.
7. **Rollback sẵn sàng:** nếu bản mới vỡ interface → trỏ submodule về commit pin cũ là xong (vì đã abstraction ở bước 2).

**Tiêu chí quyết định nâng hay không:** chỉ nâng khi bản mới mang lại giá trị rõ (tool/fix mới mình cần). Nếu v1 chạy tốt, **được phép ở lại bản pin cũ vô thời hạn** — pin = ổn định, không nợ kỹ thuật bắt buộc.
