# AD-776: A relative --config is read from the current folder, and each run names its root

Status: accepted (lead order of 2026-11-17, #1608, P0). Part of #880. Amends AD-606 and AD-735.

Before, `cd sub && archkeel validate --config archkeel.toml` used the top of the Git work tree as
the root and read `archkeel.toml` there: the run checked another project, and nothing in the output
named the root or the file. A user could read a PASS of the wrong project. This is treated as a
false PASS.

1. `ProjectRoot.of(root, config)` (`core_binding.py`) decides the root and the configuration of a
   run, in this order:
   - `--root DIR`: the root is `DIR`, and a relative `--config` is below it (as if the command ran
     in `DIR`).
   - `--config PATH`: the path is read from the current folder. A file that is not there, or a
     folder, is refused with the path that was tried (`invalid_input`). The root is the folder of
     the file, unless its `[scan]` states `root`: `"."` or a path of `..` parts, seen from the
     folder of the file. A system document (`.json`) names the top of its work tree, because its
     part paths are relative to that.
   - No flag: the nearest `archkeel.toml` at or above the current folder, inside the work tree,
     names the project in the same way. Without one, the root is the top of the work tree (the
     draft step of AD-638 writes there), else the current folder.
2. The core accepts `[scan] root` only in that form and changes no setting by it
   (`native/collect/src/config.rs`). `native/archkeel.toml`, `docs/architecture/shell.toml` and
   `docs/architecture/browser.toml` state their root.
3. The first text line names the root and the configuration as paths from the current folder:
   `validate: PASS -> exit 0 (all 26 rules pass) · root . · config docs/architecture/shell.toml`.
   A refusal after the root is known names them too. The JSON result has `root` and `config` as
   absolute paths after `exit_code`.
4. `init` keeps its root: an explicit `--root`, else the top of the work tree (AD-735).

Visible change: a relative `--config` without `--root` is read from the current folder; a missing
one is refused with its path; a run in a folder with its own `archkeel.toml` scans that folder; the
header and the JSON name the root and the configuration; the new optional key `[scan] root`.

Proof: `tests/test_cli_config_root.py` (the reproduction of #1608, a missing file, the nearest
configuration, the top, `--root` alone and with `--config`, a stated root, a system document, and
the header and JSON names). Four of its cases fail on the shell before this record.
