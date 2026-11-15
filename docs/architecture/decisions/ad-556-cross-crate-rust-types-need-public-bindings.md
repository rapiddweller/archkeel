# AD-556 Cross-crate Rust types need public bindings

**Status.** Proposed. Part of #880.

AD-544 follows explicit imports and re-exports to place a written receiver type. An import
visible only inside its crate cannot export a type to another crate. A type reached across a
crate boundary must be public, and each re-export must be `pub`, not `pub(crate)`, `pub(super)`
or `pub(in ...)`. An uncertain binding keeps the gap.

A direct path through the modules of another crate names its type when each module name is the
only declaration of its name in its file and no module is conditional. The one declaration wins
over each glob, and a macro cannot give the name again: `rustc` refuses a second item of the
name. A private module on the path is an error of `rustc`, not another type, so the resolver
does not need to prove the visibility of the modules. A relative `pub use` path starts at the
module of the `use`, not at the crate root. A crate with a `[lib] name` keeps each gap: the name
in source can be that crate. In the crate of the path, a restricted `use` leaf is also a step:
a path that cannot see it is an error of `rustc`.

The receiver plants compile the public re-export, the direct public-module path and the relative
re-export in a file module with `rustc`.
