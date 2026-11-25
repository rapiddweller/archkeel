# AD-1093 the scan progress line names the scanned root

**Status.** Accepted. Part of #1963 (item 7). It changes the text of the progress line that issue #1621 added for scans over 3 seconds.

**Reason.** The progress line named the working folder (`Path.cwd().name` in `native_scan.exchange`). A scan with `--root other` printed the name of the folder of the shell. The user then could not tell which tree the run read.

**Decision.**
1. **The root names the line.** `scan_progress(root)` in `archkeel.cli.native_scan` writes `archkeel: scanning <name>, <s> s so far...`. `<name>` is the folder name of `root`. A root without a name (a filesystem root) uses its path.
2. **The caller passes the root.** `_exchange_scan` in `core_only.py` wraps the call of the core in `scan_progress(project.path)`. `exchange` runs the core only and writes no progress line.
3. **One public name.** `scan_progress` is public in the shell contract (`docs/architecture/target/shell-contract.json`), because `core_only` imports it.

**Rejected.**
- A `root` keyword on `exchange`. It changes the call of every test fake of `exchange` (about 30 fakes), and the progress is a property of the scan, not of the transport.
- The full path in the line. It makes the line long on a narrow terminal. The name is enough to tell two trees apart.
- Keeping `Path.cwd()` and adding a second line. Two lines for one scan add output that the user must read.

**Limit.**
- Two roots with the same folder name read the same. The line gives no path.
- The line appears only after `_PROGRESS_DELAY` (3 s). A quick scan writes nothing, as before.

**Tests.** `tests/test_cli_progress.py`: the line names `other` for root `tmp/other`; a filesystem root names `/`; a quick scan writes nothing (the existing tests). `tests/test_cli_shell_self_check.py` checks the shell contract with the new public name.
