# AD-862 Rust and Dart runs state the compiler basis of their proofs

Status. Accepted. Issue #1779. It amends AD-608, AD-774 and AD-796.

Two collectors rest proofs on "the compiler accepts the code". The Rust route proofs (AD-608) use
compile errors: a macro in item place cannot add a second type of one name, because that
collides with the `use` or the definition (E0255, E0428). The Dart resolver (AD-796) lets a
declaration of a library hide an import of its name. It binds a name through an unprefixed
import of a project library, because two non-platform libraries that export one used name are a
compile error. No run said so.

Each run now states the basis through the collector premise of AD-540 (`Facts::scope_premise`):

- Rust: "the Rust code compiles (rustc accepts it)". The Cargo.lock premise of AD-774 follows it
  when that one applies, in the same text.
- Dart: "the Dart code is valid (dart analyze accepts it)".

The text line `Assumption:`, the frame key `premise` and the report show it. The system frame
joins the premises of its parts (`premise` in `native/core/src/system.rs`). No file other than
the two `reply.rs` files changes in the core.

## Rejected

- Contract premises (AD-764, "PASS assuming"). The contract declares them with an id, a
  rationale and a provenance. This basis is stated by the collector for every run.

Undo: remove the premise in the two `reply.rs` files. The Rust Cargo.lock premise stays.
