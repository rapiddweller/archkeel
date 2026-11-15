# AD-556 Cross-crate Rust types need public bindings

**Status.** Proposed. Part of #880.

AD-544 follows explicit imports and re-exports to place a written receiver type. An import
visible only inside its crate cannot export a type to another crate. A type reached across a
crate boundary must be public, and each re-export must be `pub`, not `pub(crate)`, `pub(super)`
or `pub(in ...)`. An uncertain binding keeps the gap.

Until the resolver proves the visibility of every module on a direct cross-crate path, it
accepts only a type or re-export at the crate root. A public re-export can still expose a public
type defined in a private module. The direct path through a public module remains a gap: this
is a deliberate limit, not evidence that the module is private.

The receiver plants compile both the public re-export and the direct public-module path with
`rustc`; the latter keeps its gap. The positive cross-crate path-call proof is not part of this
decision and remains fail-first.
