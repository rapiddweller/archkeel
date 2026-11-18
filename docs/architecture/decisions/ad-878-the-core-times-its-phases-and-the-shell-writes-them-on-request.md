# AD-878 The core times its phases and the shell writes them on request

Status. Accepted. Issue #659. It replaces the Python-engine mechanism of AD-267; the file and the
rule "nothing changes without the flag" stay.

`archkeel validate --timings FILE` and `archkeel report --timings FILE` write one JSON file with
the wall-clock seconds of the phases of the core. No other output changes.

- **How.** The scan request has the field `timings` (default false). The binary entry owns the
  monotonic clock and passes elapsed durations to the scan and collector through a function.
  Only a request for timings reads the clock. When asked, the core writes one line to standard error after the
  frame: the protocol `archkeel-core-timings-1` with `clock`, `unit`, `phases` and `core_seconds`, or
  the line `{"protocol":"archkeel-core-timings-1","refused":true}`. The shell checks the line and writes
  it to `FILE`. The frame, standard output, the verdict and the pages are byte-identical with and
  without the flag. The core writes no file.
- **Phases.** `prepare` (configuration, Git state, survey, inside contracts, provenance), `collect`
  (the linked collector), `validate` (the store validates the reply once), `evaluate` (rules, topology,
  explaining rows), `render` (the frame bytes of each scan, with the page when one is asked for) and
  `join` (a system run only: the frames of the parts become one frame; zero otherwise). A system run
  sums its parts and adds `join`.
- **`core_seconds`.** The time inside the core after the request is decoded to the end of the frame, not the
  time of the CLI (interpreter start, Git state, read and print of the frame). `core_seconds` minus
  the sum of the phases is the rest that no phase measures.
- **No encode or decode phase.** The collector hands its typed reply to the core in the same process
  (AD-406), so the issue's "encode/validate" and "decode/validate" are `validate` here.
- **What the shell checks.** One line. Whether the scan was refused comes from the frame (a refused
  collection, also in one part of a system run), never from this line, and the line must agree: a
  refused frame has the line `refused`, any other frame the complete line. The complete line has exactly
  the protocol fields and the six phases in order; each number is a finite number of seconds, 0 or more
  (an integer too large for a float is refused), and the phases sum to at most `core_seconds`. A
  missing, second, broken or disagreeing line is an error (exit 2).
- **No file for a refused scan.** The core never gives the sum of the parts that did run.
- **The option creates a new file and never replaces one.** `FILE` must not exist, also not as a link or
  a hard link; the shell refuses it when it reads the options, before the scan and before any other
  output. `--timings` and `--output` (or `--write-baseline`) must not name one new file. The shell
  writes all bytes to a temporary file in the folder and links it under the name: the link fails when
  the name exists or appears during the run, so a late file or link is never replaced and no partial
  file is visible. The shell does not list the inputs of the run: a file that does not exist cannot be
  one. `--output` and `--write-baseline` keep their meaning.
- **Use in a benchmark or a nightly job.** Give each run a new name, for example
  `--timings "timings-$(date +%s).json"` or `--timings "$(mktemp -d)/timings.json"`. A script that
  keeps the last file removes the old one first. The seconds depend on the machine; they are no snapshot.

- **Nightly reference.** One test of the existing nightly scans a pinned public project (SymPy, a fixed
  commit) several times with `--timings`, keeps one file for each run and a table of the spread, and sets
  no limit (`tests/timing_reference/README.md`, `tools/phase_timings.py`). Each run writes into a new
  folder of its own and deletes nothing; a cached source is used only when its bytes are the pinned
  commit (`tools/fixture_source.verify_checkout`).

**Rejected.** A `timings` key in the frame (frame schema and system join change, and a snapshot would
hold seconds); a file written by the core (it is read-only); an environment switch or a global
recorder; a list of all files that the run read (it is never complete, for example outside-code reads).
The binary entry needs `Instant` for the monotonic clock. Core logic must not access the system clock.
The system-use test pins this one access and plants clock accesses in the scan and engine path.
The collector adds `scan_with_clock` for that function. The existing `scan` remains available without timing.

**Not in this decision.** Phase limits in a gate stay in #659: the spread of many nights comes first.

**Check.** `native/core/src/scan_timings_tests.rs` and `native/core/src/phases_tests.rs` (line,
sum, frame equal with and without `timings`); `tests/test_cli_timings.py`, `test_cli_timings_targets.py`
(existing file, link, hard link and late file are not replaced and every project byte is unchanged;
refused scan and refused part write no file) and `test_cli_timings_protocol.py` (the whole protocol,
agreement with the frame, `10**400`, `write_new`).
