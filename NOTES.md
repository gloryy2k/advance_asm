# Implementation notes

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

## Phase boundary

P0 and P1 are implemented. P2 runner/orchestration/ingest are implemented and unit
tested, but P2 is NOT complete: live tool outbound enforcement remains unresolved.
See P2_EGRESS_REVIEW.md. No target traffic or real-tool integration tests have been run.

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
