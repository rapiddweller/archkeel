# AD-896 The core uses one private channel for Rust and TypeScript workers

**Status.** Integration draft. It extends AD-881 and amends AD-406 for TypeScript.
No rule, gap or API pin is approved by this record.

**Reason.** The installed core links the TypeScript collector through `collect`.
AD-806 retains 1,152 pairs because the linked collector can run in the core process.
The same reason holds for the Rust link that AD-881 removes.

**Decision.**
1. `collect` selects the installed TypeScript worker beside the core. It uses the launch,
   cancellation and frame reader that it uses for Rust. The core does not link either worker.
2. The two worker binaries use `wire::worker::serve_v1`. The server owns the request limit,
   scan thread and reply frame. Each worker owns its request decoder and snapshot work bound.
   The frame grammar and the TypeScript public compressed reply do not change.
3. Every worker goes through the same build digest and store checks. Python and Dart keep their
   linked paths. Their profile selection does not change.
4. A wheel contains the core and both workers. The build records each digest and SBOM.
   The shell checks each digest before it starts the core. A missing or failed worker gives no
   positive architecture verdict.

**Rejected.** Do not use a TypeScript-only launcher. Do not give a public reply live producer
authority. Do not discharge a native pair from a return signature or change the rule.

**Limit.** The frame keeps the AD-881 size limit and the same check-to-start window.
The worker is a separate process, not a file or system-call sandbox.

**Checks.** `tests/test_collector_native_wheel.py` checks installed binary members, digests and
link inventories. `tests/test_cli_core_binary.py` checks damaged and absent workers.
`native/collect/src/lib_tests.rs` compares the private collection with the public TS reply.
