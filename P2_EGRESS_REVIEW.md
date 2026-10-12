# Optional future hardening — Docker network layer (§13/§24)

This proposal is NOT a P2 requirement. The approved decision in
P2_COMPLETION_PLAN.md supersedes the historical proposal below. P2 T1–T5 use
audited-spawn plus safe default tool toggles; BBASM_RECON_DISABLED=1 is an
operator kill switch. Unit validation passed; real-tool validation T6 is pending.
Spawn auditing is not per-request auditing or network isolation. A future Docker
boundary remains optional work, not a blocker for P2 launches.

## Historical analysis (superseded; preserved for reference)

P2's queue, command planning, process-group teardown, replay and ingestion have unit
tests. Live recon is deliberately disabled by `ClosedEgress`; there is no ENV bypass.
This is an unfinished requirement, not a completed scope-containment implementation.

## Why the small toggle patch is insufficient

The reviewed pinned framework does more than connect to the initial input:

- httpx follows redirects; a permitted URL can redirect to an excluded hostname.
- katana discovers links; shell JS/config fetches consume recon-derived URLs.
- nuclei templates can generate secondary connections/callbacks.
- DNS wildcard/takeover checks query names beyond the initial seed list.
- secrets_hunter runs trufflehog with live key verification against issuer services.
- passive provider tools make their own third-party requests.

Filtering seed/discovery/output lists does not authorize, intercept or audit those
connections. Merely setting HTTP_PROXY also does not prevent a tool bypassing it.
Enabling normal spawning now would violate BUILD_SPEC §2.3, §2.8 and §8.4.

## Concrete implementation already available for review

- `ClosedEgress.check(plan, command)` records a denial before any process factory call.
- Unit tests supply an in-memory process factory and a test-only boundary.
- Launch currently queues, then ends `failed` with `Live recon disabled: per-request
  outbound enforcement is not implemented`. It never falls back to unrestricted spawn.
- The admission gate and ingestion gate still enforce the approved scan snapshot,
  excluded hosts and disabled categories. They are not described as network isolation.

## Proposed scope extension (requires a product/deployment decision)

Authorize a dedicated Linux execution boundary in P2 before proceeding to P3:

1. Isolate each tool process so arbitrary direct network access is denied by the OS;
   environment proxy settings alone are insufficient. Confirm the necessary container
   capability/network setup alongside §13/§24 instead of silently adding privileges.
2. Route supported HTTP/HTTPS traffic through a per-scan gate that validates each
   destination and redirect and writes audit records before forwarding. TLS traffic
   needs an enforceable destination/request policy, not an unrestricted CONNECT tunnel.
3. Define distinct, explicit passive-metadata destinations. These must never enlarge
   target scope. DNS resolution, IP/CIDR scanning and IPv6 require separate controlled
   paths; shared-IP hosting must not turn one allowed domain into an allowed IP range.
4. Disable automatic third-party credential verification and arbitrary callbacks unless
   separately authorized. This may require narrowly extending the vendor patch beyond
   recon_engine.sh; leave unsupported execution paths denied until then.
5. Add mock unit cases plus opt-in Linux/container adversarial integration checks:
   redirects to OOS, crawler OOS links, callbacks, DNS rebinding, shared-IP hosts,
   IPv6, repository path escape, proxy bypass and audit failure. No real target scans
   are needed for these tests; use local controlled fixtures.

Alternative: keep live execution disabled and postpone that boundary to the Docker
phase. That explicitly leaves P2 incomplete and requires relaxing the requested
strict phase order. No such change is assumed by this implementation.
