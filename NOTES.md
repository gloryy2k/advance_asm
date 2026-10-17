# Implementation notes

## Current phase

### Windows/browser fixes and verification (2026-10-14)

- See P8_WINDOWS_BROWSER_RESULT.md: B1 WebSocket dependency + REST fallback,
  B2 accessible Depth/status selectors, and Windows submodule CRLF image fix.
- 197 backend unit tests, 11 frontend tests, production build, real uvicorn WS,
  Docker integration, and official localhost browser E2E passed.
- Windows Docker Desktop/WSL2 DB/schedule/target persistence verified.
- Live Nation resolved 25 public assets; no recon launch. Official policy
  prohibits automated/LLM discovery and public fallback lacks full policy.
  H1 light-scan acceptance remains open; see report for precise limitations.

### Docker persistence closure (report d011a0c)

- P8_DOCKER_PERSIST_RESULT.md confirms all three tasks at 262b254 on Kali:
  195 unit tests, Compose config/cached build/health/static, and persistent
  DB/portfolio/target files/schedule/next_run through restart. Scheduler logs
  confirm job reload; this does not itself demonstrate a scheduled tick executing.
- Read-only GitHub Actions API check confirms CI success at d011a0c and 262b254.
  Evidence: https://github.com/gloryy2k/advance_asm/actions/runs/38384155496
- No new code change or local test rerun for this documentation-only update.
  Linux Docker/persistence and remote CI are no longer pending. Main remaining
  environment acceptance: browser E2E, Windows/WSL2, authorized live H1 program.
  Preserve detailed checklist items lacking live evidence; do not equate static
  dashboard HTML, reload logs or tool availability with full browser/scan coverage.

### Docker rerun and dotenv fix (review source 336e271)

- Kali confirms Docker acceptance at 578c489: 1 passed in 960.66s with cold cache,
  including image build/run/health/static. This supersedes the build-timeout blocker.
  Precision: nine release binaries are downloaded; subjack still compiles in its
  own stage. The report's 'no Go compilation' is not literally true. 960.66s is
  total test time, not an isolated build duration.
- Fixed shared .env.example: all four filesystem paths are commented defaults,
  so copying it supports local dev without /opt or /app. Dockerfile keeps container
  defaults; Compose explicitly overrides BBROOT/DATA/TARGETS/STATIC to match mounts,
  even when a user's .env has custom host paths. Custom container layout requires
  a Compose override. Other user ENV values and credentials remain configurable.
- The 13 shell unit tests now explicitly disable dotenv loading. Added regression
  for copying the example from another cwd and for an existing container dotenv.
  Full unit suite: 195 passed, 7 deselected both normally and with a temporary
  legacy container dotenv configured as the settings default. User .env untouched.
- Compose config parse confirms /opt/claude-bug-bounty and /app/{data,targets,
  backend/static}. No new Docker build/real scan here. README includes a targeted
  migration for old .env files; do not overwrite saved secrets with a new template.
- P8 remains open for browser E2E, Windows/WSL2, H1 real program, remote CI and
  any remaining live acceptance checklist items. No merge performed.

### Docker build-perf fix (Kali report d77a2c3)

- P8_FIX_VERIFICATION.md confirms all four fixes on Kali at 101b0ef, including
  real nuclei cancellation and 4 process integration tests. HIGH-1 is unblocked;
  a separate real nuclei hard-timeout was not repeated (shared teardown path).
- P8_DOCKER_RESULT.md records a 3600s source-build timeout before runtime tests.
  Nine tools now use official release binaries at the SAME pinned versions:
  subfinder/httpx/nuclei/dnsx/katana/gau/ffuf/amass/trufflehog. No vendor changes.
- scripts/tool-releases.json locks Linux amd64 and arm64 URLs plus SHA-256.
  Digests came from official GitHub release asset metadata; gau/amass hashes came
  from their publisher checksum files (metadata lacks digest). URLs are versioned,
  never latest. Archive verification precedes reading a unique binary member;
  symlinks/duplicates/wrong ELF architecture fail. Downloads have timeout/retries;
  corrupt archives are not installed. Updating a version requires reviewing hashes.
- subjack stays compiled at b53899ce6230 in its own cached Docker stage. Available
  release v3.1.0 points at 8a3a82c, so using it would silently change the tool pin.
  Separate per-tool RUN layers retain completed downloads on retry. No cache-mount
  syntax is required, so this does not add a BuildKit/buildx plugin prerequisite.
- Publisher GoReleaser configs for trufflehog v3.99.2 and katana v1.8.0 explicitly
  use CGO_ENABLED=0. Actual image/tool runtime and build speed are still unverified.
  Docker test keeps its 3600s limit, records elapsed build time, checks all nine
  release tools in health, then static HTML. No test limit inflation to hide slowness.
- Unit gate: 193 passed, 7 integration deselected. Offline fixtures exercise both
  archive formats and architectures, checksum rejection, cache reuse/corruption,
  retries, ambiguous members and symlinks. No real tool execution or Docker build.
  Kali must rerun Docker acceptance; browser/H1/WSL2/remote CI remain pending.

### P8 handoff fixes (review source: 9fa4b8c)

- FIX-1: psutil 7.0.0 snapshots recursive descendants and, on POSIX, all members
  of the subprocess session. TERM, bounded child wait, a second session snapshot
  and KILL cover GNU timeout's separate process groups and reparented children.
  asyncio retains ownership of reaping the root. Teardown runs off the event loop;
  repeated cancel requests do not interrupt an already-cancelling task's cleanup.
  No vendor edit. Unit mocks cover detached descendants/orphans; integration now
  covers GNU timeout + TERM-resistant child for cancel, hard timeout and exited
  parent. These real-process tests are NOT run here; Kali must revalidate HIGH-1.
  This is teardown of framework jobs, not containment of malicious daemonization.
- FIX-2: persist a random output_claim in existing scan stats under BEGIN IMMEDIATE
  before filesystem work; only draft/queued scans can claim. Runner claims before
  marking running. Existing unclaimed output is preserved as .orphan-ID-UUID;
  same-DB repeated claims and executed scans fail closed. Legacy execution stats
  also prevent reuse. No schema migration, deletion or output layout change.
  If disk setup fails after claim, create a new scan rather than retry that ID.
  DB and filesystem are not transactional together; keep paired backups. Old
  orphan directories are deliberately retained and excluded from hidden-file ZIPs.
- FIX-3: negative live evidence requires non-passive depth, HTTPX enabled, the
  engine's subdomains/all.txt input and both live/httpx_full.txt and live/urls.txt
  outputs. Complete scan + no live URL/status yields status_code X -> null, also
  clearing the DB status. Partial, discovery-only, passive or missing files do not.
  Assumption for review: vendor masks httpx exit errors (`|| true`), so these
  artifacts prove a probe attempt, not every successful request. An empty result
  can indicate transport/tool failure as well as downtime; no claim of definitive
  host outage. No broad recon rewrite or new vendor instrumentation added.
- FIX-4: TC-RK-1 now matches the existing 6.0 formula; no ranking weight changes.
- Unit regression: 177 passed, 7 integration deselected. Pending real-tool cancel/
  timeout recheck and Docker/browser/H1/WSL2/remote CI remain in ACCEPTANCE.md.
- Kali review measured fixture input tokens 32004 -> 994 (96.89% reduction,
  brief 2638 bytes) at 4882a9d; this supersedes the earlier pending-token note.

P2 is validated by the user on Kali at 695ef2d / vendor 7acb66a: 124 unit +
3 integration tests passed, loopback light scan ~7s instead of ~279s, audit
complete, health fixed. katana/dnsx were installed in ~/go/bin all along.
P3–P7b implementation is complete with unit gates. P8 host acceptance is pending;
see ACCEPTANCE.md. Earlier pending-T6 and deny-before-spawn notes below are
historical and superseded by the confirmed P2 result and audited-spawn design.

## P3 — ASM core

- Implemented diff_engine, ranking, framework monitors and persistent scheduling.
  Runner captures a durable pre-ingest baseline, runs gated monitors inside the
  same timeout/process-group/audit boundary, ingests results, then diffs/ranks.
- Diffs are idempotent per scan and normalize tech sets; partial/error scans and
  excluded review scope cannot mark hosts gone. Returning hosts emit changed.
- Ranking follows §12.3 exactly. Spec conflict for review: TC-RK-1's api + graphql
  + fresh + 200 totals 6.0, not >=7. The test asserts 6.0 and reasons; no arbitrary
  score inflation was added. Each feature contributes once and score clamps at 10.
- Monitor inputs are isolated and scope-filtered; missing binaries/passive depth
  skip active monitor execution. Findings retain redacted metadata. Unattributable
  secrets/relative endpoints keep NULL asset_id, with explicit idempotent upserts.
- APScheduler 3.11.0 restores jobs from the existing schedule table at startup
  (the §12.2 alternative to SQLAlchemyJobStore). Enabled jobs preserve next_run_at;
  overdue executions coalesce, overlapping scans skip a tick. Scheduled scans are
  created queued with trigger=scheduled and saved config, never via draft review.
  Monitoring API/UI comes in P5/P6. Run a single backend process for this scheduler.
- Validation: **150 passed, 3 deselected**; one upstream Starlette/AnyIO warning.
  Measured line coverage: diff/ranking 100%, monitors 95%, scheduler 94%, runner
  90% (rounded), scope gate 95%; aggregate of these modules 94%. No real monitor
  scan/integration run in this Windows environment. Vendor stays at 7acb66a.
- APScheduler reference consulted: https://apscheduler.readthedocs.io/en/3.x/userguide.html
  Optional local coverage command (install coverage separately):
  `python -m coverage run --source=backend.asm,backend.jobs.runner,backend.scope_gate -m pytest -m "not integration"`.


## P4 — Brief/scaffold/export

- Brief/scaffold generation is wired after ingest/diff/rank. PROGRAM.md is created
  once; PUT accepts only user-section text, never overwrites generated policy/scope.
  Exact PUT body: {content: string}. Folders and user notes remain intact.
- Brief preserves all scope rules and section headings within <12000 UTF-8 bytes;
  optional surface/signals are capped. If mandatory scope alone exceeds the budget,
  generation fails explicitly instead of silently dropping rules (reviewable default).
- Intel reuses intel_engine.py --json through the same audited subprocess/cleanup
  path, with 15s timeout and 1MB output cap; failure is a warning. Manual brief regen
  uses that scan's cached intel and findings, does not repeat outbound requests.
- ZIP is built to a temporary disk file and served with cleanup; symlinks rejected,
  hidden internals/system dotfiles and temporary/lock files excluded. Manifest and
  regenerated brief use the same completed/partial scan. Includes empty directories.
- Gate passed: 157 unit tests, 3 integration deselected; 200MB export fixture used
  <20MB Python peak allocation. UTF-8 tests fixed for native Windows.
- Raw monitor output can contain credentials in recon files; include_recon=false
  is the compact handoff option. Dashboard finding metadata is redacted.

## P5 — API completion

- Added portfolio sorted by NEW count, program detail/scans/scope/schedule,
  assets/surface filtering and stable rank ordering, diff and finding filters,
  schedule control and explicit-depth one-shot scan API. Canonical UI flow remains
  resolve → review → launch. Existing WS replay/config/cancel endpoints are reused.
- List APIs use bounded limits and parameterized SQL. Missing program uses the
  existing structured 422 ScopeError contract. Schedule config is optional; without
  it the selected depth's defaults are captured when enabling monitoring.
- Unit gate: 159 passed, 3 integration deselected. No real target traffic.
- P4's first push encountered GitHub DNS resolution failure; local commit retained
  and push retried with P5. No implementation was lost.

## P6 — Dashboard

- React/TypeScript dashboard includes portfolio, raw/H1 input, config review with
  category and per-host exclusion controls, explicit launch, cancellation and WS
  replay reconnect. Target tabs expose overview, surface, assets, diff, findings,
  brief, PROGRAM editing and ZIP options. Dark/light and narrow-screen CSS included.
- FastAPI serves the built bundle when BBASM_STATIC exists; Vite proxies API/WS
  in dev. No third-party font request. Markdown renderer does not enable raw HTML.
