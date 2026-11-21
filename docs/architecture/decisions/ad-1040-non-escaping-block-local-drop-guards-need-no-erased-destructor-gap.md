# AD-1040 Non-escaping block-local Drop guards need no erased destructor gap

**Decision.** In the Rust collector (`scan::local_drop::non_escaping`), an
`impl Drop for Local` inside a synchronous function body clears `may_drop` when
the block proves that no instance of `Local` can escape that block:
1. `Local` is declared once as a non-generic nominal `struct`, `enum`, or
   `union` directly in the same block with inert attributes only, and no other
   `impl`, `use`, `static`, `macro`, or item in the block can shadow or expose
   it.
2. Every construction of `Local` is a direct `let <binding> = Local(...)`
   statement in that block, and every other mention of `<binding>` in the block
   is a top-level `drop(<binding>);` (or `std::mem::drop` / `core::mem::drop`)
   statement.
3. No `unsafe` block, `async` block/function, closure, return expression, or
   non-silent macro mentions `Local` or any of its bindings, and when bare
   `drop` is called, the file does not shadow `drop`.

**Reason.** Stack-only RAII drop guards such as `Restore` in
`native/snapshot/src/work.rs::bounded` can never leave their enclosing stack
frame. Marking their module as a global `drop_home` added 530 erased-destructor
pair gaps across unrelated workspace modules (AD-866, AD-1008). Proving
block-local non-escape keeps every escaping counterexample (`Box<dyn Any>`,
static storage, `async fn`, shadowed `drop`, `impl Trait`, closures) fail-closed
while removing false destructor gaps.

**Limits.** Only direct top-level `let` bindings and `drop(...)` calls in the
same synchronous function block are proved; any other use of `Local` or its
bindings falls back to `may_drop = true`.
