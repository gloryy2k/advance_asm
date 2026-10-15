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
