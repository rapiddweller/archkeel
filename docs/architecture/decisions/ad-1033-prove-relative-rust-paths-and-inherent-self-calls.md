# AD-1033 Prove relative Rust paths and inherent self calls

**Decision.** Resolve a relative module path when its first name has one
visible module declaration or explicit rooted import and the path reaches a
known local function. Resolve a plain `self.method(...)` call when both
methods share one proven inherent implementation for a local type and the
receiver kinds match.

**Reason.** Rust paths such as `reservation::request()` and
`crate::reservation::request()` can name the same declaration. A method
of the same inherent implementation can also have a source-backed target.
Explorer uses the declaration and call site as evidence.

**Limits.** The collector withholds proof when it sees shadowing, competing
bindings, or conditional declarations. Trait dispatch, general receiver
inference, and macro expansion remain open. The collector reads source
without running the crate or Cargo build scripts.

**Checks.** Compiler-backed fixtures cover relative and rooted paths,
shadowing, inherent methods, and competing trait methods. The inventory story
checks the relative path through the Explorer HTTP and MCP queries.
