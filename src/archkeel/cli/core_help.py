# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The help of the command line: one text for the tool and one for each command (AD-432).

Each text names the options of its command, the output rule, the one exit table and two examples.
The exit table comes from `core_exit`, so the help and the header cannot disagree.
"""

from __future__ import annotations

from typing import Final

from .core_arguments import RELEASE, RELEASED
from .core_exit import table_lines
from .core_frame import CoreCommand as Command

_OUTPUT: Final = """\
Output: in a terminal, a short text summary (verdict first, then violations, then the causes
that hold rules, each group with a count). `--json` prints one JSON object, also in a terminal.
Without a terminal (a pipe or a file) the default is JSON; `--text` asks for text there.
`--all` lists every item instead of the first few. `--verbose` adds the core binary and digest."""
_COMMON: Final = """\
  --root PATH     Repository root. Default: the Git work tree of the current directory.
  --config PATH   Configuration file below the root. Default: archkeel.toml.
  --json          Print JSON also in a terminal.
  --text          Print text also without a terminal.
  --all           List every violation, rule and gap, not the first few of each group.
  --verbose       Also print the core binary, its engine and its code digest."""
_VALIDATE: Final = """\
usage: archkeel validate [--root PATH] [--config PATH] [--baseline FILE | --write-baseline FILE]
                         [--json | --text] [--all] [--verbose]

Check the contract of a repository. The Rust core decides each run; this command prints it.

options:
{common}
  --baseline FILE        Compare with this baseline file below the root, in both directions: a
                         new gap or violation, and an accepted item that is gone, exit 1.
  --write-baseline FILE  Write the baseline of this run to this file below the root.
                         A baseline records UNKNOWN items; it does not decide them.

{output}

exit codes:
{table}
  With --baseline, the core decides the code: a difference exits 1 and an accepted UNKNOWN
  exits 2. A scan that could not run exits 1 with --baseline and 2 without it, because exit 2
  with a baseline means that every UNKNOWN is accepted.

examples:
  archkeel validate
  archkeel validate --baseline archkeel-baseline.json --text
"""
_REPORT: Final = """\
usage: archkeel report [--root PATH] [--config PATH] [--output FILE [--format html|json]]
                       [--topology] [--json | --text] [--all] [--verbose]

Print the frame of the core as a report. With --output, write one file and print one line.

options:
{common}
  --output FILE   Write the report to this file. No file is written by default.
  --format FORMAT With --output: html (default, a page with the architecture) or json.
  --topology      Add the bounded topology to the printed result (the JSON field `topology`,
                  and a count line in text). The HTML page always draws the architecture.

{output}
With --output and no --json or --text, the command prints one line: the verdict and the file.

exit codes (the same as validate):
{table}

examples:
  archkeel report --output report.html
  archkeel report --json --topology
"""
_SKILL: Final = """\
usage: archkeel skill install {{claude,codex}} [--root PATH] [--json]

Install the instructions of the agent skill into a repository, for Claude Code or Codex.

exit codes:
  0  installed
  2  not installed (a wrong argument or a path that cannot be written)

examples:
  archkeel skill install claude
  archkeel skill install codex --root ../service
"""
_INIT: Final = """\
usage: archkeel init [--root PATH] [--json]

Draft the files of a first contract below the root: archkeel.toml, a contract of open decisions
(every decision is a TODO) and its provenance page. For a Python project with one top-level
package. It replaces no file and starts no scan.

exit codes:
  0  drafted
  2  nothing drafted (a file exists, or the layout is not one that init can read)

examples:
  archkeel init
  archkeel init --root ../service
"""
_NOT_YET: Final = """\
usage: archkeel {command}

`{command}` is not available on this development line. {where}
Nothing runs; the exit code is 2. Use `archkeel validate` or `archkeel report`.
"""
_TOOL: Final = """\
usage: archkeel <command> [options]

ArchKeel checks the architecture of a repository against its contract. The Rust core decides
each run; this command line prints the result.

commands:
  validate   Check the contract: PASS, FAIL or UNKNOWN. `archkeel validate --help` lists options.
  report     Print the same result as a report; with --output, write an HTML page.
  init       Draft archkeel.toml and a first contract for a Python project.
  skill      Install the agent skill: archkeel skill install {{claude,codex}}

not available yet (exit 2): check (use release {release}); explore, guide, story, view, studio
(no release has them).

{output}

exit codes:
{table}

Run `archkeel <command> --help` for the options and examples of one command.
  --version       Print the version.
"""


def help_for(command: Command | None) -> str:
    """The help of one command, or of the tool for `None`."""
    table = "\n".join(table_lines())
    fields = {"common": _COMMON, "output": _OUTPUT, "table": table, "release": RELEASE}
    if command is Command.VALIDATE:
        return _VALIDATE.format(**fields)
    if command is Command.REPORT:
        return _REPORT.format(**fields)
    if command is Command.SKILL:
        return _SKILL.format()
    if command is Command.INIT:
        return _INIT
    if command is None:
        return _TOOL.format(**fields)
    where = (
        f"Release {RELEASE} has it."
        if command in RELEASED
        else f"No release has it; release {RELEASE} is older."
    )
    return _NOT_YET.format(command=command, where=where)
