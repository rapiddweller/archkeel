# AD-103 Baseline and amendment paths are relative to --root

Resolve baseline/amendment reads and writes against `--root`, including absolute paths and symlinks.
Escapes exit two. From outside root, reject a relative spelling when its cwd target exists inside
root but its root-relative target is missing. Existing root-relative files win; there is no cwd
fallback.

This supersedes outside-root baseline comparison. Report/check output paths remain cwd-relative;
`check --baseline` names a commit. Proof: [test_cli.py](../../../tests/test_cli.py).
