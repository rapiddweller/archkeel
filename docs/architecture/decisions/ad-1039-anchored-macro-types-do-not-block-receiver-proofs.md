# AD-1039 Anchored macro types do not block receiver proofs

**Decision.** In the Rust collector, `Builder::expand_methods` records a named
method from a `macro_rules!` definition in `macro_members` only when `foreign`
is true (`def.item_level.foreign_impl(...) || call.writes_impl`), matching the
rule for `$name` methods taken from call tokens. In `Index::cross_type` and
`routes::type_route`, an item-level macro call in the target file does not block
type resolution or complete publication routes when `binds_nothing` proves that
the macro expansion cannot write a `use`, `extern crate`, or `mod`.

**Reason.** Macros that declare a type and its inherent `impl` together
(`text_id!`, `closed!`, `text_type!`, `id_type!`, `section_facts!`) add methods
only to their own type (AD-383). Recording their fixed method names (`as_str`,
`new`, `as_text`, `index`, `from_index`) as unanchored macro members blocked
written receiver proofs across the workspace. Allowing `cross_type` and
`type_route` to use `binds_nothing` lets re-exported macro-declared types such
as `Profile` resolve their receiver type and publication route without creating
a module cycle between `modules.filled` and `modules.state`.

**Limits.** Macros whose expansion can write an `impl` for an arbitrary existing
type (`foreign == true`) or write imports at item level continue to hold back
receiver and route proofs.
