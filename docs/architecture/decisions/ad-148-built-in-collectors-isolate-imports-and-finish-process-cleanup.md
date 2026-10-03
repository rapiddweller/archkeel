# AD-148 Built-in collectors isolate imports and finish process cleanup

The default Python and Dart collectors use Python isolated mode (`-I`). A scanned
repository or inherited `PYTHONPATH` must not replace collector or stdlib modules.
Collectors resolve from the installed distribution, including editable installs.
Custom collector argv remains an explicit caller choice.
The Windows job starter also uses isolated mode before importing its helper code.

On POSIX, each collector owns a process group. Clean that group after every
exchange, including interruption, before trusting its exit status or payload. Descendants can survive a
valid response, invalid JSON, snapshot mismatch or nonzero exit. Timeout cleanup
alone does not cover those paths.

Acceptance tests exercise public CLI calls with package and stdlib shadows, then
check descendant liveness after successful, failed and interrupted responses. Windows process
cleanup follows the existing platform path and needs native CI proof.
