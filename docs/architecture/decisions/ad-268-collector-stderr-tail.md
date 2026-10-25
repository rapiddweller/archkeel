# AD-268 Keep the end of collector stderr, never fail on its size

**Decision.** `ProcessCollector` reads collector stderr into a buffer that keeps only the
last `stderr_limit_bytes` (64 KiB). Stderr size never fails a run. A collector that exits
with a nonzero code returns an `execution_error` that names the exit code and the last 2,000
characters of stderr. Stdout keeps its hard limit (AD-224), because a stdout overflow means the
answer is incomplete.

**Reason.** Before this change, more than 64 KiB on stderr raised an output-limit error.
The run then reported "Collector output exceeded its 65536 byte limit" for two cases: a
collector with a long but harmless log, and a collector that crashed with a long
traceback. The first case failed a valid scan. The second case hid the real exception,
because the code read the limit error before it checked the exit code. Only the end of a
stderr stream explains a crash, so the end is the part to keep.

**Rejected.**
- A larger fixed limit: a long trace still fails at the new size and the real error
  stays hidden.
- Dropping stderr: a failed run would then give no cause.
- Keeping the first 64 KiB: a traceback ends with the exception, and the end is what
  the reader needs.

**Check.**
- `tests/test_collection_process.py`: a collector writes 200,000 bytes to stderr and still
  returns a valid answer; a collector exits 3 after 50,000 noise lines and the message
  starts with `Collector exited 3:`, ends with the real exception and is shorter than 2,100 characters.
- Both tests fail on the code before this change.
