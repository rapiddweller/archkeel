# AD-305 Studio starts one scope per root

**Status.** Accepted for issue #848. Amends AD-290.

**Decision.**
- Use the already pinned `filelock` package for a cross-platform per-root lock; ship it as a
  runtime dependency because the installed CLI needs the same lock. Scope the dependency to
  `archkeel.cli.launcher`.
- Keep one Studio session per canonical root. Persist its language, source paths, namespace,
  tsconfig and selected chat agent beside the existing process state. Reuse only an exact scope match.
- An older state without scope is UNKNOWN. Tell the user to stop that server before starting; do
  not assume its scope and do not launch a second Explore process.
- Hold a per-root OS file lock from the start state check until the HTTP serving loop begins. Stop
  first verifies the HTTP server, marks its state as stopping, then holds the same lock until the
  server removes its state after workspace cleanup. If stop exceeds its 15-second wait, retain that
  marker and refuse new scans while the marked process remains alive. An unmarked stale state is
  never trusted by PID alone. PID reuse can make an old marked state appear live; after verifying
  that no Studio or Explore process for the root remains, the user may remove the reported state
  file manually. Wait at most 60 seconds for the session lock; on timeout, report that nothing was
  started or stopped. A stable lock file is not removed while other processes may be waiting on it.
- Keep the root-keyed cache and existing CLI options. A different scope requires `--stop` first.

**Rejected.** Put scope in the cache key (would allow several Studio servers per root); trust
unknown legacy state; kill and replace a mismatched server automatically (could disrupt a user).

**Limits.** The lock coordinates ArchKeel CLI starts/stops sharing the same cache folder. It does
not coordinate manually launched server processes or separate cache roots. Long Explore runs may
outlast the wait; retrying later preserves the one-session invariant.

**Checks.** `tests/test_studio_session.py` covers scope and agent mismatch, malformed legacy scope
as UNKNOWN, readiness serialization, concurrent starts and bounded start/stop waits.
`make demo-studio` exercises the visible mismatch/stop path with bounded client and server cleanup.
