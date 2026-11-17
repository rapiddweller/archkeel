# AD-826: Text headers use absolute paths across drives

## Decision

Use absolute paths in a text header when the project and current folder are on different drives.
Keep relative paths when the operating system can compute them.

## Reason

Windows cannot compute a relative path between two drives.
The text command must not refuse a valid project on another drive.

## Alternative

Changing the current folder before a command hides the failure from users.

## Check

`tests/test_cli_windows_root.py` checks the absolute path fallback.
The installed-wheel smoke test runs the command on Windows.
