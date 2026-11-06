# AD-308 Finite per-run collector limit for explore and Studio

`explore` and `studio` accept `--collector-output-limit-bytes BYTES`. The value must be a positive
integer no greater than the active interpreter's `sys.maxsize // 16`. The
default remains 64 MiB. `explore` passes the value to its collector. Studio
passes it to its Explore child and stores it in the session scope. A second start
reuses a session only when the value matches. A previously saved explicit scope
with a null limit means the old default; records without this field remain
readable, but their scope is unknown and they are not reused.

The collector keeps its bounded streaming read, tree cleanup, protocol checks and decompression
bound of 16 times the configured limit. A larger value can use much more memory after decompression
and parsing. There is no unlimited mode, truncation, or automatic retry with a larger value.

This per-run option serves contract-free Explore and Studio, which do not read `[scan]` config.
Their failure guidance names this flag; configured scans keep the existing AD-224 setting and
guidance to raise `[scan].collector_output_limit_bytes`. The absent and explicit default limits
share one effective Studio scope. Older scope records remain readable as unknown and are not reused.

**Rejected.** Raise the default for every project, remove the output bound, or omit facts to fit.

**Checks.** `tests/test_explore.py` checks a too-small and a sufficient finite value, plus the public
TypeScript demo. `tests/test_studio.py` checks forwarding. `tests/test_studio_session.py` checks
scope mismatch and safe handling of older scope records.
