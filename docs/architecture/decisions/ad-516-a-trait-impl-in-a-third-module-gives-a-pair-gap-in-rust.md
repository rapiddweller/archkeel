# AD-516 A trait impl in a third module gives a pair gap in Rust

**Status.** Proposed. Part of #880. Closes the orphan class of #1004 and its row in #1075. It
extends AD-357.

**Problem.** An impl of a trait for a type runs wherever the types fit; no `use` names it. One
crate: `b.rs` holds `impl From<crate::a::Y> for crate::c::S`, `a.rs` calls `y.into()`, a rule says
`a` must not use `b`. Deleting `mod b;` fails `a` (E0277), yet the verdict was PASS with no gap.
The same holds for `S::from`, `?`, operators, `Deref`, `Display`, `for`, `Default`, `==`, `Drop`,
`AsRef`, `TryFrom`, `Index`, a blanket impl over closures and generic dispatch. The scan reads
no types.

**Rule (written before the code).**
1. An impl is *anchored* in module `b` when its self type is a struct, enum or union that the
   file of `b` defines, or its trait is a trait that the file of `b` defines. The self type is
   read after `&`; `Box<Local>`, `Vec<Local>`, arrays, tuples, qualified paths, type parameters
   and `dyn` types are never anchored by their parts. A trait argument never anchors.
2. A name that a block declares anchors only when the impl is not in an inline `mod`, no `use`
   is in any block around the impl, exactly one item of that name is in the blocks around it,
   and that item is a struct, enum or union. A trait of a block never anchors. Any other case is
   unresolved, and an unresolved path is not defined. Strict is allowed, weak is not.
3. An impl that is not anchored is an orphan of `b`. Each module that may reach it gets the pair
   gap `m -> b`, written as in AD-357; the host drops it when the contract allows the pair and
   no cycle closes (AD-418). A pair that an edge joins gets no gap.
4. May reach: each module of the crate of `b` and of each crate that depends on it.

**Proof of the bound.** Coherence gives an impl no scope: code of crate `K` runs an impl of crate
`X` only when `K` is `X` or `X` is in the Cargo closure of `K`. Any module of that set can hold a
value of the type without naming it. The scan has no type of a value, so no smaller set is
provable.

**Why the trait anchors but its arguments do not.** The strict form "only the self type anchors"
made 17 written impls in 4 modules of `native/` orphans, and more that macros make (extension
traits on `String`, `Option`, `Vec` in `fields.rs`, `readset.rs`, `pyrepr.rs`, `macros.rs`), which cannot move to the module of a foreign self type.
So an impl of a local trait on a foreign type stays anchored by its trait (form 4 below). The
review plants of a local trait argument (`Tg<Marker>`, `AsRef<L>`) are orphans: no clean cost.

**Open false PASS, not accepted (pinned plants; each is a true edge today).**
1. A value of a type that `b` defines, which `a` gets from another module, with the impl in `b`.
   13 forms are pinned: a method call, `Display`, `Drop`, `==`, `for`, `+`, `?`, `impl Trait`,
   `dyn`, a field, an alias with `Default`, a closure, `into()` into a sink of `c`.
2. An impl of a trait of `b` for a type of another module, reached through a generic bound, a
   supertrait, a `dyn` supertrait or a re-export of the trait (4 plants).
3. An impl that a macro of `b` generates (#1020), and a foreign trait that a glob brings in.

Amended by AD-806 (#1515, #1516): forms 1 and 2 and the glob form give the pair gap `a -> b` when `a`
reaches `b`, the module of a trait impl that runs code.

**Price (measured).** `make self-validate`: native 63/1/19, 124 pinned gaps, shell 22/0/0; no
pin moves. One orphan in a crate of `N` modules gives `N - 1` pair gaps plus the modules of
dependent crates, and `REQUIRES`, `NO-CYCLES` and the pair rule go UNKNOWN until the contract
allows every pair. With one component for each module the gap `c -> b` stays when `c` holds the
type, because `b -> c` closes a cycle: the cure is to move the impl to the module of its type.
The rule found one orphan in `native/`; the `From<PythonVersion> for String` of `pyminor.rs`
became a hand-written `Serialize`. The fixture matrix has no Rust row.

**Where.** `native/rust/src/orphan_impls.rs` (below `impl_edges.rs`); `scan_definitions.rs`
(`trait_impl`, `block_type`); `impl_globs.rs` (`once_gap`, `depends`).

**Mutations (each run).** No gap: all plants fail. Callers limited to the crate: the cross-crate
plant. Block items ignored: the block control. An unresolved path counts as defined: the alias
and glob plants. A trait argument anchors: the marker, `AsRef` and local-argument plants.

**Plants (53).** 10 fail first on `009b527de`: 9 plants and the forbidding contract. They give
UNKNOWN now. The allowing contract, the controls and the open forms give PASS before and after.
`tests/test_collector_false_pass_rust_orphan_impl.py`, `tests/rust_orphan_plants.py`.
