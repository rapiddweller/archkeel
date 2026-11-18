# AD-878 The core times its phases and the shell writes them on request

Status. Accepted. Issue #659. It replaces the Python-engine mechanism of AD-267; the file and the
rule "nothing changes without the flag" stay.

`archkeel validate --timings FILE` and `archkeel report --timings FILE` write one JSON file with
the wall-clock seconds of the phases of the core. No other output changes.

- **How.** The scan request has the field `timings` (default false). The core times the phases with
  the monotonic clock (`Instant`) and, when the request asks, writes one line to standard error after
  the frame: `{"protocol":"archkeel-core-timings-1","clock":"monotonic","unit":"seconds","phases":{...},"core_seconds":N}`.
  The shell reads the last line of standard error and writes it to `FILE` with the atomic writer of
  the report. The frame on standard output, the text, the JSON result, the pages and the verdict are
  byte-identical with and without the flag. The core writes no file.
- **Phases.** `prepare` (configuration, Git state, repository survey, inside contracts, provenance
  documents), `collect` (the linked collector), `validate` (the store validates the reply once),
  `evaluate` (rules, topology, explaining rows) and `render` (the frame bytes, and the page when one
  is asked for). `core_seconds` is the whole scan in the core, so the rest that no phase measures is
  `core_seconds` minus the sum. A system run sums the phases of its parts and adds the join to
  `render`.
- **No encode or decode phase.** The collector hands its typed reply to the core in the same process
  (AD-406). The wire encode, decode and second validation of the Python engine do not exist on this
  path, so the issue's "encode/validate" and "decode/validate" are `validate` here.
- **No file for a refused scan.** A scan that the core refuses, or that fails before the phases,
  gives no timings line, so `FILE` is not written. The seconds depend on the machine and are not
  snapshots.

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
