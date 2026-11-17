# AD-822: A TypeScript draft lists its scan roots, without ArchKeel's own outputs

Status: accepted (lead order of 2026-11-17, #1754, P1). Part of #880. Amends AD-638.

The draft of a TypeScript project wrote `roots = ["."]`. The README quick start then writes
`archkeel report --output report.html` into the project. The page holds script text, so the next
scan reads it as a code form that the TypeScript profile does not read (#1635), and every rule of
the run stays UNKNOWN although no code changed.

1. The draft of a TypeScript project lists its roots: each folder of the project folder and each
   code file beside them (the files that its `root` component owns), as they are at the time of
   the draft. It never lists `.git`, the installed-package folders (`node_modules`,
   `jspm_packages`, `bower_components`, which the collector walks only as far as an import reaches
   them) and ArchKeel's own outputs: `report.html`, the path of the README, and `test-artifacts/`.
   A folder of build output (`dist`, `build`) stays a root: a name does not prove that a file is
   generated (AD-488).
2. An entry made after the draft, such as the page of `archkeel report --output`, lies outside the
   roots and changes no verdict. An import of such a file is a named gap, never a PASS. To scan a
   new top-level entry, add it to `roots`.

Why not the other way (lead option 2: `report --output` without a path writes into a place that
the draft excludes): the configuration has no exclude key, and any place below the project folder
lies under the root `.`. A default path would also not help a user who names a path of their own.
Excluding a page by an ArchKeel marker in its text was rejected too: a marker can be written into
any page, so it could hide the scripts of a real page (a false PASS).

Visible change: the drafted `roots` of a TypeScript project list the entries of its folder instead
of `.`; the quick start gives the same verdict before and after its report page. On graphql-js
16.15.0 and full-stack-fastapi-template 0.12.0 every rule keeps its status; gaps about a data file
or a top-level page become gaps about a file outside the scan roots (the outside guard, #1712).

Proof: `tests/test_cli_quick_start.py` (validate, report, validate on a fresh TypeScript project;
the draft lists no ArchKeel output).
