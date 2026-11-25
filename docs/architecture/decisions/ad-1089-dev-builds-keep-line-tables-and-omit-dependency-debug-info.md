# AD-1089: Dev builds keep line tables and omit dependency debug info

Dev builds use disk space in each worktree. The `shell` and `dump` test builds use
separate target directories. The `parity` profile inherits the dev profile.

1. The native workspace and the rustc facts driver keep line tables for their own
   code. They omit debug information for dependencies.
2. Release and wheel builds keep their existing profile.
3. Full debug information supports inspecting variables and types in a debugger.
   Developers who need it can override the dev profile locally.

We reject full debug information by default because it makes each target directory
larger. We reject removing all debug information because line tables support
source locations in backtraces.

On macOS, clean `make native-test` runs on the same commit used 3.0 GiB and
234.40 seconds before this change, and 2.1 GiB and 183.78 seconds after it.
Both runs disabled incremental compilation and used four build jobs and test threads.
These are single measurements, not a build-time benchmark.
