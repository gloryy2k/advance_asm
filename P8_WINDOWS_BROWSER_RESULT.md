# P8 Windows, browser and H1 verification

Date: 2026-10-13–14 (Asia/Saigon). Branch: `build/p8-acceptance`.
Base: `f79c9fb`, plus the fixes committed with this report. Vendor remains
`7acb66a6c4450786b0d18794f528a1452f591b1d`; no vendor source/pointer change.

## Fixes

- B1: install pinned `websockets==15.0.1`. Scan status polls REST every 3s,
  retries transient errors, stops at all four terminal states and aborts on
  unmount. Logs retain WebSocket replay/reconnect without endless terminal retries.
- B2: explicit accessible name for Depth and a role-based E2E selector.
  E2E now asserts the **status badge**, not log text that can also say `done`
  for a failed scan.
- Windows Docker: the submodule checkout contained CRLF shell scripts. The
  parent `.gitattributes` does not apply inside a submodule. This caused real
  recon and scope aggregation to fail despite healthy HTTP/tool checks.
  Normalize only the copied image's `*.sh` files to LF; preserve source/pin.
  Docker regression now checks both shell entrypoints with `bash -n` and a
  real WebSocket handshake. The image build normalized 24 shell files.
- TestClient alone cannot catch a missing uvicorn WebSocket protocol dependency;
  added an actual localhost uvicorn handshake/replay integration test.

## Results

Environment: Windows host, Python 3.13, Docker Desktop Linux engine 28.3.2,
`docker-desktop` WSL version 2. User explicitly authorized local integration.

| Check | Result |
| --- | --- |
| `pytest -m "not integration" --tb=short` | 197 passed, 8 deselected, 26.19s |
| Frontend Vitest | 11 passed, including broken WS fallback for all terminal statuses |
| Frontend production build | Passed |
| Real uvicorn WS integration | 1 passed, 1.50s; HTTP 101 and replay |
| Enhanced Docker integration | 1 passed, 7.86s; cached build 3.37s, health/static/shell syntax/WS |
| Official browser pytest below | 1 passed, 7.35s |
| DB + schedule restart | Scan records and full schedule unchanged; scheduler job reload logged |
| Target files restart | All localhost target file SHA256 hashes unchanged |

PowerShell browser command (after starting the isolated test stack):

```powershell
$env:BBASM_E2E_TARGET='127.0.0.1'
$env:BBASM_E2E_URL='http://127.0.0.1:18765'
.venv/Scripts/python.exe -m pytest -q -m integration backend/tests/test_browser_integration.py
```

The real browser used exact Depth selection, launched passive scan #5, observed
the final `done` badge, and opened AGENT BRIEF. Earlier UI verification also
completed scan #4 without a page reload. Brief is 621 bytes with scope localhost,
one asset and no live probes/findings. These are loopback passive tests, not a
claim of successful active internet recon.

Compose project `bbasm-p8-windows` binds only `127.0.0.1:18765`, uses isolated
`data/p8-windows-runtime/{db,targets}`, disables template updates and historical
collection. The temporary daily/passive localhost schedule was disabled after
verification. Local evidence (ignored by Git): `persistence-before.json`,
`persistence-after.json`, `files-before.json`, `browser-brief.jpg`, and target
audit/output files below that directory. User `.env` was not changed.

Playwright/Chromium were installed for the opt-in test. Chromium download needed
`NODE_OPTIONS=--use-system-ca` on this host; TLS verification remained enabled.
Docker Desktop needed startup time after resuming on October 14.

## Live Nation: metadata only, not full H1 acceptance

Requested URL: https://hackerone.com/live_nation?type=team . Resolver input used
canonical `h1:live_nation` because the strict URL parser rejects query strings.
The default container resolver returned HTTP 200, scan #3 draft, no warnings,
25 assets: 22 web and 3 mobile. No H1 credentials were used: this exercises the
public metadata fallback, not authenticated H1 API access. Stored policy contains
asset instructions but **does not contain the full current program policy**.

The current official page was read separately in the browser on October 13
(policy updated September 25, 2026). It prohibits bots, automated scanners and
LLMs/generative AI for bug discovery. No Live Nation recon was launched. Audit
shows metadata fetch and offline scope aggregation; `started_at` is null. On the
October 14 follow-up, scan #3 is cancelled, not an executed scan.

Native Windows metadata fetch initially hit a CA verification error. A diagnostic
using the Windows trust store could resolve metadata, but it was not a default
runtime pass. The supported Docker path resolved successfully after the LF fix.
No certificate validation was disabled and no native recon support was added.

## Remaining acceptance

- H1 light scan → Brief needs a program explicitly permitting the intended
  automation, or a written exception. Do not use Live Nation for this test.
- Public metadata is insufficient to certify current full policy; review the
  official program page before any launch. H1 policy completeness remains open.
- Full detail checklist in ACCEPTANCE.md remains applicable: real scheduled
  execution, monitor fixtures with findings, narrow viewport/reconnect behavior,
  and other live evidence not established by the loopback E2E.
- Remote CI for these new fixes must be checked after push. Prior green CI is
  not evidence for the new commit. P8 is not declared fully closed.
