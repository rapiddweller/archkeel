# AD-319 A collector process has a memory limit and a checked adapter version

**Decision.** The host bounds the memory of each collector it starts, and it checks the adapter
version of a collector from its own package. This closes the gaps of PR 4.1b-3 of issue #880.

1. `COLLECTOR_MEMORY_LIMIT_BYTES` in `analyzer/memory_limit.py` is 4 GiB. `ProcessCollector`
   has the field `memory_limit_bytes`. It applies to every collector, whatever its language.
2. Linux: after `Popen` and before the request is written, the host calls
   `resource.prlimit(pid, RLIMIT_AS, (limit, limit))`. A refused call is an `execution_error`.
   An existing lower limit is kept.
3. Windows: `windows_job.py` takes `--memory-limit-bytes=<n>`. The job sets
   `JOB_OBJECT_LIMIT_PROCESS_MEMORY` with `KILL_ON_JOB_CLOSE`. It limits committed memory.
4. macOS: no limit. `RLIMIT_AS` is not reliable there, so the collector runs without a memory
   limit. Time and output stay bounded.
5. A collector that exits after a failed allocation gives an `execution_error`. On Linux and
   Windows the text starts with "Collector exceeded its memory limit of N bytes (M MiB)." and
   keeps the exit status and stderr. The host finds the failure in stderr: `MemoryError`,
   "memory allocation of", "out of memory" or "Cannot allocate memory".
6. `observer_for` sets `pin_adapter_version` for a bundled collector. The reply must then report
   the installed version of `archkeel` as `adapter.version`. Another version is a
   `protocol_error` and the host fails closed. A collector from `collector_argv` has no pinned
   version. No wire field is new.
7. `native/typescript` reads at most 4 MiB from one file (`MAX_FILE_BYTES`). A larger file is
   not held in memory and gives a collection gap that names it. The file stays selected and has
   no file fact, so its rules are UNKNOWN. The Python collector has no such cap. A `tsconfig`
   is parsed by `serde_json`, whose depth limit of 128 gives "Cannot parse" and not a crash.
8. The reply checks moved from `process.py` to `reply_checks.py`. `process.py` is now below
   500 lines, and its entry left `tests/file_size_baseline.json`.

**Reason.** Time and output were bounded, memory was not. A hostile or huge source can make a
collector use all memory of the host. The process boundary is useful only when the host can also
bound the child. The version check closes the drift between host and binary (AD-317).

Measured on Linux (OrbStack, Python 3.11.18): the Python TypeScript collector on the React UI
corpus, 907 files, a 105 MB reply, 3 runs. Virtual size peak (`VmPeak`): 966 to 973 MiB. Resident
peak (`VmHWM`): 863 to 864 MiB. The 4 GiB limit is about four times the virtual peak. With
the limit, the same run gives 907 files. A 512 MiB limit gives the named `execution_error`. The
largest TypeScript source of that corpus has 92 KB, 2 % of the 4 MiB file cap.

**Rejected.**
- `RLIMIT_RSS`. Linux ignores it. `RLIMIT_DATA` misses `mmap` memory.
- cgroups. They need privileges and a container, and they are not portable.
- A setting in `archkeel.toml`. No user need exists. The field can be set in code.
- A message that names the limit for each non-zero exit. Only an allocation failure names it.

**Limit.**
- `RLIMIT_AS` counts address space, so a library with a large mapping can reach it early.
  Python threads reserve stack space too. The margin of four covers the measured peak.
- Windows counts committed memory per process. The check runs in the Windows safety job only.
- A collector on macOS has no memory limit.
- A collector that dies by another cause, for example a signal from the kernel, shows no name.

**Check.** `tests/test_collection_process.py` runs a child that allocates over a 256 MiB limit,
reads the limit in the child, tests the Windows job flags and arguments, and the exit text on
each platform. It tests a reply with another adapter version and the observer pin.
`tests/test_collector_native_typescript.py` tests the pin with the binary. `cargo test` has a
file of exactly the limit, a file one byte over, and a config nested 200 000 levels deep.