- Gate: 160 backend unit tests; 6 Vitest tests; production build passes. npm audit
  reports 0 vulnerabilities after updating initial build/test pins. Node >=22.12 is
  required (newer than the spec's illustrative node:20 stage); CI/Docker use Node22.
- Localhost portfolio was visually checked. Full browser example.com e2e and
  phone-device acceptance remain integration/user checks, not claimed as run.

## P7 — Docker/runtime

- Added multistage frontend/Go tools/Python image, localhost-published Compose,
  volume persistence, startup migration, bounded audited template refresh and
  optional subfinder/capability overrides. Default nmap remains -sT without caps.
- Reviewed vendor install_tools.sh: it attempts Homebrew bootstrap, unsuitable
  for a root Debian build. A Linux container install adapter compiles the same
  tools at pinned Go-proxy versions; recon itself remains the untouched fork.
  Trufflehog builds inside its tagged source module to honor replace directives.
- Tool versions were resolved against proxy.golang.org, but **Docker compilation
  and real tool CLI compatibility are not validated here**. Docker daemon is not
  running; per task instructions no Docker build was attempted. This is a P8
  acceptance item for Kali/Docker, not a claim that the image has been built.
- Unit gate: 162 passed, 3 integration deselected. Shell syntax checks passed.

## P7b — CI/logging/smoke and P8 handoff

- Added structured HTTP request logs with generated request IDs; request bodies,
  query values and exception messages are omitted. Errors return structured 500.
- CI runs backend non-integration tests, frontend tests/build and shell LF checks.
- Added opt-in smoke, Docker integration and Playwright integration scripts.
  Real scan/build/browser integration has not been run here.
- Final unit gate: 163 passed, 5 integration deselected; one upstream warning.
  Core aggregate coverage is 93% (ASM, brief/export, runner, scope_gate).
- Compose parses with the example env; fixed empty ENV values whose inline
  comments were interpreted as values. No Docker daemon/build was used.
- Added a synthetic token comparison script. Tokenizer installation was not
  executed because automatic approval review failed with a usage-limit error.
  No token savings numbers are claimed. See ACCEPTANCE.md for host commands.

## Historical phase records

The records below describe the state at each earlier phase, not today's feature
availability. The P2 open/pending restrictions were superseded by its later plan
and the user-confirmed 695ef2d / 7acb66a validation above.

## P0 scope

- Read BUILD_SPEC.md v2.4, README.md and .env.example before implementation.
- Cloned recursively; framework remains pinned at 32131c1b4037d8488ac6a35274bc29fa2be67691.
- Added backend packages and frontend directory skeleton per §5. Functional modules
  for later phases, Docker files and frontend dependencies are deferred to those phases.
- Config loads process ENV over root .env, validates limits, and centralizes framework paths.
- GET /api/health reports PATH executables and framework files without subprocesses,
  network requests, scans, or filesystem writes. Missing tools do not stop the API.
- CI installs root requirements and runs `pytest -m "not integration"` on main,
  build branches and pull requests. Real-tool/network/Docker tests must use integration.

## Defaults for review (not specified in detail by the spec)

- Local path defaults use the repository's vendor/, data/, targets/ so Windows/Linux
  development works without /app or /opt. Explicit ENV and .env.example retain the
  container paths from §14. No runtime directories are created before they are needed.
- Health `ok` means API liveness; each tool boolean means availability only, not correct
  version or successful execution. Framework scripts are reported by filename as extra
  entries in tools. This is reversible when tool version checks are defined.
- Invalid ENV fails startup with a validation error instead of silently replacing unsafe
  values. Missing optional keys remain valid, and secrets are masked in settings repr.
- Dependencies currently cover P0 only; later phases add their required libraries.

## Historical P2 phase boundary (superseded)

P0/P1 and P2 implementation T1–T5 are complete. P2_COMPLETION_PLAN.md supersedes
the earlier egress-blocking decision preserved below. T6 real-tool integration and
an authorized light smoke scan await the user on Kali/Linux; T7 PR/merge is pending
that confirmation. No target traffic or real-tool integration tests have been run.

## P2 completion (T1–T5)

### T6 follow-up: F1/F2

- F1 vendor commit: 7acb66a, pushed to build/bbasm-depth-toggles; parent pointer
  updated in this follow-up. Fork and tools/ layout remain unchanged.

- Read P2_T6_RESULTS.md at parent b67cb84. The earlier Kali validation belongs to
  5efda86/9cb6954; its ~4m39s runtime is a baseline, not a measurement of this fix.
- F1: IP-only lists and CIDR commands receive BBASM_SKIP_HISTORICAL=1. The
  vendored helper also filters IPv4/IPv6/CIDR from mixed lists before any provider
  call. Domains retain historical collection unless the operator disables it.
- BBASM_HISTORICAL_TIMEOUT defaults to 60 seconds (validated 1..300). gau runs
  once under a real GNU timeout with a 5-second kill grace, preserving partial
  output; no unbounded retry. Without timeout/gtimeout, gau is skipped with a
  warning. Wayback uses curl --max-time against a shared phase deadline.
- F2: health, runner warnings and subprocess ENV share Settings.tool_search_path:
  HOME/go/bin, then /opt/homebrew/bin and /usr/local/bin on POSIX, then PATH.
  Health remains read-only and does not validate tool identity/version.
- Unit validation: 124 passed, 3 deselected; one upstream deprecation warning.
  Bash syntax and git diff --check passed. Tests cover IP/CIDR skipping, mixed
  lists, timeout flags/partial output, bounded fallback, and Go-bin discovery.
- No post-fix real scan or integration run here: Windows host has no recon tools;
  WSL lists only docker-desktop and Docker Linux daemon is unavailable. Repeat
  T6 on the original Kali host before claiming a measured runtime improvement.

### T1–T5 implementation record

- Default AuditedEgress records allow/audited_spawn before process creation, with
  scan ID and resource. BBASM_RECON_DISABLED=1 selects deny-before-spawn.
- ENV-only settings default to 1: BBASM_NO_INTERACTSH, BBASM_NO_REDIRECT,
  BBASM_SCOPE_CRAWL, BBASM_NO_VERIFY. No database migration is needed. Restart
  the backend after changing settings. Setting a toggle to 0 restores that behavior.
- Minimal vendor patch also touches secrets_hunter.sh as authorized by T2:
  committed and pushed as 9cb6954 on build/bbasm-depth-toggles in the same fork.
  --no-verification replaces --only-verified, retaining unverified candidates.
  Recon uses nuclei -no-interactsh, omits httpx redirect following, and supplies
  katana -field-scope fqdn and -disable-redirects by default.
- Historical list queries now use actual input hosts (gau and Wayback fallback),
  not the list basename. Inputs remain isolated at targets/<slug>/.inputs/<scan_id>/;
  outputs remain recon/scans/<scan_id>/<step>/. Some vendor helpers retain fixed
  concurrency; BB_THREADS/BB_RATE_LIMIT are not a global per-request limiter.
- Audit covers scope checks and command launches, not every internal tool request.
  Toggles reduce secondary traffic; they do not implement a network boundary.
  Optional hardening analysis remains in P2_EGRESS_REVIEW.md.
- Actual pinned scope-checker interface is ScopeChecker.is_in_scope(); spec §3.3
  uses in_scope(). The adapter already uses the real interface; spec left unchanged.
- Validation: pytest -m "not integration": **110 passed, 3 deselected**, one
  upstream Starlette/AnyIO deprecation warning. New shell unit tests execute only
  extracted helper functions with fake tools; they skip when Bash is unavailable.
  bash -n passed for both changed scripts. No recon, Docker build or integration run.
- User validation T6: run pytest -m integration on Kali/Linux, then a light scan
  against an explicitly permitted target; verify done, audit record and scan output.
  This is required before treating real runtime behavior as validated and preparing T7.

## P0 validation

- `.venv/Scripts/python.exe -m pytest -m "not integration"`: **16 passed**
  on Windows / Python 3.13.2; includes TC-HLT-1. One upstream Starlette/AnyIO
  deprecation warning. CI targets Python 3.11 on Ubuntu; its result is not yet verified.
- The first sandbox test attempt could not create pytest temporary directories;
  the approved run outside the sandbox passed. No integration tests were run.
- `git diff --check` passed; submodule working tree is clean and pin unchanged.

## P1 scope and validation

- SQLite schema matches §6, including policy_json, asset.category, draft scans,
  scan_config and schedule.config_json. Migration v1 is atomic/idempotent, enables
  WAL and foreign keys, and refuses unknown/unversioned databases without deleting data.
- Resolve stores a program, IN/OUT rules, draft scan, default config, policy and a
  per-scan scope snapshot. Repeated input reuses the program, creates another draft.
- Added `POST /api/scope/resolve` early so the P1 draft contract is reviewable.
  No launch or recon route exists. Health remains read-only; resolve initializes DB.
- ScopeChecker is dynamically loaded from the configured framework tools directory.
  The actual pinned method is `is_in_scope`, unlike `in_scope` in §3's example.
  Wildcards exclude apex; OOS wins. IPv4/IPv6 ranges use ipaddress, and any OOS
  overlap denies a whole submitted CIDR. GitHub repo rules restrict the resource path.
- Raw asset classification and H1 asset_type produce web/wildcard/ip/cidr/source_code/
  mobile/other; mobile/other are excluded from automatic default categories.
- `pytest -m "not integration"`: **78 passed, 1 deselected**, one upstream
  Starlette/AnyIO deprecation warning, Windows Python 3.13.2. Includes TC-SR-1..6,
  TC-SG-1..8, TC-LC-1 and TC-CAT-1 plus DB, malformed input and metadata safety cases.
- The real offline Bash adapter test is marked integration and was NOT run.
  Live HackerOne, real recon, Docker and Linux CI results are not claimed here.

## P1 spec discrepancies and reversible defaults for review

1. **Pinned aggregator loses scope boundaries.** Its bbscope branch strips `*.`,
   `--include-oos` merges IN/OUT without labels, and dump matching uses substrings.
   Feeding that flattened output into an allowlist would be unsafe. No vendor changes
   were made. The adapter retrieves structured metadata via audited, fixed-origin HTTP
   requests (redirects/proxies disabled), selects an exact handle, fills an isolated
   cache, then invokes the real aggregator via subprocess. Bash functions disable
   curl/bbscope for that invocation. Classified IN/OUT rules come from the metadata,
   never from the lossy host list. This adapter is tied to the reviewed pin; re-review
   transport commands on any future vendor upgrade. Shell exit 1 may mean no web assets;
   structured mobile/source/IP assets remain available with a warning.
2. **H1 API endpoint:** `/policy_scopes` is an accepted browser input. Optional rich
   metadata uses `/v1/hackers/programs/{handle}` and `/structured_scopes`, following
   [HackerOne's official API](https://api.hackerone.com/hacker-resources/). Program policy,
   per-asset instructions and eligibility are stored; pagination uses fixed URLs.
   Missing credentials/API failure falls back to the public dump. Missing/ambiguous
   eligibility metadata fails closed with 422, without creating a draft.
3. **Identity and slugs:** raw scopes use a normalized, deduplicated pattern/kind set
   as identity; changing that set creates another program. Single web/IP scopes use
   the normalized full hostname as slug (no speculative public-suffix/apex guessing).
   Multi/category-only scopes use `raw-<digest>`. Collisions get a deterministic suffix;
   Windows reserved filenames are prefixed. These choices need product review if a
   future UI allows naming or editing raw programs.
4. **Draft isolation:** the latest program rules/.scope represent the latest preview.
   Each scan also stores resolved_scope in stats_json so an older draft's launch can
   retain its own scope. P2 must consume that snapshot, not a mutable shared .scope.
   Resolve transactions serialize program/slug allocation; filesystem and SQLite are
   not a distributed transaction, so DB snapshots remain authoritative after I/O failure.
5. **Conservative scope:** URL rules use hostname as §8.4 specifies; GitHub source-code
   rules additionally require the organization/repository path boundary. Other source
   hosting requires a later explicit adapter. Raw `# IN`/`# OUT` sections are supported
   for exclusion input. CIDRs require canonical network addresses (host bits rejected).
6. **P1 limitations:** the gate is implemented and metadata requests use it. Enforcing
   and auditing every outbound request from recon tools belongs to P2 and is not yet
   implemented. No assertion of full recon scope containment is made at this phase.

## P2 implementation and validation

- Vendor toggle commit `d8bd79524bcf16074da929311edc5bbdbe1f98b6` was pushed to
  `gloryy2k/claude-bug-bounty`, branch `build/bbasm-depth-toggles`, before updating
  the parent submodule pointer. It remains on the original tools/ layout/fork.
- Read the real recon_engine.sh, scope checker, dashboard tail parser, recon adapter
  and secrets_hunter interfaces before modifying/integrating them.
- Small vendor patch: depth toggles also cover CIDR ping sweep, DNS wildcard/takeover,
  JS fetching, config checks and CI/CD. Added optional FFUF/CI-CD toggles because light
  must not fuzz and an inferred GitHub organization is not granted source scope.
  Nuclei ENV override works. Managed nmap list mode uses `-iL`; optional `-sT` is used
  conservatively for all BBASM strong scans (works without raw sockets).
- Command planning uses approved config + immutable scan scope snapshot. Wildcards
  enumerate passively first; discoveries are filtered before building active list mode.
  Disabled categories/excluded hosts are not fed to tools. Source routes to secrets_hunter,
  mobile/other are manual. Passive source execution stays manual because the pinned
  secret scanner verifies live keys. Missing tools/scripts produce warnings.
- Queue caps concurrency and serializes scans per program. Config is persisted before
  queued; only draft may launch. Timeout is bounded by both reviewed config and ENV.
  Cancel/timeout clean the process group; partial output is ingested on nonzero exit
  and timeout. Interrupted jobs become failed on restart, never silently relaunched.
- Logs reuse dashboard.py's actual regex/map, have increasing event IDs, bounded replay
  and disk persistence. WebSocket reconnect supports an `after` cursor.
- Ingest reuses `load_recon` for canonical output and `ReconAdapter` for engine layout;
  scoped assets/URLs/nuclei/source-secret findings upsert by the spec keys. DB does not
  duplicate raw credential values. Snapshot observations are saved for P3 diff work.
- Output is isolated below `recon/scans/<scan_id>/<step>` rather than reusing the same
  recon folder. This is a documented layout refinement to avoid stale partial results;
  export/brief must consume the current scan manifest/stats rather than guessing files.
- Added minimal scan/config/cancel/WS endpoints now to make P2 behavior reviewable;
  remaining API/portfolio work stays in P5. Monitors and post-ingest ASM run in P3.
- Unit command: `.venv/Scripts/python.exe -m pytest -m "not integration"`:
  **100 passed, 3 deselected**, one upstream Starlette/AnyIO warning (Windows Python 3.13).
  Covers TC-RO-1..5, TC-RUN-1..5 (mock process-group signals), TC-IN-1..2,
  LC config limits/routing, replay, API state transitions and default egress denial.
- `bash -n vendor/claude-bug-bounty/tools/recon_engine.sh`: passed; no script execution.
  TC-RO-6/real process-tree teardown are integration-marked and were NOT run.
- **P2 open item:** every tool's network requests cannot be contained/audited by the
  toggle patch and seed filtering alone. The default boundary refuses all live recon
  before spawn. See P2_EGRESS_REVIEW.md for the concrete proposal requiring review.
  P2 is not presented as ready for real scans or as satisfying all acceptance criteria.
- Remaining framework behavior for review: list mode historical collection still uses
  the list basename; some helper phases have their own fixed concurrency. Before enabling
  live execution, reconcile those with reviewed target/limit semantics in the boundary
  or a separately authorized minimal adapter patch. No default upstream behavior was
  silently rewritten in this toggle patch.

---

## v1.1 "Guided UX" (spec v2.5) — triển khai trong cloud sandbox

Nhánh `claude/upbeat-thompson-b7bb23` (chồng lên `build/p8-acceptance` @ f9de2d5). Không đổi §1/non-goals.
Nguồn lỗi: `CLOUD_REVIEW_RESULTS.md` F1–F10.

| Finding | Sửa ở đâu | Bằng chứng |
|---|---|---|
| F1 policy H1 mất | `h1_scope.py` (`policy_text/source/fetched_at`), `BriefGenerator.program_text` | TC-PRG-4 dùng đúng shape provider; E2E mock H1 thấy policy trong tab Program |
| F2 `#OUT` lật OUT→IN | `jobs/scope_parse.py` | TC-SR-7 (7 cách viết header) + header sai → lỗi; E2E `# OUTT` chặn Resolve |
| F3/F4 parser, URL H1 | `scope_parse.py`, `h1_handle` | TC-SR-8/9/10 + preview endpoint |
| F5 CIDR 254 asset | `Ingester._collapse_ranges`, `ranking`, brief | TC-UX-5, `test_ux_cidr_is_one_range_asset_not_254_hosts` |
| F6 draft/scope_rule | `ScopeResolver`, `JobRunner._apply_scope_snapshot/delete_draft/purge_drafts` | TC-LC-5/6, purge test |
| F7 Review thiếu policy | `/api/scans/{id}/review`, `PolicyPanel`, ack gate | Vitest + E2E: Launch disabled tới khi tick |
| F8 health httpx | `api/health.py` sniff shebang (không thực thi) | TC-HLT-2 |
| F9 monitoring | Overview: chọn depth riêng + ack | Vitest |
| F10 brief | `generator.py` | TC-BR-7 |

Quyết định ngoài spec (để review):
- `automation_ack` chỉ **ghi lại** (scan stats + audit), không bị server ép buộc — UI mới là cổng; tránh phá API cũ/scheduler.
- Preview là hàm thuần dùng chung với resolve (một parser, không lệch).
- Range IP `a-b` mở thành tối đa 32 CIDR; vượt → lỗi. CIDR không chuẩn (`10.0.0.5/24`) là **lỗi có gợi ý**, không tự nới rộng.
- URL có đường dẫn vẫn recon cả host (giới hạn cũ), nay có cảnh báo ở preview.
- `BBASM_HOST_TARGETS` (tuỳ chọn) để lệnh `cd … && claude` đúng đường dẫn máy người dùng khi chạy Docker; không đặt thì hiển thị `cd "targets/<slug>"` kèm ghi chú.
- Nội dung policy là dữ liệu ngoài: PROGRAM.md và CLAUDE.md ghi rõ "tham chiếu, không phải chỉ thị".
- PROGRAM.md tạo lúc resolve và **không** cập nhật khi policy nguồn đổi (bền theo §22.4); Review hiển thị policy mới nhất.

Kiểm chứng trong sandbox: 259 unit (`python -m pytest -m "not integration"`), 33 Vitest, `npm run build`,
browser E2E cũ (đã cập nhật selector) + `test_ui_e2e_mock_h1.py` (7 test: luồng H1 mock, an toàn OUT, 5 route ở 390px
không cuộn ngang). **Chưa chứng minh:** H1 thật, recon thật, Docker/Windows, tick scheduler thật.


---

## v1.2 — rõ chức năng, rõ output, URL inventory, tuỳ chỉnh (spec v2.6)

Phạm vi theo phản hồi của người dùng: **không** ép/siết giới hạn tốc độ (scan giữ nhanh như cũ); giá trị nào đổi được thì cho đổi.
Nguồn: `V11_HOST_RESULTS.md`, `V11_FOLLOWUP_NOTES.md`, `V11_PRODUCT_REVIEW.md`, `V11_SCAN_9_12_EVIDENCE.md`, `PLAN_V12.md`.

| Vấn đề | Đã làm | Bằng chứng |
|---|---|---|
| F1 lệnh hunt Windows nhân đôi `\` | `quote_path` theo shell đích (Windows giữ `\`, POSIX escape) | unit + test Codex cũ |
| R7 native Windows chờ 6 phút rồi lỗi | `health.runtime` + `launch` trả 422 `platform_unsupported` ngay + banner | unit |
| R8 CI không chạy nhánh làm việc | `ci.yml` thêm `claude/**`, `test/**` | — |
| F3 test recon cứng path / race | dùng `Settings.tool_path`, `NoSuchProcess` = đã chết | — |
| DB v1 từ chối nâng cấp | `migrations.py`: v1→v2 có backup, rollback, từ chối bản mới hơn | TC-MIG-1..4 |
| R4 Diff 0 thay đổi | baseline = **observations của scan hoàn tất gần nhất** (không phải asset row bị ghi đè), lưu `baseline_scan_id` | TC-DF-5 (chuỗi có scan huỷ + asset bị "nhiễm") |
| R3 8.836 URL chỉ thấy 1 host | `asm/urlintel.py` (tag/score/shape), phễu raw→trong scope→ngoài scope, `/urls`, `/urls/summary`, `/urls/export` | TC-URL-1..3 |
| URL lịch sử bị hiểu nhầm là live | `verification`: `historical` (gau/wayback) · `observed` (katana). Không bao giờ `live` | test riêng |
| R2 H1 không token | `trust.py`: nhãn "CHƯA XÁC MINH" ở Review/Program/PROGRAM.md/brief + checklist đối chiếu | TC-H1V |
| R5 ZIP chứa dữ liệu ngoài scope | export `brief` / `filtered` (mặc định) / `full` có nhãn trong MANIFEST | TC-EXP-7.. |
| R6 brief cắt giữa JSON | `tech_chips` ("nginx, PHP, +4"), mục ENDPOINT ĐÁNG XEM (một URL mỗi dạng đường dẫn) | TC-BR-8 |
| "Mỗi chức năng output ở đâu" | `asm/phases.py`: 12 bước, trạng thái từ **bằng chứng** (ran/empty/skipped/missing_tool/no_output), file viewer an toàn (path trong thư mục scan, không symlink, secret bị ẩn) | TC-PH-1..3 |
| Tuỳ chỉnh | `ScanConfig` thêm: skip_ffuf/historical/takeover/secrets, max_js_files, url_exclude_patterns, brief_*; profile (CRUD, nhân bản, mặc định theo program); `/api/meta/plan` cho biết bước nào sẽ chạy | TC-CFG/PR |

Quyết định ngoài spec: (1) **không** có shim rate-limit và không có "quy tắc program" cứng — người dùng muốn scan nhanh; UI chỉ ghi rõ rằng một số công cụ có giới hạn riêng. (2) `url_exclude_patterns` chỉ lọc kết quả/brief, **không** ngăn công cụ truy cập đường dẫn đó (nói rõ trong UI). (3) Profile chỉ chứa cách quét, không chứa scope. (4) Giá trị bí mật trong file kết quả bị ẩn khi xem (`reveal=true` mới hiện). (5) Export mặc định là "đã lọc scope".
Giới hạn đã biết: nguyên nhân gốc thật của "Diff = 0" trên DB của Codex chưa tái hiện được từ dữ liệu xuất (chuỗi sạch cho kết quả đúng) — đã đổi sang baseline bất biến + lưu `baseline_scan_id` để lần sau chẩn đoán được; cần chạy lại Passive→Light trên máy thật để xác nhận.

## v1.2.1 — sửa theo QA host (V12_HOST_RESULTS.md)

| Finding | Cách sửa | Test |
|---|---|---|
| F1 secret lộ trong trình xem file | `scrub()` che credential ở **mọi** file (AKIA/ghp_/xox/JWT/private key + `token=…`, `password:…`, `Authorization: Bearer …`); dòng URL giữ nguyên query vì là dữ liệu recon; tìm kiếm chạy trên nội dung đã che; tải về mặc định đã che, `reveal=true` mới ra bản gốc | `test_f1_*` |
| F2 DB v1 không tự migrate khi khởi động | `lifespan` gọi `Database.migrate()` (có backup) nếu file DB đã tồn tại; cài mới vẫn tạo DB lười (health vẫn fail-soft) | `test_f2_*` |
| F3 URL cũ không được phân loại | migration v2 chạy thêm `_backfill_urls`: tag/score/shape cho mọi URL cũ, `verification='historical'` (không bao giờ "observed"); idempotent, cùng transaction nên lỗi thì rollback | `test_f3_*`, `test_tc_mig_1` |
| F4 OUT không thắng IN trong preview | `apply_precedence`: dòng IN bị OUT phủ hoàn toàn bị đánh dấu `shadowed_by`, `summary.effective_in`; nếu không còn IN hiệu lực thì preview `ok=false` và resolve báo `scope_empty_after_out` (ScopeGate lúc chạy vẫn deny trước, nên an toàn từ trước) | `test_f4_*` |
| F5 test trên Windows | `BBASM_HOST_TARGETS` là `str` nguyên văn (không qua `Path` nên đường dẫn WSL/POSIX không bị đổi `/`→`\`); E2E "launch tới done" bỏ qua trên Windows gốc. **Bộ unit chạy ở Linux/WSL2/CI**; 6 test enqueue recon trên Windows gốc vẫn bị từ chối `platform_unsupported` theo thiết kế | — |
| F6 API nhận Light không ack | `require_ack`: `/launch` và `POST /api/scans` trả 422 `ack_required` nếu depth ≠ passive mà thiếu `automation_ack`. **Lịch (scheduler) chưa có ack riêng** — ghi nhận là việc còn lại | `test_f6_*` |
| F7 PUT profile đổi depth ngầm | PUT gộp vào config đã lưu; depth chỉ đổi khi gửi rõ | `test_f7_*` |
| F8 a11y | link trong văn bản có gạch chân; mọi `.table-wrap`/`pre` cuộn được có `tabindex=0` + `role=region`; axe (wcag2a/aa) 10 route × 390/1366px: 0 lỗi serious/critical | axe chạy ngoài repo |

Chưa làm: Review trên mobile vẫn dài (~4.9k px); ack cho schedule; xác nhận trên host với dữ liệu thật (F2/F3 cần chạy lại T3).

### v1.2.2 (sau QA v1.2.1)
- N1 race ack: `automation_ack` được ghi **trong cùng transaction** với chuyển sang `queued` (`submit(..., ack=True)`), nên worker nhanh không thể ghi đè hoặc chạy trước; audit `automation_ack_by_user` ghi ngay sau commit. Đã bỏ `record_ack` rời.
- `test_recon_integration.py` nhớ `BBASM_BBROOT`/`BBASM_TOOLS_SUBDIR` lúc import (conftest xoá env mỗi test nên `Settings()` rơi về `/app/vendor`); chạy nguyên trạng trong image.
- Sáu test cần recon được `skipif(os.name != "posix")`; trên Windows gốc: 301 passed, 6 skipped. Mobile không còn là tiêu chí nghiệm thu (người dùng chỉ dùng desktop).

## v1.2.3 — N2: nguồn H1 công khai và cổng Light/Strong

**Thứ tự nguồn** (`backend/jobs/h1_scope.py`): `api` (có `H1_USER/H1_TOKEN`) → `public_page` (đọc chỉ-đọc policy + structured scope của đúng handle, không credential) → `public_dump` (bounty-targets-data). Mỗi lần Resolve lưu `policy.attempts` (nguồn nào đã thử, lý do ngắn không chứa token/body từ xa), `fetched_at`, `classification` (số asset phân loại / không phân loại).

**An toàn truy cập:** chỉ ba host (`api.hackerone.com`, `hackerone.com`, `raw.githubusercontent.com`) qua ScopeGate + audit; `follow_redirects=False` (3xx = lỗi, không bao giờ theo sang host khác); timeout 20s; trang giới hạn 5 MB và ≤20 request phân trang theo `endCursor` (không theo link do server đưa); trang chỉ chấp nhận khi `team.handle` khớp đúng handle và mọi asset có `eligible_for_submission` kiểu bool — sai cấu trúc thì coi như lỗi và rơi xuống dump (có gắn cờ thiếu dữ liệu). Token chỉ gửi tới `api.hackerone.com`.

**Phân loại asset** (`_entries`): chỉ asset gọi tên rõ (domain/wildcard có domain cụ thể/IP/CIDR/repo/app) vào scope gate. "Open Scope", loại `OTHER`, `*`, `*.com`, văn bản tự do **không** bị suy diễn thành quyền quét; chúng được liệt kê trong "chưa phân loại" (và là cảnh báo trên Review). Ineligible vẫn thắng nhãn pool IN của dump.

**Cổng Light/Strong** (`backend/trust.py: launch_gate`, lưu theo từng draft trong `stats.launch_gate`): chỉ cho khi (1) nguồn là `api` hoặc `public_page`, (2) có policy (từ program hoặc do bạn dán ở bước nhập), (3) không có mục OUT chưa phân loại, (4) có ít nhất một IN phân loại rõ. Dump-only → chỉ Passive, kể cả khi dán policy. Cưỡng chế ở server: `/launch`, `POST /api/scans`, `/programs/{slug}/schedule` → 422 `scope_incomplete`. Review hiển thị nguồn + thời điểm + chuỗi đã thử + phần còn thiếu, khoá Light/Strong và tự chuyển về Passive nếu bản nháp đang ở mức bị khoá. Program nhập tay (raw) không bị cổng này (đã có ack).

**Test:** `backend/tests/test_h1_sources.py` (21 ca, mock cả ba nguồn: thứ tự, fallback khi trang đổi cấu trúc/redirect/quá lớn/sai handle, phân trang, Open Scope, thiếu policy, dump + policy dán tay, API end-to-end, token không lộ), 2 ca Vitest. Ảnh Review desktop trước/sau: `review_evidence/n2_review/` (`before_dump` = hành vi cũ cho Strong trên dump; `after_dump`, `after_page`, `after_api`); harness `review_tools/mock_h1_modes.py` + `n2_screenshots.py`.

**Giới hạn chưa xác minh:** truy vấn GraphQL công khai (`PAGE_QUERY`) được viết theo schema công khai và **chỉ kiểm bằng mock** — cloud không truy cập được hackerone.com. Nếu tên trường sai, provider báo "Public page structure unexpected" và rơi về dump (an toàn, chỉ Passive). Cần Codex/bạn kiểm một handle công khai trên máy có mạng và chỉnh `PAGE_QUERY` nếu cần; chỉ đọc metadata, không scan.

### v1.2.4 — sau kiểm tra trực tiếp (N2_LIVE_CHECK.md)
- **Kết quả thật:** `PAGE_QUERY` hoạt động ẩn danh với 2 handle công khai (policy Markdown, structured scope, không cần cookie/CSRF; `User-Agent` kiểu trình duyệt đủ). Verisk: 2 IN, policy 3.109 ký tự, mở khoá Light/Strong. GitLab: 44 node = 19 IN + 25 OUT khớp số lượng của trang (Burp do người dùng cung cấp), nhưng 12 asset (9 IN, 3 OUT) chưa phân loại → 3 OUT chưa phân loại chặn Light/Strong.
- **Đối chiếu số lượng:** truy vấn thêm `assets_in/assets_out: structured_scopes_search(eligible_for_submission:…){total_count}` (đúng các trường trang tự dùng). Đọc ít hơn tổng → `completeness` ghi rõ, gate chặn Light/Strong ("asset chưa đọc đủ"). Nếu trang từ chối các trường này (GraphQL `errors`), thử lại đúng 1 lần với truy vấn thường và không khẳng định gì về số lượng.
- **P2 từ Codex:** Review ghi rõ "mở khoá = đủ dữ liệu để cấu hình, không phải policy đã cho phép quét"; việc cho phép do người dùng đọc policy và tick xác nhận.
- **Chưa giải quyết:** 12 asset GitLab chưa phân loại (cần danh sách `identifier/asset_type` để biết dạng nào parser bỏ sót, ví dụ URL có path, wildcard có path, `host:port`). OUT dạng path không thể thi hành ở mức host nên cần quyết định riêng. Độ dài policy GitLab (26.067) so với ước lượng Burp (~17–18k) chưa đo cùng thời điểm.

### v1.2.5 — theo danh sách asset thật (N2_UNCLASSIFIED.md: GitLab, Shopify, Uber)
- **Kho mã:** `repo:` nhận `github.com`, `gitlab.com`, `bitbucket.org` (GitLab có nhóm con tới 6 cấp); `…/org/*` nghĩa là chính tổ chức đó, không rộng hơn; so khớp theo đúng host. Repo ngoài GitHub chỉ được **ghi nhận để làm tay**, recon không tự clone (`--github-org` chỉ đúng cho GitHub).
- **OTHER nhưng là host rõ ràng:** `*.uberinternal.com`, `supplier-portal.shopifycloud.com`… được nhận theo hình thức (domain/wildcard/IP sạch), có cảnh báo riêng và danh sách `classification.by_shape`. Nhãn mô tả ("Open Scope", "Your Own GitLab Instance"), `*ubereats.com` (dấu `*` không có dấu chấm) vẫn **không** thành rule cho phép.
- **Loại trừ có `*` giữa nhãn** (`*scaledsolutions.uber.com`, `scaledsolutions*.uber.com`) được thi hành bằng glob chỉ ở phía deny của ScopeGate (`fnmatch`, `*` cũng phủ dấu chấm: loại nhiều hơn chứ không bao giờ ít hơn); `normalize_pattern` vẫn từ chối glob khi làm allow.
- **OUT dạng mô tả** ("Other", "Fraud Reports") không chỉ tới host nào nên không thể che giấu một host IN: đánh dấu `blocking:false`, vẫn hiển thị để bạn tự đọc. OUT trông như host mà parser không hiểu vẫn **chặn** Light/Strong.
- Kỳ vọng sau sửa (dựa trên danh sách thật, bằng test `test_real_world_shapes_*`): GitLab, Shopify, Uber mở khoá Light/Strong nếu policy có; IN dạng mô tả vẫn nằm trong danh sách "chưa phân loại" để người dùng tự xử lý. Cần Codex chạy lại 3 handle để xác nhận.
- Độ dài policy GitLab: 26.066 ký tự (Codex đo cùng một POST); ước lượng Burp 17–18k chỉ là ước lượng, không có lệch.

## v1.3 — theo bằng chứng Wolt #29/#31 (WOLT_SCAN_EVIDENCE.md)

Không sửa vendor (submodule pin). Mọi thay đổi nằm ở BBASM; kiểm bằng tool giả + server localhost, không có request ra ngoài.

**1. Nguồn thụ động có giới hạn thời gian riêng** — `backend/shims/{curl,subfinder}` đứng trước công cụ thật: mọi `curl` không tự đặt `--max-time` được thêm `--max-time $BBASM_SOURCE_TIMEOUT` (45s), `subfinder` được thêm `-max-time` (`BBASM_SUBFINDER_TIMEOUT`, 120s). Engine tự thêm `~/go/bin` và `/usr/local/bin` lên đầu PATH nên shim cũng được xuất thành **hàm bash** (`BASH_FUNC_curl%%`) để không bị che. Shim ghi kết quả từng nguồn (`crt.sh`, `web.archive.org`, `subfinder`: ok/timeout/error) vào `.source_status.tsv` — chỉ host + kết quả. Nguồn lỗi → `stats.sources`, cảnh báo trong log, scan thành `done_partial`. Ingest đọc `subfinder.txt/crtsh.txt/wayback_subs.txt` khi `all.txt` chưa được gộp (trường hợp #29), mỗi host vẫn qua scope gate (`stats.partial_inputs`).

**2. Pipeline theo giai đoạn** (`runner._pipeline`): discovery → host nêu trong scope → **probe host đã khám phá theo đợt** (`BBASM_PROBE_BATCH`, chỉ liveness+tech) → quét sâu top host sống (`BBASM_DEEP_HOSTS`) → monitor. Mỗi giai đoạn có hạn chót tích luỹ (Light: 30/55/85/97% ngân sách; Passive: 90%) nên quá hạn chỉ cắt giai đoạn đó, giai đoạn sau vẫn chạy. `stats.stages` (trạng thái, ngân sách, đã dùng) và `stats.coverage` (**discovered/probed/unprobed**). Host thuộc đợt chưa xong tính là unprobed; còn unprobed hoặc giai đoạn bị cắt thì diff `complete=false` ⇒ không suy ra `gone`.

**3. OUT dạng URL có đường dẫn** (`scope_gate.url_rule`): `https://wolt.com/en/x` chặn đúng đường dẫn đó và phần dưới (không phân biệt hoa thường, giải mã `%xx`, bỏ `..`), **không** chặn cả host. Cưỡng chế ở mọi nơi gọi `gate.in_scope(url)` (ingest, monitor tải JS, export) và ingest đếm riêng `path_rule_blocked`/`by_path_rule` (không còn cộng vào "ngoài scope"). Crawler (katana), nuclei, ffuf không thể nhận loại trừ theo đường dẫn nên host có luật đó **chỉ được probe** (cảnh báo rõ trong Review/Run), trừ khi người dùng bật `allow_active_on_path_rules` có xác nhận.

**4. Header theo policy** — `ScanConfig.request_headers` (tối đa 5, kiểm chặt: không Cookie/Authorization/Host/Proxy-*…, ký tự in được) đi vào `BBHUNT_AUTH_HEADERS` chỉ cho lệnh chạm target (không cho discovery/passive); engine nạp vào httpx/katana/nuclei/ffuf/curl; shim `curl` bổ sung cho script không biết header (tải JS). Nguồn thụ động không bao giờ mang header. Mặc định theo program (`PUT /api/programs/{slug}/request-headers`, migration v3), gợi ý tên header từ policy (`request_header_hints`), Review chặn Light/Strong nếu policy nhắc header mà chưa điền/chưa xác nhận bỏ qua. Giá trị không vào log/audit/stats (stats chỉ ghi tên). Không thuộc profile.

**5. Nhãn trạng thái** — log gắn `tag` (`skipped_config`, `missing_tool`, `timeout`, `no_input`, `not_needed`); dòng ffuf của engine ở Light được viết lại thành "bỏ qua theo mức quét". Chỉ công cụ mà cấu hình thật sự dùng mới bị cảnh báo thiếu (`tools_needed`; `stats.missing_needed`). `dnsx` bỏ khỏi danh sách (engine không gọi), `bbscope/git/trufflehog` là tuỳ chọn (`optional_tools`). Brief có dòng phủ sóng/nguồn lỗi/giai đoạn bị cắt/OUT đường dẫn; trong lúc scan khác chạy hoặc scan lỗi/huỷ, `AGENT_BRIEF.md` được đánh dấu "scan #M … nội dung dưới là của scan trước". Program › Tổng quan có băng "số liệu là của scan #K lúc …, scan #M đang chạy".

**Chưa kiểm bằng công cụ thật (cần máy có Docker image):** cờ `-max-time` của subfinder thật; httpx/katana/nuclei/ffuf thật nhận `-H` (engine vốn đã truyền `BB_AUTH_ARGS`, kiểm bằng httpx giả + curl thật). Không thêm máy quét mới.

### v1.3.1 — sau QA host v1.3 (V13_HOST_RESULTS.md)
- **Katana thiếu header ở request khởi đầu** (P1): katana v1.8.0 gửi `/robots.txt` và `/sitemap.xml` (`-kf all`) không kèm `-H`. Khi có header policy, shim `backend/shims/katana` bỏ `-kf`; thông báo hiện trong Run ("Giai đoạn & độ phủ") và log. Vì engine chạy `timeout 300 katana …` (binary, bỏ qua hàm bash) nên recon_env xuất thêm hàm `timeout` chỉ đổi tên lệnh katana/curl/subfinder thành shim; ngữ nghĩa timeout giữ nguyên.
- **Nuclei "có" nhưng 0 template** (P1): `nuclei-templates` thành mục kiểm tra riêng (health, `missing_tools`, plan, báo cáo Run). Binary không có template ⇒ Review/Run ghi **thiếu công cụ**, không còn trình bày là "chạy, không có finding". Image không bake template (cập nhật lúc khởi động khi `BBASM_UPDATE_TEMPLATES=1`, cần mạng); đặt `=0` mà chưa có template thì nuclei coi như thiếu.
- Test mới: `test_v13_templates.py`, 2 ca katana trong `test_v13_pipeline.py`. nuclei + header **chưa kiểm tích hợp** (cần template fixture trong image); phép thử binary độc lập của Codex đã xác nhận `-H` hoạt động.

### v1.3.2 — sau QA host v1.3.1 (V131_HOST_RESULTS.md)
- **Nuclei tự tải template giữa scan** (P1, thật): không có template thì nuclei tự tải ~14.000 file từ internet và ăn hết ngân sách giai đoạn. Giờ (1) `recon_env` đặt `BBASM_SKIP_NUCLEI=1` khi `nuclei_templates_ready()` sai nên engine không gọi nuclei, và (2) wrapper `backend/shims/nuclei` (hàm bash + `timeout`) không bao giờ chạy nuclei khi thiếu template (ghi chú "chặn tải template tự động" ở Run) và luôn thêm `-duc` khi chạy. Phase Nuclei hiện **thiếu công cụ**, không còn "0 kết quả". Template do người dùng chủ động cài (`nuclei -update-templates` hoặc `BBASM_UPDATE_TEMPLATES=1` lúc khởi động).
- **Katana "GET / thiếu header"** (P1 do Codex ghi): **không tái hiện được trên request thật**; nguyên nhân là test so sánh tên header phân biệt hoa thường. Go chuẩn hoá `X-HackerOne-Research` thành `X-Hackerone-Research` trên dây, nên recorder không thấy khoá. Đã chạy lại với đúng binary katana v1.8.0 (SHA-256 khớp `scripts/tool-releases.json`) và 3 server localhost: `-kf all` ⇒ `/robots.txt`, `/sitemap.xml` KHÔNG có header; bỏ `-kf` (wrapper) ⇒ mọi request có header, kể cả cổng khác 80. Recorder trong test giờ so khoá viết thường; `BBASM_TEST_REAL_KATANA=<đường dẫn binary>` cho test dùng katana thật.

### v1.3.3 — sau QA host v1.3.2 (V132_HOST_RESULTS.md)
- Đạt: nuclei không được spawn khi thiếu template (scan 18,79s, 0 YAML sau scan, 0 kết nối ESTABLISHED, `top`/log không có nuclei), template có mặt ⇒ nuclei chạy `-duc` và gửi header; katana thật pass. 
- P2 đã sửa: Run giờ ghi rõ "nuclei KHÔNG được chạy … BBASM chặn việc tự tải template" ngay từ lúc dựng kế hoạch (`plan.tool_notes`, không phụ thuộc wrapper vì engine đã bỏ qua nuclei), và cảnh báo/phase/log dùng cùng một câu ("không được chạy"), không còn "chạy nhưng không kiểm tra gì".

## v1.3.4 — Wolt Passive #43: kẹt `running`, Cancel không phản hồi (P1), header bắt buộc (P2)

**Nguyên nhân gốc chưa được xác định.** Không tái hiện được cục bộ (dữ liệu cỡ Wolt, mock + 127.0.0.1); bằng chứng
cho thấy dữ liệu đã nhập (log cuối "stage main: ok") rồi dừng, trước khi có `done`. Các biện pháp dưới đây loại bỏ
những nguyên nhân khả dĩ và làm cho lần kẹt sau **lộ ra bước nào** thay vì im lặng.

P1
- `runner.py`: scan có threadpool riêng (`bbasm-run`, 6 luồng) và Cancel có pool điều khiển riêng (2 luồng) — Cancel
  không còn xếp hàng sau threadpool mặc định của asyncio.
- Các bước sau pipeline (ingest, monitors, diff, rank, brief) chạy qua `_post`: có giới hạn thời gian
  (`POST_LIMITS`), phát sự kiện `stage` (running/ok/timeout/error + `used_s`). Bước thiết yếu quá hạn → scan `failed`
  có lý do; bước phụ → ghi cảnh báo và đi tiếp. Scan luôn tới trạng thái cuối.
- `_finalize`: ghi trạng thái cuối thử lại tối đa 4 lần khi DB bị khoá.
- `cancel()`: mọi thao tác chờ đều có hạn (≤ ~8 s), tự ghi `cancelled` + `done`.
- `ingest.py`: quyết định scope một lần cho mỗi host (trước: mỗi URL một lần + một dòng audit) — profile 13k URL
  22 s → ~4.7 s; `normalize_host` dùng regex đơn. Tránh hàng chục nghìn lần ghi audit trên bind mount chậm.
- `/phases` single-flight + cache ngắn khi tính toán chậm; `count_lines` bỏ qua file > 50 MB — UI polling không chồng chất.
- Test: `test_v133_hang.py` (6 test).

P2
- Backend chặn Light/Strong khi policy nhắc header (`required_headers`) mà cấu hình không có header đó:
  lỗi `header_required` ở `/launch`, `POST /api/scans`, `/schedule`. Chỉ `skip_required_headers=true` (người dùng
  xác nhận đã đọc policy) mới cho qua. Passive không bị ảnh hưởng. Không bao giờ tự điền giá trị.
- Review gửi `skip_required_headers` theo ô xác nhận hiện có. Test: `test_v134_header_gate.py`.

Còn mở: Strong vẫn cần người dùng tự cân nhắc khi policy cấm brute-force (ffuf); chưa có xác nhận theo từng bước.

## v1.3.5 — Xác nhận header policy nhất quán (P2 của V134_HOST_RESULTS)

- Nghĩa duy nhất: xác nhận "đã đọc policy, không dùng header X" là **một phần config của draft/schedule**, theo **tên header**
  (`skipped_headers`). Header policy thêm về sau không bị xác nhận cũ phủ lên. `skip_required_headers: true` giữ làm dạng cũ (chấp nhận, không UI).
- Header đã được gửi thì tự bị loại khỏi `skipped_headers` (model validator). Không nằm trong profile; `/rescan` không chép xác nhận.
- Review: ô xác nhận suy ra từ config (không còn state cục bộ ghi đè lúc Launch); sửa cấu hình lưu vào draft sau 0,7 s nên tải lại trang
  giữ nguyên lựa chọn.
- Enforcement: `/launch`, `POST /api/scans`, `/schedule` (`header_required`) và **lúc `dispatch`** (policy có thể đã thêm header từ khi lên lịch).
- Audit: `request_headers` — `required`, `sent`, `skipped`, chỉ tên, không giá trị; ghi lúc Launch và lúc schedule xếp hàng.
- Tests: `test_v134_header_gate.py` (5), `test_scheduler.py` (+1), Vitest (+1).

## v1.3.6 — Rà soát UI/logic (V134_UI_LOGIC_AUDIT, 8 finding) + một lượt kiểm lại

| ID | Sửa |
| --- | --- |
| UI-1 | Tab URL có bộ chọn **Scan mới nhất / Tất cả scan**; ghi rõ "URL do scan #N nhìn thấy"; khi scan mới nhất có 0 URL mà lịch sử có thì hiện lời nhắn + nút "Xem URL lịch sử" thay cho "chưa có URL". Mỗi dòng có cột Scan (lần đầu→gần nhất). Phễu chỉ hiện khi xem scan mới nhất. Export theo cùng phạm vi. API: `scan=latest|all|<N>` cho `/urls`, `/urls/summary`, `/urls/export`; summary thêm `latest`, `history_total`. |
| UI-2 | Run của scan cũ: link URL mang `scan=<id>` ("ghi nhận tới scan N" — kho URL chỉ lưu first/last seen nên không khôi phục được "đúng những gì scan N thấy"; UI nói rõ điều này), nút Brief ghi "Brief hiện hành (scan #X)" và có ghi chú Host/Findings/Brief là hiện trạng program. |
| UI-3 | Lịch giám sát dùng **mặc định của program** (profile nếu cùng mức, header đã lưu) qua `program_config()` (cùng nguồn với draft). Thêm `automation_ack` (server bắt buộc cho light/strong) và `skipped_headers`; policy đòi header mà chưa có → `header_required`. Tắt giám sát giữ nguyên cấu hình đã lưu. UI hiện dòng "Mỗi lần chạy: …header gửi kèm: …", cảnh báo + ô xác nhận bỏ qua. Audit ghi `automation_ack_by_user` cho lịch. Summary trả `schedule.config` (chỉ tên header). |
| UI-4 | "Host đang hoạt động" → "trong inventory · N có HTTP · M chưa probe · K biến mất" (summary `assets_live`, `assets_gone`); bảng ghi "chưa có HTTP" thay cho "—". Danh mục: "Host trong inventory". |
| UI-5 | Diff trống: "Đã so sánh #N với #M: không phát hiện thay đổi" khi có baseline; chỉ nói thiếu scan khi thật sự thiếu baseline. |
| UI-6 | Resolve lại / "Scan lại" giữ `user_policy_text` đã dán (chỉ bản dán mới thay thế). |
| UI-7 | Tab Scope & policy hiện cả policy từ nguồn và policy người dùng dán, có nhãn. |
| UI-8 | Công tắc "Hiện giá trị" ở trình xem file còn sau khi bật (tắt lại được), tự tắt khi đổi file; nút tải ghi "Tải file THÔ" khi đang hiện. |

Kiểm lại thêm: Danh mục — công cụ tùy chọn (bbscope…) không còn nhãn đỏ "thiếu"; Profile — đổi preset khi đã chỉnh sửa hỏi xác nhận trước khi bỏ chỉnh sửa.
Tests: `test_v136_ui_logic.py` (4), `test_scheduler.py`, Vitest +8 (63 tổng). `review_tools/v134_policy_rescan_check.py` nay cho `after_manual_policy: true`; `v134_schedule_ui_check.py` cần gửi `automation_ack` (hành vi mới).
Chưa kiểm: export mọi chế độ, mobile (không làm), H1 thật, Light/Strong thật, hơn 1.000 hàng, trình duyệt khác.


## v1.3.7 — F1/F2/F3 của audit luồng input→output

- **F1 — lựa chọn ở Review thuộc về program.** Migration v4: `program.scope_selection_json`. Lúc launch lưu `excluded_hosts` (host bỏ chọn **và mục loại trừ tự gõ, kể cả URL có đường dẫn**) và `categories_disabled`. Draft mới (Scan lại), lịch giám sát lúc bật và **lúc mỗi lần chạy** đều áp dụng lại (`backend/scope_selection.py`: `apply_selection`). Chỉ thêm loại trừ, không bao giờ tự đưa lại; muốn đưa lại thì bỏ khỏi danh sách và launch (lựa chọn mới thay thế cũ). Review hiện ghi chú và số mục loại trừ. `effective_gate()` là cách duy nhất dựng gate từ scope + cấu hình: dùng ở plan (`ReconOrchestrator.build`) và ZIP.
- **F2 — ZIP "filtered".** Mọi host/IP/URL trên dòng đều phải thuộc scope (trước đây chỉ token đầu tiên), nhận cả `host/đường-dẫn` không scheme, `\/` trong JSON, IP; tên file kiểu `app.js` không tính là host. Gate giống scan đã chạy (gồm mục loại trừ tự gõ) cộng loại trừ hiện tại của program. Dòng không có host nào được giữ (không có gì để gán).
- **F3 — lịch kiểm lại gate.** `dispatch` gọi lại `launch_gate` và header theo policy hiện tại của program; nếu không đạt thì không tạo scan, ghi `schedule.last_error` + `last_error_at` (commit trước khi báo lỗi), Program hiện cảnh báo "lần chạy theo lịch gần nhất đã bị bỏ qua". Bật lại lịch hoặc lần chạy hợp lệ kế tiếp xóa lỗi.
- Tests: `test_v137_scope_selection.py` (5), Vitest +2; migration v4 trong `test_v13_headers_api.py`.

### v1.3.7.1 — kết quả host QA `14cfbed` cho F1–F3
F1 PASS (Rescan và lịch giữ 2 loại trừ, Review hiển thị), F3 PASS (lịch bị bỏ qua, có `last_error`, Program hiện cảnh báo), F2 FAIL một ca: JSONL có URL escape **hai tầng**. Sửa: bộ lọc ZIP bỏ mọi chuỗi dấu `\` đứng trước `/`, đọc JSON/JSONL theo từng chuỗi đã giải mã (kể cả `\u002f` và JSON lồng trong chuỗi), URL token không còn nuốt dấu `\` ở cuối. Test hồi quy trong `test_v137_scope_selection.py`.


## v1.3.8 — F4 (policy theo draft) và F5 (glob OUT)
- **F4:** mỗi draft lưu `policy_snapshot` + `policy_snapshot_at` lúc Resolve. Review, hint header, trust và kiểm header lúc launch đều dùng bản chụp của draft đó, không dùng policy mới nhất của program. Draft cũ khi program đã được Resolve lại (hoặc draft khác đã launch) hiện cảnh báo `policy_newer` kèm link tới draft mới nhất. Launch một draft đặt policy của program về bản chụp của nó cùng lúc với scope (scope và policy luôn đi cùng nhau).
- **F5:** ô OUT chấp nhận mẫu host glob (`api*.example.com`) như gate; cấu hình scan (`excluded_hosts`) dùng cùng quy tắc `normalize_pattern(deny=True)`. IN glob vẫn bị từ chối (sẽ mở rộng scope); OUT glob kèm đường dẫn (`https://*.x.com/admin`) vẫn từ chối, nay có thông báo rõ.
- Tests: `test_v137_scope_selection.py` (+2), Vitest +1.


## v1.4.0 — V1: cây sitemap (Dữ liệu › URL › "Cây sitemap")
- API `GET /api/programs/{slug}/urls/tree`: một cấp mỗi lần (`host`, `prefix`), `depth` 1–6 để mở nhiều cấp (tối đa 3000 nút/yêu cầu, báo `truncated`), phân trang con (`limit` ≤ 500, `offset`), cùng bộ lọc và phạm vi scan như `/urls` (`scan`, `q`, `tag`, `verification`, `min_score`). Sắp xếp `az` (không phân biệt hoa thường) / `score` / `count`, tuỳ chọn `folders_first`. Mỗi nút: số URL cả nhánh, điểm cao nhất, nhãn, mức kiểm chứng, "mới", scan thấy lần đầu→gần nhất, số biến thể query (`?id=1`, `?id=2` gộp một nút), URL đại diện. Cổng khác nhau là host khác nhau. Mã trong `backend/sitemap.py`.
- UI `SitemapTree`: mũi tên ▸/▾ mở/thu và tải con khi mở; "Thu hết", "Mở tới cấp 2/3", "Mở hết"; bàn phím ↑↓ Home End, → mở/vào con, ← thu/lên cha, Enter/Space; `role="tree"`/`treeitem`/`aria-expanded`; "Xem thêm" khi một nút có > 200 con; tìm kiếm tự mở các nhánh khớp; chép URL và mở tab mới (`noopener noreferrer`). Lần đầu chuyển sang cây, mức điểm đổi thành "mọi URL".
- Chưa làm: nhớ trạng thái mở khi rời trang; xác định method/status/length (dữ liệu chưa có cho mọi URL).
- Tests: `test_v138_sitemap.py` (5, gồm 20.000 URL < 2 s và phân trang), Vitest +3 (69). Kiểm bằng trình duyệt thật 1366px với 1.500 URL: không cuộn ngang, không lỗi JS.

### v1.4.1 — kết quả host QA `24f0c03` cho cây sitemap, F4, F5
Cây sitemap: dữ liệu và thao tác PASS (mở/thu, Xem thêm 150 mục, bàn phím, "Mở tới cấp 3" 302 ms), F4 PASS, F5 PASS. **FAIL một ca:** tìm kiếm chỉ tự mở tới cấp 3 nên file nằm sau 4 thư mục không hiện. Sửa: tìm kiếm và "Mở hết" yêu cầu `depth=12` (API nhận 1–12); khi vượt ngân sách 3000 nút thì ghi rõ số URL khớp (`matched`) và cách thu hẹp. Đã kiểm bằng trình duyệt thật: `item0999` sau 5 thư mục hiện ngay sau một lần tìm. Test: `test_v138_sitemap.py` (+1), Vitest cập nhật.


## v1.5.0 — dọn backlog: sửa nhỏ (A3–A7)
- **A3 Strong/ffuf:** Strong chỉ dò thư mục khi người dùng xác nhận policy cho phép (`ffuf_confirmed`, theo từng scan, không nằm trong profile) hoặc tắt bước dò thư mục. Server từ chối `ffuf_confirm_required` ở launch, `POST /api/scans`, bật lịch và lúc chạy lịch. Review hiện ô xác nhận, cảnh báo nếu policy nhắc brute-force/fuzz.
- **A4 nuclei:** mặc định loại template gắn thẻ `dos,fuzz,intrusive,bruteforce,brute-force` (`-etags` trong shim); tuỳ chọn `nuclei_allow_intrusive` (nằm trong profile) trong Review › Nuclei. Lựa chọn `-etags` tường minh không bị ghi đè.
- **A5:** `purge_drafts` không còn xóa draft thiếu dòng `scan_config` ở mỗi lần khởi động.
- **A6:** `LogBuffer` ghi journal trên một luồng nền theo thứ tự (không chặn event loop); `flush()` đợi ghi xong; `JobRunner.close()` flush.
- **A7:** so khớp đường dẫn OUT đọc như server: bỏ `;param` từng đoạn, `\` thành `/`, phân giải `..`; ingest xóa URL đã lưu từ scan cũ khớp rule OUT hiện hành (`url_funnel.purged_stale`).


## v1.5.1 — bảng công cụ duy nhất + trang "Công cụ & môi trường"
- `backend/tools.py` là bảng duy nhất mô tả công cụ/dữ liệu (loại, dùng cho bước nào, mức quét nào cần). `/api/health` lấy `DEPTH_TOOLS`/`OPTIONAL_TOOLS`/`EXECUTABLES` từ đây, giữ nguyên dạng JSON cũ. `tool_inventory()` trả trạng thái `ready | missing_binary | missing_data | wrong_binary` (httpx Python bị nhận ra), "ảnh hưởng" theo từng mức quét (ví dụ "Bước bị bỏ qua: Nuclei"), cách khắc phục, phiên bản ghim (offline, từ `scripts/tool-releases.json`) và phiên bản đo được.
- `GET /api/tools` chỉ tìm tệp. `POST /api/tools/check` mới chạy `<tool> -version` (kèm `-duc`, 8 s mỗi công cụ) và lưu `data/tools_check.json`. Test khẳng định `/api/health` và `/api/tools` không bao giờ lệch nhau.
- UI: mục "Công cụ & môi trường" (`#/tools?focus=<id>`), hook `useHealth()` dùng chung (làm mới khi quay lại tab) cho NewScan/Portfolio/Review; Review và Run có liên kết sang trang Công cụ; công cụ tùy chọn (bbscope, git…) không còn hiện như báo động.
- Tests: `test_v150_tools.py` (3), Vitest +3.


## v1.5.2 — Nuclei templates có chủ đích + template riêng
- **Kho template** (`backend/templates.py`): thư mục `templates_dir` (`BBASM_NUCLEI_TEMPLATES`, mặc định `data/nuclei-templates`; compose dùng **named volume** `bbasm-templates:/app/templates` để nhanh trên Windows/macOS và sống qua `up --force-recreate`; `down -v` sẽ xóa). Bố cục: `official/` (bộ đang dùng + `.bbasm-templates.json`: số lượng, thời điểm, nguồn, phiên bản), `official.staging/`, `official.prev/`, `custom/<id>.yaml`, `state.json`.
- **Cập nhật** (`POST /api/tools/templates/update`): một lần một job (khóa + trạng thái bền; job `running` mồ côi lúc khởi động thành `failed`); kiểm dung lượng trống; chạy `nuclei -update-templates` với HOME tạm (không phụ thuộc cờ `-ud` chưa kiểm chứng); **nuclei thoát mã 0 cả khi tải lỗi** (kiểm bằng thực tế) nên kết quả được xét theo số template tải về (`BBASM_TEMPLATES_MIN`, mặc định 100): thiếu thì coi là tải không đầy đủ và **giữ bộ cũ**; lỗi 403/rate limit/mạng/hết giờ/hết đĩa được diễn giải bằng tiếng Việt; thay bộ bằng đổi tên. Ghi audit `template_update`; không request nào tới target.
- **Khởi động:** `bootstrap` chỉ migrate (không còn tải đồng bộ trước khi server lên). `BBASM_UPDATE_TEMPLATES`: `auto` (mặc định: cài nền một lần nếu chưa có), `1` (mỗi lần), `0` (không).
- **Sức khỏe nhanh:** `nuclei_templates_ready` đọc marker nhỏ thay vì quét 14k file; vẫn nhận bộ cũ ở `~/nuclei-templates`. Shim nuclei dùng `-t <official>` (+ template riêng đã chọn) khi có bộ quản lý; không có template thì không chạy và ghi chú "cài ở trang Công cụ".
- **Dấu vết:** `stats.nuclei_templates` của từng scan ghi số lượng/thời điểm/phiên bản bộ chính thức và id template riêng đã dùng.
- **Template riêng** (`POST /api/tools/templates/custom`, `DELETE …/custom/{id}`): chỉ YAML UTF-8 ≤ 256 KB, tối đa 200; từ chối `code/javascript/headless/file/flow`, dòng yêu cầu hoặc `path` bắt đầu bằng URL tuyệt đối, khối `tcp` nhắm địa chỉ cố định, id lạ/trùng; thêm `nuclei -validate -duc`; không chạy khi nhập. Chạy **thêm** bộ chính thức và chỉ khi chọn ở Review cho từng scan (`nuclei_custom`, không nằm trong profile). Xóa template riêng không đụng bộ chính thức.
- UI: panel "Nuclei templates" trên trang Công cụ (cài/cập nhật, trạng thái job, danh sách và nhập template riêng); Review có ô chọn template riêng. PyYAML thêm vào `requirements.txt` (cần build lại image).
- Tests: `test_v151_templates.py` (7), `test_v13_templates.py` (+2), Vitest +2. Chưa kiểm được với GitHub thật trong môi trường này (403 từ sandbox) và chưa chạy Docker: Codex cần kiểm `docker compose up --force-recreate` giữ nguyên số template.


## v1.5.3 — dọn bản nháp hàng loạt, lưu trữ / khôi phục / xóa vĩnh viễn program
- **Dọn draft:** `POST /api/drafts/delete {ids}` kiểm lại `status='draft'` cho từng id trong transaction (đã launch hoặc không tồn tại thì nằm trong `skipped` kèm lý do), xóa luôn program "mồ côi" chỉ sinh ra từ draft đó. Portfolio có lọc theo tên/nguồn, sắp xếp, chọn tay hoặc "chọn các bản đang hiện", xác nhận có liệt kê, ghi chú ngưỡng tự xóa 7 ngày. Không tự chọn theo tên.
- **Lưu trữ:** `POST /api/programs/{slug}/archive` (từ chối khi có scan queued/running) đặt `archived_at`, tắt lịch (`paused_by_archive=1`) và gỡ job APScheduler. Program bị ẩn khỏi Portfolio (có ô "Hiện cả program đã lưu trữ"). Lịch sử, Diff, finding, file giữ nguyên. Các thao tác ghi đổi hành vi (bật lịch, rescan, profile mặc định…) bị từ chối `program_archived`; dispatch lịch bỏ qua program đã lưu trữ/đang xóa. `POST …/restore` khôi phục nhưng **không tự bật lại lịch** (UI nói rõ). Launch một draft của program lưu trữ cũng khôi phục nó (Review có thông báo).
- **Xóa vĩnh viễn** (`lifecycle.py`): chỉ với program đã lưu trữ và không có scan chạy. `GET …/delete-preview` liệt kê chính xác số scan/asset/URL/finding/diff, thư mục và dung lượng; `DELETE …/{slug}` cần `confirm_slug` trùng tên (UI bắt gõ lại). Thứ tự: đặt `deleting_at` → copy audit vào `data/audit-archive` (+ tombstone) → đổi tên `targets/<slug>` sang `targets/.trash` (nguyên tử) → xóa dòng con→cha → xóa trash. Lỗi giữa chừng thì trả thư mục về chỗ cũ; đứt giữa chừng (mất điện) được hoàn tất tiến tới lúc khởi động (`finish_pending`). Từ chối symlink/slug lạ/đường dẫn ngoài `targets`. Log `data/logs/<id>.jsonl` và `_REPORT_CACHE` được dọn vì ID scan có thể được cấp lại (`LogBuffer.forget`).
- Migration v5 (chỉ thêm cột): `program.archived_at/deleting_at`, `schedule.paused_by_archive`.
- Tests: `test_v152_lifecycle.py` (7; đã sửa race: đợi worker nền xong rồi mới đặt trạng thái), Vitest +5 (79).


## v1.5.4 — V2: biểu đồ
- `GET /api/programs/{slug}/charts`: xu hướng của tối đa 30 scan hoàn tất gần nhất (host live, URL, finding từ `stats_json`; mới/đổi/mất từ `diff_event`), phân bố mã trạng thái (theo lớp 2xx…/chưa probe và mã phổ biến), top 10 công nghệ, top 10 host theo số URL (kèm điểm cao nhất), ma trận mức nghiêm trọng × tối đa 8 host nhiều finding. Chỉ tính host còn `active`. Chỉ đọc DB, không chạm target.
- Trang Program › Tổng quan có 3 panel: Xu hướng, Bề mặt hiện tại, Ma trận. Cần ≥ 2 scan hoàn tất mới vẽ xu hướng (nếu không có câu giải thích). Mọi giá trị đều in thành chữ (số, mũi tên ▲/▼ kèm chênh lệch so với scan trước), cột mới/đổi/mất khác nhau bằng họa tiết (đặc / sọc / chấm) chứ không chỉ màu, có "Xem dạng bảng", ô ma trận in số; dùng biến màu có sẵn nên theo dark mode.
- Run: thanh thời gian từng giai đoạn (đã dùng so với ngân sách, cùng một thang), giai đoạn dùng hết ngân sách có sọc và ghi chữ "dùng hết ngân sách". Chưa làm Gantt theo thời điểm bắt đầu vì dữ liệu chưa ghi thời điểm bắt đầu từng giai đoạn.
- Tests: `test_v153_charts.py` (2), Vitest +3 (82). Kiểm bằng trình duyệt thật 1366px sáng/tối: không cuộn ngang, không lỗi JS.

### v1.5.5 — kết quả host QA `d5d5ac9` cho v1.5.4
14/15 PASS (templates qua `--force-recreate`, cập nhật lỗi giữ bộ cũ, template riêng, dọn draft, archive/restore/delete, khôi phục sau gián đoạn, biểu đồ, health). **FAIL R2:** ZIP `filtered` giữ dòng `127.0.0.2/admin [200]` dù `/admin` thuộc OUT: IP literal chỉ được trích phần địa chỉ, mất phần `:port/đường dẫn`. Sửa: `IP_TOKEN` nay lấy cả `:port` và đường dẫn và đưa `http://<ip><đường dẫn>` vào kiểm gate như URL (host dạng tên đã được xử lý đúng từ v1.3.8). Test: `test_v137_scope_selection.py` (+1, và các ca token IP).
- CI `frontend-build` đỏ ở nhánh kết quả test không do mã sản phẩm: test Run dùng `getByText(/52/)` trong khi thời gian "đã chạy" của scan giả tính theo đồng hồ thật (ngày 16/10 ra "52.2 giờ"). Test nay chỉ khớp phần tử `strong` của funnel.


## v1.6.0 — xử lý audit arc-bbp Strong #65
Chi tiết từng mục, trạng thái và quyết định còn mở: `ARC_BBP_TRIAGE.md`. Điểm chính:
- **Takeover (F1):** `backend/asm/takeover.py`; ứng viên subjack là `subjack:<SERVICE>`, Medium, chưa xác minh. `backend/repair.py` sửa dữ liệu cũ lúc khởi động (sao lưu `bbasm.db.pre-repair-*` trước, tạo lại Brief, ghi `stats.repairs`, hiện ghi chú trên UI). Có thể chạy lại an toàn.
- **nmap/ffuf:** probe không còn nmap; shim `nmap` (`--host-timeout`, tổng thời gian) và `ffuf` (`-ac`, `-maxtime`); biến `BBASM_NMAP_TIMEOUT`, `BBASM_NMAP_HOST_TIMEOUT`, `BBASM_FFUF_MAXTIME`, `BBASM_PROBE_BATCH` (50). Cấu hình theo scan: `nmap_timeout`, `ffuf_maxtime`, `deep_hosts`.
- **Độ phủ & ngân sách:** mỗi lệnh có trần theo phần còn lại của stage; coverage `attempted/responded/completed/unreached`; `stats.unprobed_hosts`; stage ghi `commands_ok/timeout/skipped`. Trần stage: 25/45/62/95%.
- **Kết quả đọc đúng:** `backend/asm/results.py` (nmap greppable, ffuf, nhận diện CDN); phase `partial`.
- **Scope/asset:** `backend/coverage.py`, `POST /api/scans/{id}/coverage`; repo có hướng dẫn giới hạn bị khóa (`source_full_repo_ok`); domain gốc tường minh (`include_apex` + `apex_confirmed`, server từ chối nếu thiếu xác nhận, cả lịch giám sát).
- **Funnel:** `in_scope + from_probe = stored`. **Nhãn auth** theo segment. **F6:** “ghi nhận lần đầu”.
- **UI:** panel độ phủ ở Review/Run/Tổng quan, cây sitemap mới, tab program lưu trữ.
- Tests: `test_v160_takeover.py`, `test_v160_p1.py`, `test_v160_results.py`, tích hợp `test_v13_pipeline.py` (+1), Vitest +6.


## v1.6.1 — host audit v1.6.0 (`test/v160-host-audit`, 63044d3): repair không idempotent, test phụ thuộc PATH
- **Repair không idempotent:** `backend/repair.py::repair_takeover` nhánh thiếu `subjack.txt` hạ severity về `info` nhưng giữ `name='subjack.txt:candidate'`, nên câu query chọn nhóm cần sửa ở đầu hàm khớp lại đúng các row đã sửa ở lần khởi động sau — tạo thêm backup DB và thêm entry `stats.repairs` mỗi lần, vô thời hạn. Đổi `name` thành `subjack:unverifiable` khi không còn file; lần gọi `run_repairs` thứ hai giờ là no-op thật (`result == []`, không backup mới). Test: `test_v160_takeover.py::test_without_the_original_file_nothing_stays_high`.
- **Test phụ thuộc binary trên PATH:** `test_v13_status.py`, `test_v150_tools.py`, `test_v151_templates.py` cô lập bằng `monkeypatch.setenv("PATH", ...)`, nhưng `Settings.tool_search_path()` luôn chèn `~/go/bin`, `/opt/homebrew/bin`, `/usr/local/bin` **trước** `$PATH` (để khớp PATH của engine vendor) — máy chạy test có nuclei/ffuf thật ở `/usr/local/bin` sẽ làm các test "giả định thiếu tool" tìm nhầm binary thật. Đổi sang `monkeypatch.setattr(type(settings), "tool_search_path", ...)` theo đúng idiom đã dùng ở `test_health.py`/`test_v160_p1.py`.
- **Nuclei — độ phủ thật (NUCLEI_COVERAGE_FOLLOWUP.md):** `vendor/claude-bug-bounty/tools/recon_engine.sh` Phase 9 thêm `-stats-json`, ghi stderr vào `nuclei/stats.jsonl` (trước đó `2>/dev/null`), ghi `nuclei/coverage.json` (`live_urls`, `given_urls`, `limit`, `quick`, `timed_out`, `last_stats`), cảnh báo khi giới hạn 50/200 URL/lượt cắt mất URL. **Không đổi** `NUC_LIMIT` hay severity/tag filter. `backend/asm/results.py::read_nuclei_coverage`/`summarize_nuclei` đọc file này; `backend/asm/phases.py` Run hiện "X/Y URL đưa cho nuclei" + số template/request thật từ nuclei, phân biệt rõ với `stats.nuclei_templates` (số đã **cài**, không đổi). Không có `coverage.json` (dữ liệu cũ, hoặc `BBASM_SKIP_NUCLEI`) → giữ nguyên hành vi cũ (đếm dòng `findings.jsonl`). Submodule bump: `1e9a1e3` (nhánh `claude/nuclei-stats-coverage`).
- Kiểm bằng binary nuclei/ffuf thật (chỉ `127.0.0.1`, container cách ly): run thường, bị cắt URL, timeout — đều đúng.
- Tests: `test_v160_results.py` (+5), Vitest +1 (89). 450 backend passed cả có/không nuclei+ffuf thật trên PATH.

## v1.6.2 — host audit v1.6.1 (`test/v161-host-audit`, 6b9efe6): coverage.json hỏng khi nuclei lỗi, giới hạn sai khi gộp
- **`coverage.json` hỏng khi nuclei thất bại (C9):** nuclei có thể ghi một dòng lỗi dạng chữ (`[FTL] Could not run nuclei: ...`) vào **cùng** luồng stderr đang được ghi vào `nuclei/stats.jsonl`, ngay sau dòng `-stats-json` cuối — `tail -n1` lấy nhầm dòng lỗi đó, làm cả `coverage.json` không parse được. Sửa: `last_stats` chỉ lấy dòng thật sự có dạng JSON (`grep -E '^\{.*\}$' | tail -n1`); thêm field `failed` (true khi nuclei thoát mã khác 0 và khác 124). `read_nuclei_coverage` bỏ qua số liệu `last_stats` khi `failed=true` (toàn là giá trị canh giữ như `"n/a"`/số int64 lớn, không phải số thật). Run hiện "LỖI: nuclei không chạy được..." thay vì im lặng nói "0 kết quả". Kiểm bằng nuclei thật với `-t` trỏ thư mục không tồn tại (exit 1, `coverage.json` vẫn parse được, `failed=true`).
- **Giới hạn sai khi gộp quick/full (C8):** `summarize_nuclei()` từng lấy `limit` của lượt đầu tiên (`runs[0]`), nên scan có cả lượt quick (50) và lượt full (200) báo sai "giới hạn 200" cho cả lượt bị cắt ở 50. Đổi field `limit` (số) thành `limits` (danh sách giá trị khác nhau thực sự dùng); Run hiện đúng "mỗi lượt có giới hạn riêng: 50, 200 URL" khi khác nhau, giữ câu cũ khi chỉ có một giá trị.
- Submodule bump: `488d910` (tiếp `claude/nuclei-stats-coverage`).
- Tests: `test_v160_results.py` (+4). 453 backend passed cả có/không nuclei+ffuf thật trên PATH; 89 Vitest passed, tsc sạch, build OK.

## v1.6.3 — UX-1 (bảng Cổng/Dịch vụ, Đường dẫn dò được) + ENG-1 (open_ports.txt)
- **UX-1 (BACKLOG mục 4):** `GET /api/programs/{slug}/ports`, `GET /api/programs/{slug}/dirs` (mới, `?scan=latest|<id>`) — đọc lại `backend.asm.results.summarize_ports`/`summarize_dirs` của một scan cụ thể, không có bảng DB riêng (dữ liệu nằm trên đĩa theo scan). Tab Dữ liệu › "Cổng/Dịch vụ" và "Đường dẫn dò được" mới, dùng đúng câu chữ Run đã có (cổng CDN, nmap dở dang, nhiễu ffuf, host chỉ có 403).
- **ENG-1 (BACKLOG mục 6, NOTES FN2):** `recon_engine.sh` Phase 3 — `open_ports.txt` dùng `sed` tham lam chỉ giữ cổng cuối của mỗi dòng greppable (một host có nhiều cổng mở trên 1 dòng). Đổi sang `grep -oE '[0-9]+/open'` giữ đủ mọi cổng. `backend/asm/results.py` đã đọc `nmap_greppable.txt` trực tiếp từ v1.6.0 (FN2) nên số liệu BBASM hiển thị không sai; chỉ file tóm tắt thuần văn bản này sai. Submodule bump: `bfd61ba`.
- Tests: `test_v163_ports_dirs_api.py` (4 mới), Vitest +3 (92). 457 backend passed cả có/không nuclei+ffuf thật trên PATH; tsc sạch, build OK.

## v1.6.4 — host audit v1.6.3 (`test/v164-host-audit`, 3379dfd): UX-1 bỏ qua scan đã chọn, đọc nhầm output mồ côi
ENG-1 PASS không cần sửa thêm. UX-1 FAIL 2 finding P2, cả hai đã sửa:
- **Frontend bỏ qua `scan=<id>`:** `PortsView`/`DirsView` gọi `/ports`, `/dirs` không kèm query nào, nên mở `?v=ports&scan=1` vẫn hiện scan mới nhất. Giờ nhận prop `scan`, forward thành `?scan=<id>`, hiện "Đang xem scan #N" khi có chọn.
- **Draft có output mồ côi bị đọc như kết quả thật:** `_resolve_scan_id` (khi chọn theo id cụ thể) không lọc trạng thái, nên scan còn ở `draft` (chưa launch) mà có file sót lại dưới thư mục số của nó (id bị dùng lại, bản chép lạc) vẫn trả `found=true`. Giờ từ chối `status='draft'`, giống cách `latest` đã loại mọi trạng thái trước `queued`.
- Tests: `test_v163_ports_dirs_api.py` (+2), Vitest +1. 459 backend passed cả có/không nuclei+ffuf thật trên PATH; 93 Vitest passed (chạy 3 lần liên tiếp để chắc không còn flaky do thiếu `await`); tsc sạch, build OK.

## v1.6.5 — nuclei "tự chọn theo công nghệ" (`-as`) + tra cứu template theo tag
Một nhánh cụ thể của quyết định D1 (độ phủ nuclei): người dùng chọn phương án "B — auto-select theo công nghệ", kèm yêu cầu có mục riêng cho người dùng xem trước (tag nào có sẵn) và xem sau (scan đó thực nạp gì).
- **Trước khi scan — tuỳ chọn:** `ScanConfig.nuclei_auto_select` (mặc định tắt, có trong profile). Bật ở Review/Profiles (panel Nuclei) → thêm `-as` vào lệnh nuclei: nuclei tự dò công nghệ (kiểu Wappalyzer) trên từng host rồi chạy thêm template khớp, ngoài severity/tag đã lọc. **Không biết trước** template nào sẽ chạy cho host cụ thể — chỉ biết sau khi nuclei hỏi host thật.
- **Trước khi scan — tra cứu:** `GET /api/tools/templates/lookup?tag=<text>` (`backend/templates.py::TemplateStore.lookup_by_tag`) chạy `nuclei -t <official> -tl -tags <tag> -duc` (liệt kê thuần, không request tới target nào) trên bộ đã cài, đọc `name`/`severity` của các file khớp. Panel Nuclei ở ConfigEditor có ô "Tra cứu template theo công nghệ/tag" dùng API này — trả lời "công nghệ X có N template sẵn sàng", không phải "scan này sẽ chạy N template".
- **Sau khi scan — xem thực tế:** khi `-as` bật, shim `nuclei` thêm `-vv` (nuclei tự in mọi template đã nạp) và chuyển hướng stdout vào `nuclei/templates_loaded.txt` (không đụng `nuclei/stats.jsonl` ở stderr — vẫn hoạt động bình thường cạnh nhau). File này tự động xuất hiện trong nút "Đọc file thô" sẵn có của bước Nuclei ở Run (không cần code frontend mới — cơ chế đa-file đã có từ port_scan/takeover). Danh sách có thể dài (quan sát thật: ~2130 dòng) vì gồm cả bộ dò panel/công nghệ nuclei luôn chạy trước khi chọn lọc — không phải lỗi.
- Kiểm bằng nuclei v3.4.10 thật: `-as -vv` tiêm đúng, `templates_loaded.txt` và `stats.jsonl` cùng tồn tại không đè nhau, `findings.jsonl` không đổi hành vi.
- Tests: `test_v151_templates.py` (+4: lookup đọc đúng/validate tag/truncate/API), `test_v13_templates.py` (+2: shim thêm -as/-vv + capture file, không lặp khi đã có -as), `test_v137_scope_selection.py` (+1: env var), Vitest +1. 466 backend passed cả có/không nuclei+ffuf thật trên PATH; 94 Vitest passed (chạy 3 lần); tsc sạch, build OK.
- Chưa làm (ngoài phạm vi lượt này): phương án A (lọc theo `-tags` include, không chỉ severity) — vẫn còn trong BACKLOG nếu muốn làm tiếp.

## v1.6.6 — host audit v1.6.5 (`test/v166-host-audit`, db4442a): `-as` lỗi trong image chuẩn, số liệu mâu thuẫn, file lẫn finding
Codex chạy bằng nuclei thật (v3.11.1) qua đúng Phase 9 của engine, phát hiện 1 lỗi P1 chặn PASS và 2 lỗi P2/P3 về độ tin cậy số liệu. Cả ba đã sửa:
- **P1 — `-as` thất bại trong image chuẩn (chặn PASS):** tái hiện bằng binary thật (nuclei 3.4.10 và 3.11.1): `-as` **luôn đọc `$HOME/nuclei-templates`** để dựng "automatic scan service" — bỏ qua hoàn toàn `-t`, và **không theo symlink** đặt ở đó (đã tự kiểm: symlink trỏ tới bộ quản lý đầy đủ vẫn báo "no templates found"/"không có file"). Vì bộ quản lý của BBASM nằm ở `templates_dir/official` (khác `$HOME/nuclei-templates`), `-as` luôn lỗi trong môi trường thật dù `official/` có đủ template. Sửa: shim giữ một **bản chép hard-link** (không symlink) của `official/` tại đúng `$HOME/nuclei-templates`, làm mới trước mỗi lần chạy (đo thật: ~0,3s cho 14.075 template, gần như miễn phí dung lượng vì chung inode trên cùng filesystem); rơi về chép thật (`cp -r`) nếu hard-link thất bại (khác filesystem). Không đồng bộ khi bộ quản lý đã chính là `$HOME/nuclei-templates` (trường hợp không có `BBASM_NUCLEI_OFFICIAL` riêng).
- **P2 — số template mâu thuẫn:** nuclei (quan sát trên bản 3.11.1 khi dùng `-as`) có thể ghi `"templates":0` trên cùng dòng `-stats-json` có `matched`/`requests` thật. `read_nuclei_coverage` giờ phát hiện mâu thuẫn này (`templates_unreliable`), không hiện "0 template" như số thật; Run hiện "đã gửi N request... — số template nuclei tự báo không đáng tin ở lượt này" thay vì im lặng hoặc nói sai.
- **P3 — `templates_loaded.txt` lẫn bản ghi finding JSONL:** nuclei in nguyên dòng JSON của finding ra stdout dù đã có `-o`/`-silent`, cùng luồng với các dòng `-vv`. Shim giờ lọc bỏ dòng bắt đầu bằng `{` trước khi ghi `templates_loaded.txt` (dùng pipe + `${PIPESTATUS[0]}` thay `exec` để giữ đúng mã thoát); `findings.jsonl` (qua `-o`) vẫn là nguồn finding duy nhất.
- Kiểm lại toàn bộ bằng nuclei thật (git clone trực tiếp bộ nuclei-templates đầy đủ thay vì chờ nuclei tự tải, để test nhanh): `-as` thành công (exit 0), `templates_loaded.txt` không còn dòng JSON, `stats.jsonl` vẫn tái hiện đúng mâu thuẫn `templates:0` + `matched:4`/`requests:4979` đã sửa ở backend.
- Tests: `test_v13_templates.py` (+3: đồng bộ hard-link, không đồng bộ khi trùng đường, lọc JSON khỏi templates_loaded.txt), `test_v160_results.py` (+2: đọc đúng mâu thuẫn, Run không hiện "0 template"). 470 backend passed cả có/không nuclei+ffuf thật trên PATH; 94 Vitest passed; tsc sạch, build OK.

## v1.6.7 — D1 chốt: bỏ giới hạn 50/200 URL/lượt của nuclei
Người dùng chốt D1 (2026-10-17): mọi URL đang sống đều phải được đưa vào nuclei, không còn cắt theo số lượng; nếu vẫn thiếu giờ, chấp nhận scan chạy lâu hơn — không làm thêm cơ chế "quét tiếp" (giữ nguyên quyết định tách biệt D3).
- **`recon_engine.sh` Phase 9:** bỏ `head -50/-200`; `cp` toàn bộ `live/urls.txt` vào `nuclei/targets.txt` — `given_urls` luôn bằng `live_urls`. `NUC_TIMEOUT` (hằng số cứng 600s Quick/1800s Full) đổi thành biến môi trường `BBASM_NUCLEI_TIMEOUT` (mặc định 3600s Quick/7200s Full nếu không được truyền) — đây chỉ là **lưới an toàn phụ** khi script chạy ngoài `JobRunner`; lưới an toàn thật là ngân sách còn lại của giai đoạn (`runner.py::_stage`, đã có từ v1.6.0: mỗi lệnh chỉ được phần ngân sách giai đoạn còn lại × tối đa 1,5), cắt và báo "Chạy dở dang" trung thực nếu hết giờ.
- **Backend:** `Settings.BBASM_NUCLEI_TIMEOUT` (mặc định 3600) + `ScanConfig.nuclei_timeout` (ghi đè theo từng scan, `None`=mặc định máy chủ) — cùng mẫu với `nmap_timeout`/`ffuf_maxtime` đã có. Ô nhập mới ở ConfigEditor panel "Ngân sách công cụ".
- `coverage.json` giữ field `"limit"` để tương thích dữ liệu cũ nhưng luôn ghi `0` (không giới hạn) cho scan mới; `backend.asm.results`/`phases.py` không cần đổi gì (logic "truncated"/"limits" cũ tự nhiên không còn kích hoạt vì `given==live`).
- Kiểm bằng nuclei thật: 300 URL đưa đủ 300 (trước đây bị cắt ở 200), `BBASM_NUCLEI_TIMEOUT=5` cắt đúng 5s và báo `timed_out:true`, mặc định không ghi đè ra đúng 3600/7200 theo Quick/Full.
- Tests: `test_v137_scope_selection.py` (+1: env var `BBASM_NUCLEI_TIMEOUT`). 471 backend passed cả có/không nuclei+ffuf thật trên PATH; 94 Vitest passed; tsc sạch, build OK.
- `BACKLOG.md` mục "Độ phủ nuclei" cập nhật: D1 **đã chốt và làm xong** phần giới hạn URL; không còn mục "chưa quyết" nào liên quan tới 50/200 nữa.

## v1.6.8 — host audit v1.6.7 (`test/v168-host-audit`, 05e0692): log "no findings" sai khi timeout
NUC-6 PASS các tiêu chí chính (300/300 URL không còn cắt ở 200, `BBASM_NUCLEI_TIMEOUT` override đúng, ô nhập Review đúng, hồi quy xanh). 1 finding P2 đã sửa:
- **Log nói "no findings" sau khi nuclei timeout:** `6638e72` (v1.6.2) đã xử lý nhánh "nuclei lỗi" nhưng bỏ sót nhánh "nuclei hết giờ" (`NUC_EXIT=124`) — vẫn rơi vào `else: log_done "nuclei: no findings"` ngay sau cảnh báo "stopped after Ns (timeout) ... PARTIAL" phía trên, đọc như đã chạy xong sạch 0 kết quả dù phần lớn target chưa kịp quét. Thêm nhánh `elif NUC_EXIT=124` ghi rõ "không có finding trong phần đã chạy trước khi hết giờ — chưa phải lượt chạy xong". Kiểm bằng script tách riêng 3 nhánh (clean/failed/timeout) — đúng cả ba.
- Submodule bump: `ccae299`.

## v1.6.9 — chọn kết quả theo lần scan (Program page), merge từ Codex `codex/scan-output-selector`@97ab94f
Codex (ngoài phạm vi QA đã thống nhất — tự viết feature, không phải task nào trong `COORD_TASKS.md`) thêm bộ chọn "xem kết quả của lần scan" trên trang Program, giữ lựa chọn khi chuyển tab Dữ liệu/Phát hiện/Lịch sử/Hướng dẫn; Run cũng forward lựa chọn sang Program.
- API `assets`/`surface`/`findings` nhận `scan=latest|all|<id>` (`all` mặc định, tương thích client cũ); `GET /{slug}/scan-options` trả danh sách gọn mọi scan hoàn tất (không giới hạn 100 record như `detail`).
- Host/Finding ở lần scan cũ là **ước tính** (lọc theo `first_seen_scan`/`last_seen_scan`, không phải snapshot — status/tech/rank vẫn là hiện hành); URL/Cổng/Đường dẫn/Diff đọc đúng dữ liệu của lần scan đó; Brief/ZIP chỉ có bản hiện hành. Giao diện cảnh báo rõ ở mọi nơi dùng ước tính và dẫn link ra Run xem file gốc. Chi tiết: `SCAN_OUTPUT_SELECTOR_REVIEW.md`.
- Tôi review (không phải chỉ merge thẳng): logic SQL/validate đúng, chạy lại test thật xác nhận không regression. Tìm 1 lỗ hổng nhỏ: `/diff` nhận `scan_id` thẳng không kiểm tra thuộc program này/không phải draft như các bộ chọn khác đã làm — trước đây frontend chưa bao giờ gửi tham số này nên không lộ, nhưng `DiffView` mới gửi thẳng từ URL `?scan=` (người dùng sửa được). Không rò dữ liệu thật (do `diff_event` tự giới hạn theo `program_id`, sai thì trả rỗng) nhưng âm thầm sai thay vì báo lỗi `invalid_scan` như mọi nơi khác — đã vá (`58c5c3f`) + thêm test `test_diff_rejects_a_draft_or_foreign_scan_id`.
- Tests: 477 backend passed (cùng 11 fail môi trường có sẵn trên HEAD trước merge — thiếu curl trong container chuẩn, không liên quan thay đổi này, đã verify chạy lại trên HEAD cho kết quả giống hệt); tsc sạch; 95 Vitest passed; build OK.
- Đã nhắc Codex: chỉ QA theo `COORD_TASKS.md`, không tự viết feature sản phẩm nữa — xem "Quy tắc bàn giao" cuối file đó.

## v1.6.10 — tự QA bộ chọn scan + audit UI/UX và luồng recon (2026-10-18)
Tôi tự mở browser test v1.6.9 trên dữ liệu thật (`arc-bbp`), tìm và sửa ngay các vấn đề sau; sau đó audit tiếp toàn bộ panel cấu hình và `recon_engine.sh` theo yêu cầu người dùng.

- **Gộp 2 banner Overview** còn chéo nhau khi xem scan cũ (banner mới "Các ô bên dưới là inventory hiện hành" đứng cạnh banner cũ "Số liệu dưới đây là của scan #N" — không nói chúng là cùng một thứ). Giờ chỉ 1 câu, nêu rõ khác với scan đang xem.
- **Thẻ TECH trong bảng Host** nhiều thẻ làm dòng cao lệch nhau — `TechCell` mới chỉ hiện 3 + nút "+N nữa".
- **Cột "Chi tiết" Findings** URL dài bị cắt cứng sát mép — wrap trong 420px.
- **Spinner ô số bị lệch** (panel Ngân sách công cụ) — ẩn hẳn nút tăng/giảm gốc trình duyệt toàn app.
- **`.table-wrap` có bóng mờ cuộn ngang** (bảng Tools, Host) — báo còn nội dung thay vì cắt im lặng.
- **Tự QA phát hiện bug do chính đợt sửa trên gây ra:** dải tóm tắt severity mới thêm ở Findings — bấm "1 critical" dẫn tới bảng rỗng vì `findings_by_severity` (backend) là tổng **toàn bộ chương trình mọi thời điểm**, không khớp bộ lọc "scan mới nhất". Bỏ click-to-filter, chỉ hiển thị kèm ghi chú rõ phạm vi.
- **`GET /api/meta/tool-defaults`** (mới): 4 ô ngân sách tuỳ chọn (nmap/ffuf/nuclei timeout, deep_hosts) trước đây để trống chỉ hiện chữ "mặc định", không nói con số thật — giờ `ConfigEditor` hiện đúng số hiện hành của máy chủ (placeholder + ghi chú "(hiện là Ns)"), không bake số vào `ScanConfig` để vẫn theo đúng khi admin đổi server setting sau này.
- **Dọn 18 bản nháp QA rác** (`qa-v134-ui`, `qa-v13-draft-*`...) khỏi dashboard thật; giữ nguyên các bản nháp trông như người dùng tự thử (`uber`/`shopify`/`gitlab`/`verisk-vdp`).
- **Audit `recon_engine.sh`** theo yêu cầu: tìm Phase 10 "Takeover quick-check" mồ côi hoàn toàn (không ai đọc), ffuf/katana/config-expose/js-analysis hardcode `head -N` không cấu hình được — **chưa sửa**, ghi vào `BACKLOG.md` mục "Còn dở trên chức năng hiện có" chờ ưu tiên.
- Tests: 478 backend passed (cùng 11 fail môi trường có sẵn mọi lần chạy trong phiên này); 96 Vitest passed; tsc sạch; build OK.
