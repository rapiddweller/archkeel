# AD-1039 Anchored macro types do not block receiver proofs

**Decision.** In the Rust collector, `Builder::expand_methods` records a named
method from a `macro_rules!` definition in `macro_members` only when `foreign`
is true (`def.item_level.foreign_impl(...) || call.writes_impl`), matching the
rule for `$name` methods taken from call tokens. In `Index::cross_type`, an
item-level macro call in the target file does not block type resolution when
`binds_nothing` proves that the macro expansion cannot write a `use`,
`extern crate`, or `mod`. In `routes::type_route`, when a file has no written
declaration or `use` of the target name, `macro_type_here` completes the route
only when `defined_here` holds and every module-level macro call proves via
`macro_items::published` that it can declare that name only as a nominal type
(`struct`, `enum`, `trait`), with at least one call witnessing the name.

**Reason.** Macros that declare a type and its inherent `impl` together
(`text_id!`, `closed!`, `text_type!`, `id_type!`, `section_facts!`) add methods
only to their own type (AD-383). Recording their fixed method names (`as_str`,
`new`, `as_text`, `index`, `from_index`) as unanchored macro members blocked
written receiver proofs across the workspace. Allowing `cross_type` to use
`binds_nothing` and `type_route` to prove macro-defined nominal types lets
re-exported macro-declared types such as `Profile` and `section_facts!` enums
resolve their receiver type and publication route without accepting type
aliases or multi-`cfg` bindings, and without creating a module cycle between
`modules.filled` and `modules.state`.

**Limits.** Macros whose expansion can write an `impl` for an arbitrary existing
type (`foreign == true`) or write imports at item level continue to hold back
receiver and route proofs.
