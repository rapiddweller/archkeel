# AD-262 Configurable collector timeout

**Decision.** An optional positive integer `scan.collector_timeout_seconds` replaces
the fixed 300-second collector deadline for report, validate and historical check.
Absent means 300. The parser rejects booleans, non-integers, zero, negatives and values
above `threading.TIMEOUT_MAX`. `init --collector-timeout-seconds` uses and persists the
value, as AD-224 does for the output limit. The timeout diagnostic names the key.

**Reason.** A large repository can need more than 300 seconds to collect. The output
limit already has a configured path (AD-224), and the deadline should follow it: the
CLI injects a finite bound and Core keeps its policy. A longer deadline costs wall-clock
time only. It removes no source facts and grants no evidence; a timeout still exits 2
without a complete observation.

**Rejected.**
- An environment variable: it lives outside the repository, so a check on another
  machine could use a different deadline. The config must travel with the repository.
- A CLI flag on report only: check would then bind a deadline that the accepted config
  does not record.
- An unlimited or a larger fixed default: an unbounded wait hides a hung collector, and
  a larger default changes every project.

**Check.**
- `tests/test_collector_timeout.py` covers: the parser and schema reject 0, -1, true,
  false, 1.5, a string, a list and values above `TIMEOUT_MAX`; the default of 300 and a
  configured value reach `ProcessCollector` for every language; `init` persists the key
  and rejects invalid values without writing files; report and validate pass the
  configured value to the observer.
- `tests/test_configured_collector_check.py` proves historical check passes the accepted
  timeout to the observer.
- `tests/test_source_trust_boundary.py` pins the diagnostic that names
  `collector_timeout_seconds` for a real timeout.
