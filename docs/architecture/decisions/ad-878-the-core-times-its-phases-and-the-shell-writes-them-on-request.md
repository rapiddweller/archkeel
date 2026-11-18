# AD-878 The core times its phases and the shell writes them on request

Status. Accepted. Issue #659. It replaces the Python-engine mechanism of AD-267; the file and the
rule "nothing changes without the flag" stay.

`archkeel validate --timings FILE` and `archkeel report --timings FILE` write one JSON file with
the wall-clock seconds of the phases of the core. No other output changes.

- **How.** The scan request has the field `timings` (default false). The core times the phases with
  the monotonic clock (`Instant`). When the request asks, the core writes exactly one line to standard
  error after the frame: `{"protocol":"archkeel-core-timings-1","clock":"monotonic","unit":"seconds","phases":{...},"core_seconds":N}`,
  or `{"protocol":"archkeel-core-timings-1","refused":true}` for a scan that was refused in whole or in
  a part. The shell reads that one line, checks all of it and writes it to `FILE` with the atomic
  writer of the report. The frame on standard output, the text, the JSON result, the pages and the
  verdict are byte-identical with and without the flag. The core writes no file.
- **Phases.** `prepare` (configuration, Git state, survey, inside contracts, provenance documents),
  `collect` (the linked collector), `validate` (the store validates the reply once), `evaluate`
  (rules, topology, explaining rows), `render` (the frame bytes of each scan, and the page when one
  is asked for) and `join` (a system run only: the frames of the parts become one frame; zero for
  one configuration). A system run sums the phases of its parts and adds `join`.
- **`core_seconds`.** The time inside the core from the read request to the end of the frame. It is
  not the time of the CLI: the start of the interpreter, the read of the Git state, and the read and
  print of the frame come on top. `core_seconds` minus the sum of the phases is the rest that no phase
  measures.
- **No encode or decode phase.** The collector hands its typed reply to the core in the same process
  (AD-406). The wire encode, decode and second validation of the Python engine do not exist on this
  path, so the issue's "encode/validate" and "decode/validate" are `validate` here.
- **What the shell checks.** One line, no more and no less. The protocol, the fields and the phase
  order are exactly as above. Each number is a finite number of seconds, 0 or more, and the phases
  sum to at most `core_seconds` (with the rounding of six decimals). A missing line, a second line or
  a broken line is an error (exit 2): a successful run that was asked for its timings must give them.
- **No file for a refused scan.** A scan that the core refuses, in whole or in one part of a system run,
  has the line `refused`: the shell writes no timings file and keeps an old file as it is. The core
  never gives the sum of the parts that did run.
- **Targets are checked before the first write.** `--output`, `--timings` and `--write-baseline` must
  not name the same file as one another, nor a file that the run read: the configuration, the system
  document and the configuration of each part, a contract file, `--baseline`, `--part-of`, or a source
  file that holds evidence. A link or another name of such a file counts (the path is resolved, and the
  device and inode are compared). The refusal names each pair, writes no file at all and exits as a file
  that was not written (AD-731). The seconds depend on the machine and are not snapshots.

**Rejected.**
- A `timings` key in the frame: it changes the frame schema and the system join, and a snapshot would
  hold seconds.
- A file written by the core: the core is read-only by design; the shell writes the files.
- An environment switch or a global recorder: hidden state.

**Not in this decision.** Phase budgets in the PR gate and the nightly run on a pinned public project
stay in #659. A budget needs the spread of several runners first.

**Check.**
- `native/core/src/frame_parts.rs` (module `tests`): the line is one JSON document with the five
  phases in order; the phases of parts are summed.
- `native/core/src/scan_timings_tests.rs`: a scan with `timings` has a frame equal to the frame
  without it, and the phases are positive and sum to at most `core_seconds`.
- `tests/test_cli_timings.py`: `--timings` writes the file, stdout is identical with and without it, and a
  refused scan writes no file.
- `tests/test_cli_timings_targets.py`: no target replaces another target or an input (also through a link),
  a system run with a refused part writes no file and keeps the old one, and a complete system run names
  `join` apart.
- `tests/test_cli_timings_protocol.py`: the whole protocol of the line, and a run that asked and got no line.
