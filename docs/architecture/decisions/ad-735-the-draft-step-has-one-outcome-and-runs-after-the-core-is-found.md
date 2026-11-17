# AD-735: The draft step has one outcome and runs after the core is found

Status: accepted (lead plan of 2026-11-17, #1451, Wave 3). Part of #880. Amends AD-638.

Before, the draft step of `validate` and `report` gave `Created`, a stop text or `None`. It wrote
files before the shell looked for the core, and a later refusal lost the list of written files.
`ARCHKEEL_NO_INIT=false` opted out, and each stop had the fix "run `archkeel --help`". Each step
found its own root: `init` drafted in the current folder, `--write-baseline` wrote below the top of
the work tree while the core read `--baseline` below the scan root. The shell chose text or JSON in
three places, and the JSON results had different heads.

1. The draft step gives one `InitOutcome(state, created, message)` (`core_init.py`): `not_first_run`,
   `system_found`, `created`, `opted_out`, `cannot_write` or `nothing_to_draft`.
   `InitOutcome.refusal()` gives the kind and the fix of a stop, one match arm for each state:
   `opted_out` is `invalid_input` ("run `archkeel init` to write the draft, or run again without
   --no-init and ARCHKEEL_NO_INIT."), `cannot_write` is `io_error` ("allow writing in the project
   folder, then run again."), `nothing_to_draft` is `invalid_input` ("write archkeel.toml and a
   contract by hand (the guide shows how), or name a configuration with --config PATH.").
2. The shell finds and checks the core before the draft step. A refusal after a write prints the
   written files first; in JSON it carries `init`. A stop has `init: {"state": ...}`.
3. `ARCHKEEL_NO_INIT` keeps the draft on for an empty value, `0`, `false`, `no` and `off` (any case).
   Each other value opts out: writing is the step that must not happen by mistake.
4. One `ProjectRoot(path, mode)` (`core_binding.py`) is the root of a command: an explicit `--root`
   (`explicit`), else the top of the Git work tree above the current folder (`work_tree`), else the
   current folder (`current`). `init`, the draft step, the configuration reason, the baseline write,
   the Git ignore check and the scan request use it. The draft step still runs only at the top of a
   work tree.
5. `output_mode(argv)` (`core_arguments.py`) gives one `OutputMode` (`json`, `text`, `summary`) for
   the result and each refusal. A flag decides; else `init` and `--output` print text, and each
   other command prints JSON when its output is not a terminal.
6. `envelope(command, outcome, status, exit_code)` (`core_exit.py`) is the head of every JSON result:
   run, refusal, `init` and `skill`. `outcome` is new: `verdict`, `collect_refused`,
   `command_refused`, `delivery_failed` or `completed` (`init`, `skill`; exit 0 by `exit_for`).
   `status` is `null` without a verdict, and `command` is `null` when no command is named. Each
   field that a result had before keeps its value.
7. The parts that the collector refuses by name are one `_RefusedPart` (`core_words.py`), read
   from the refusal message in one place. A test reads `native/collect/src` and pins the set. The
   exit codes of the core are one `CoreExit` (`core_json.py`). The typed core refusal
   `parse_work_limit` is its own refusal kind (was `core_error`) with the fix "the file is larger or
   deeper than the scan reads; split it, or leave it out of the scan roots."

Visible change: the fix lines and the kind `io_error` above; no files when the core is missing; the
written files before a later refusal; `ARCHKEEL_NO_INIT=false` writes the draft; `init` below the
top of a work tree drafts at the top; a baseline written with `--root sub` is read back; the
configuration reason names the top of the work tree when the core looked there; the head fields
`outcome`, `command` (refusals) and `status` (`init`, `skill`); a refusal of `init` or of
`report --output` in a pipe without a flag prints text, as its result does; the kind
`parse_work_limit` and its fix.

Proof: `tests/test_cli_init_outcome.py`, `test_cli_project_root.py`, `test_cli_output_envelope.py`,
`test_cli_refused_part.py`.
For item 6 the text of 22 command lines is byte-identical before and after, and their JSON is equal
without the new head fields.
