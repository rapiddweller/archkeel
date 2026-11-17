# AD-735: The draft step has one outcome and runs after the core is found

Status: accepted (lead plan of 2026-11-17, #1451, Wave 3). Part of #880. Amends AD-638.

Before this record, the draft step of `validate` and `report` (AD-638) gave `Created`, a stop text or
`None`, and the shell told them apart by type. The draft wrote its files before the shell looked for
the core, so a run without a core wrote files and then refused without saying what it wrote. A
refusal of the core after a write also lost the block of written files.
`ARCHKEEL_NO_INIT=false` opted out, and each stop had the fix "run `archkeel --help`".

1. The draft step gives one `InitOutcome(state, created, message)` (`core_init.py`). The states are
   `not_first_run`, `system_found`, `created`, `opted_out`, `cannot_write` and `nothing_to_draft`.
   `InitOutcome.refusal()` gives the refusal kind and the fix of a stop, with one match arm for each
   state:
   - `opted_out`: `invalid_input`; "run `archkeel init` to write the draft, or run again without
     --no-init and ARCHKEEL_NO_INIT."
   - `cannot_write`: `io_error` (was `invalid_input`); "allow writing in the project folder, then
     run again."
   - `nothing_to_draft`: `invalid_input`; "write archkeel.toml and a contract by hand (the guide
     shows how), or name a configuration with --config PATH."
2. The shell finds and checks the core before the draft step. A run without a core writes no file.
3. A refusal after the draft wrote its files prints the block of written files first. In JSON it
   carries the `init` object.
4. The JSON of a stop has `init` with its `state`. The `init` object of a run that wrote files also
   has `state: created`.
5. `ARCHKEEL_NO_INIT` keeps the draft on for an empty value, `0`, `false`, `no` and `off` (any case).
   Each other value opts out, because writing is the step that must not happen by mistake.

Visible change: the three fix lines above, the kind `io_error` for a folder that cannot be written,
the `init.state` field, no files when the core is missing, the block of written files before a
later refusal, and `ARCHKEEL_NO_INIT=false` writes the draft.

Proof: `tests/test_cli_init_outcome.py`.

## One project root

Before, each step found its own root. `init` drafted in the current folder, while `validate`
without `--root` read the configuration at the top of the Git work tree. The configuration reason
looked in the current folder. `--write-baseline` wrote below the top of the work tree, while the
core read `--baseline` below the scan root, so a baseline written with `--root sub` could not be
read back. The Git ignore check of missing modules ran in the current folder.

6. One `ProjectRoot(path, mode)` (`core_binding.py`) names the root of a command: an explicit
   `--root` (`explicit`), else the top of the Git work tree at or above the current folder
   (`work_tree`), else the current folder (`current`). `init`, the draft step, the configuration
   reason, the baseline write, the Git ignore check and the scan request use it. The request sends
   the root with `discover_root` false only for an explicit root.
7. The draft step runs only when the project root is the top of a work tree, as before.

Visible change: `init` in a folder below the top of a work tree drafts at the top; a baseline
written with `--root sub` is written to `sub` and read back; the configuration reason names the
top of the work tree when the core looked there.

Proof: `tests/test_cli_project_root.py`.
