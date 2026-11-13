# AD-422 Core-only validation renders the scan frame

**Status.** Accepted by lead decision L-121. Part of #880. It extends AD-406 and AD-416.

**Decision.**
1. Add `--core-only` or `ARCHKEEL_CORE_ONLY=1`, off by default. Keep `--native-core` as stage 1.
   Refuse conflicting switches. Never fall back after a core-only request.
2. The core-only entry imports no `archkeel.ir` or `archkeel.check` module.
   The shell sends only the root and configuration location to `archkeel-core scan`.
   The core collects, builds the model and decides. The shell reads and renders its frame.
3. One typed shell table maps PASS to 0, FAIL to 1 and UNKNOWN to 2.
   A usage, collector, binary, process or frame refusal gives exit 2, never PASS.
   Core process exits 0 and 3 describe frame completeness, not the product verdict.
   This opt-in architecture gate differs from the legacy report, which returns 0 for FAIL.
4. `validate` gives the architecture verdict only. Other validation operations refuse by name.
   They remain available without the switch. No policy operation disappears silently.
5. `report` renders the verdict and its causes as text or JSON. It produces no full report.
   Full HTML, architecture.json, saved reports, projections and explore refuse by name.
   The remedy says to run without the switch. Do not port `Unsupported::Report` here.
6. Core-only `check` always refuses with the active check names and #1103.
   Each shipped check authenticates the lock and evaluates an authenticated expectation.
   Ratchets and selected changes live in those bytes, not in a disabling command option.
   Git and host ordering also run unconditionally. There is no verdict-only check form.
7. `collect` owns repository discovery and Git state. Derive HEAD and dirty in the core.
   Optional request provenance is checked, never trusted. A false clean claim refuses.
   Use the platform's fixed Git executable, not PATH. Missing Git refuses by name.
8. `Ruling::frame` remains the only frame maker. Typed evidence explains each FAIL.
   UNKNOWN names its gap and location when available. Unported rules name their missing kind.
   Refused collection does not parse an empty contract or report a false contract error.
9. One lookup finds the installed `_native` binary with its digest, or a checkout build.
   A broken installed binary never falls back to a checkout binary.

**Reason.** The milestone needs one complete architecture gate without a second verdict.
The merge gate and full report still need ports. A refusal is safer than an incomplete PASS.

**Rejected.** Replacing check with a live scan; empty full reports; and silent Python fallback.
Do not close #1095 or #1103. Stage 1 remains for the operations that core-only refuses.

**Limits.** The default, wheel packaging and Makefile switch belong to slice 5.
No proof in model or eval changes. No analyzer is removed. No rule kind is added.

**Tests.** `tests/test_cli_core_only.py` blocks imports in a subprocess.
Boundary tests cover process failures, frame validation, exit mapping, lookup and refusals.
Native tests cover Git state, refused collection and typed violation evidence.
