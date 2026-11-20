# AD-881 The core runs the Rust collector as a sibling process

**Status.** Draft for review. Epic #880. It amends AD-406 (point 2: the Rust collector is no
longer linked into the core) and AD-436 (point 1: the wheel carries two binaries). No merge.

**Decision.**
1. `archkeel-collect` has no dependency on `archkeel-rust-collector`. The core starts the
   executable `archkeel-rust-collector` that lies beside `archkeel-core`, with the argument
   `--core-worker-v1`. The start clears the environment. Nothing in the scanned project
   selects the program.
2. The request is one line on standard input, 1 MiB at most. The reply is one frame on standard
   output: four bytes of length (big endian) and JSON. A frame has 1 GiB at most, and a reader
   checks the length before it reads the body. Neither side reserves the stated length.
3. The worker exits when standard input closes, so a dead or cancelled core does not leave a scan.
4. The wire crate owns the frame. Its public interface adds three names:
   `worker:RUST_WORKER_V1`, `worker:write_rust_v1`, `worker:read_rust_v1`. The frame types are
   private. The frame carries what the public record encoding omits: the profile limits, the
   scope premise and the dispatch flag of each gap. A reply with a reason code, an owned file or
   standard-library facts is refused, because the Rust collector sets none of them.
5. The core gives the reply to the same `ingest_typed` as before. `Producer::Trusted` still needs
   the code digest of the core build (AD-406 point 5), so a worker of another build is not trusted.
6. A missing worker, a failed start, a wrong frame and a non-zero exit are a refusal (exit 2)
   that names the worker path or the reason. They are never a verdict.
7. The wheel carries `archkeel-core` and `archkeel-rust-collector`, each with its `.sha256` and its
   SBOM. The shell checks both digests before it starts the core. `make core` builds both packages.

**Reason.** `NATIVE-NO-CORE-TO-RUST` was UNKNOWN. The core could reach the Rust collector through
`collect` in its own process, and 744 core-to-Rust pairs had no proof of non-use. Without the
crate edge no such pair exists, so the rule has a scope proof from the Cargo graph. The edge
is not hidden by an exception: with the edge restored, the rule is UNKNOWN again.

**Measured** (same installed engine, tree of main `cef0d6f3a` against this draft). Rules: 81 PASS and
11 UNKNOWN before; 82 PASS, 0 FAIL and 10 UNKNOWN after. Only `NATIVE-NO-CORE-TO-RUST` changed.
Pair gaps: 22,597 before, 21,852 after (809 gone, 64 new). Plants: a Cargo edge or a use from
core to the Rust collector gives FAIL; the old `collect` edge gives UNKNOWN; removing any one of
the three wire names, or using an unlisted public name, gives `NATIVE-INTERFACE-BOUNDARY` FAIL.

**Rejected.** A `Facts` in the public wire encoding with the private fields: it would give a
public reply live authority (the reason of the omission). A frame limit of 128 MiB: a frame is 9
to 16 times the Rust source (6.8 MB gives 59 MiB, the `std` crate gives 86 MiB), and the whole
Rust `library` tree (54 MB of source) gave more than 128 MiB, which the linked collector accepted.

**Limits.**
- The 1 GiB limit gives a peak of the worker and the core together. The old path had one process.
- `NATIVE-INTERFACE-BOUNDARY` stays UNKNOWN, as on main.
- The 64 new pair gaps (new modules with trait impls) are not in `native/expected-gaps.json`,
  and 809 pinned gaps are gone. The pins are not changed in this draft.
- The CI core cache stores both binaries. The release check verifies both wheel members and their digests.
- A change between the digest check and the start of the worker stays open, as for the core (AD-432).
