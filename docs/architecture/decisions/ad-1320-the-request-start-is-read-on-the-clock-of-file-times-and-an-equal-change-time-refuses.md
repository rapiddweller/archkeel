# AD-1320: The request start is read on the clock of file times, and an equal change time refuses

Status: accepted. Closes #2204. Amends AD-438.

## Why

The shell refuses a nested contract whose `st_ctime` is after the start of the request (AD-438). The core reads a nested
contract itself, so a file that changed after the start has a digest that matches its new bytes. Only the change time can
tell it from an earlier write, also when the write sets `mtime` back (`os.utime`).

Before kernel 6.13 Linux stamps `st_ctime` with a coarse clock (one tick, 1 to 4 ms). The shell took the start with
`time_ns()` and compared with `>`. A write that follows the start by less than one tick got a time at or below the start
and passed. Measured on Linux (`CLOCK_REALTIME_COARSE`, 10,000 runs each): the check missed the write 10,000 times
when the write came 20 us after the start, and 4,329 times when it came 2 ms after. This is the intermittent exit 0 of
`test_a_nested_only_change_refuses_the_frame[backdated-write]` (the test is right). Kernels with multigrain timestamps
and macOS stamp a fine time, so they did not show it.

## Decision

1. On Linux the start of a request waits for two ticks of `CLOCK_REALTIME_COARSE` and is the time of the second
   (`request_started_ns`). Elsewhere it is `time_ns()`. #2212 shows why the first version failed: it took the coarse
   time at once. A file that the same run wrote a moment before (the drafted contract documents) has the same tick as
   the start, so `ctime >= start` refused an unchanged file. A write before and a write after the start in one tick
   have the same coarse time. No comparison can tell them apart. The wait removes the tick they share.
2. A nested contract with `st_ctime >= start` is refused (`>` before AD-1320). A write before the call has a time below
   the start. A write after the call has the time of the second tick or later, so it is at or above the start.
3. Two ticks, not one, because a kernel with multigrain timestamps (6.13 and later) stamps a write with a fine time,
   while the coarse clock can lag its tick by some time under load. One tick still refused a write before the call in
   some runs under load (measured). Two ticks need a lag of less than one tick.
4. The wait is bounded by 0.1 s. A clock that does not move gives the last time: a refusal, never a missed write.
5. The digest check and the identity, `mtime` and `ctime` comparison across the read are unchanged.

## Counter-examples

Simulation with `CLOCK_REALTIME_COARSE` on Linux (10,000 runs per cell; a write before the start and a write after it,
each at a gap of 20 us and of 2 ms; ticks of 1 ms and 4 ms). "Spurious" is a refusal of a write before the start.
"Missed" is a write after the start that binds.

| Variant | Spurious | Missed |
|---|---:|---:|
| `time_ns()` start, `>` (before AD-1320) | 0 | up to 10,000 |
| coarse start, `>=` (AD-1320 first version) | up to 9,948 | 0 |
| coarse start plus one tick, `>=` | 0 | up to 9,946 |
| coarse start, `>` | 0 | up to 9,949 |
| wait for the next tick, `>=` | 0 | 0 |

The wait for two ticks (the decision) on the real Linux clock under load (12 busy processes on 4 cores), 10 runs of
1,000 writes before and after the start: 0 failures. The wait for one tick failed in 2 of 5 runs.
Unit tests: `tests/test_cli_core_binding_started.py` (equal times, the tick boundary with a fake clock, a frozen clock).

## Not done

- A file system with a coarser time (FAT, 2 s) can refuse a file that was written seconds before the start. It never
  accepts a changed file.
