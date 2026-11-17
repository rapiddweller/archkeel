# AD-731: Under a baseline, only a verdict exits 2

Status: accepted (lead plan of 2026-11-17, #1451). Part of #880. Amends AD-546.

With `--baseline`, exit 2 means "every UNKNOWN is accepted", and CI treats it as green (AD-546).
Before this record, a run that gave no verdict also exited 2: a missing core binary, a core crash or
timeout, a core refusal with exit 2, a frame that did not bind to the request, a frame that could not
be decoded, an auto-init stop and a baseline file that could not be written. Each was a
false green. The core had the same fault: `--baseline FILE --write-baseline OTHER` on a run with a
refused part gave the state `not_written` with exit 2.

1. The shell has one `Outcome` (`core_exit.py`): `verdict`, `collect_refused`, `command_refused`
   and `delivery_failed`. One function, `exit_for(outcome, frame, baseline)`, gives every exit code.
   A verdict exits with the code of the frame: the baseline part of the core, else the run status.
   Each other outcome exits 1 when the command line names `--baseline`, and 2 when it does not.
   A collector refusal already did so. Without a baseline, no exit code changes.
2. "Names `--baseline`" is a property of the command line, not of the command. A refused argument
   (`--baseline` with a parent path, or with the path of `--write-baseline`) and the refusal of
   `check --baseline` also exit 1.
3. `--write-baseline` on a run with a refused part is a delivery outcome. The shell keeps the frame
   and prints it, and adds the refusal kind `baseline_not_written`. It is no longer a fault of the
   core (`core_error`) that drops the frame.
4. The JSON result of a run keeps `refusal` as the first refusal and adds `refusals`, which lists
   each refusal in order. A command that gave no frame has one refusal and keeps its old fields. A collector refusal and a report file that could not be written are both in
   the list. The text prints a `Problem:` line for each, so the text and the JSON name the same
   refusals.
5. The header reason comes from the outcome and from the baseline state, with one match arm for each
   state. A delivery failure names the file only when it changed the exit code; else the verdict
   reason stays and the `Problem:` line names the file.
6. The core has one `BaselineState` enum (`baseline.rs`). Each state gives its word and its exit
   code, so the two cannot disagree. `NotWritten` exits 1 when the request also compares with a file,
   and keeps the exit code of the run status when it only writes. The request is one `Input`:
   `Compare`, `Write` or `CompareAndWrite`. The frame keys `state` and `exit_code` and the committed
   frame schema do not change.

Visible change: under `--baseline`, a refusal and a file that was not written exit 1, not 2. The
JSON result of a run with a refusal has the new field `refusals`. `--write-baseline` on a refused run prints the
frame and the refusal `baseline_not_written`.

Proof: `tests/test_cli_exit_outcome.py` (each refusal under a baseline, the write failure on a
drifting run, `not_written` with the frame, both refusals kept) and the core test
`a_refused_run_that_compares_and_writes_exits_1_because_exit_2_means_all_accepted`.
