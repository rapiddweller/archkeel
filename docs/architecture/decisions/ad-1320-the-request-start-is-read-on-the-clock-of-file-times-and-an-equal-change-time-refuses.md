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

1. The start of a request is read on the clock that stamps file times: `CLOCK_REALTIME_COARSE` on Linux, `time_ns()`
   elsewhere (`request_started_ns`).
2. A nested contract with `st_ctime >= start` is refused (`>` before). A write in the tick of the start has the same
   coarse time as the start, so equality must refuse.
3. The digest check and the identity, `mtime` and `ctime` comparison across the read are unchanged.

## Counter-examples

- A write 20 us or 2 ms after the start: refused (0 of 10,000 missed, measured).
- A file written 5 ms before the start: bound (0 of 2,000 refused).
- A change time equal to the start: refused. One above the file time: bound (`tests/test_cli_core_binding_started.py`).
- A refusal is the safe direction: the message says to run again. A file that was written in the very tick of the start
  is refused once, and binds on the next run.

## Not done

- A file system with a coarser time (FAT, 2 s) can refuse a file that was written seconds before the start. It never
  accepts a changed file.
