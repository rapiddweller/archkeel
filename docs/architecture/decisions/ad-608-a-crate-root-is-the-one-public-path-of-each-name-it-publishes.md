# AD-608: A crate root is the one public path of each name it publishes

Status: accepted (owner order). Part of #880. It amends AD-604.

## Context
AD-604 derived the `public` lists of the self-contract from the uses of today, so
`NATIVE-INTERFACE-BOUNDARY` found no violation by construction. 18 uses from other crates reached a
name of `facts` by a deeper module path (`archkeel_facts::sections::GapFact`) although the root of
`facts` publishes the same name (`pub use sections::GapFact`). One name then has two public paths.

## Decision
1. Architecture rule of the self-contract: a crate root is the one public path of each name that it
   publishes. Another crate uses such a name through the root. A name that the root does not
   publish keeps its module path, which is then its one public path.
2. The rule is a statement of `public`, checked by `NATIVE-INTERFACE-BOUNDARY`. A component that
   owns a crate root lists the root entry (`native.archkeel_facts:GapFact`) of each name that the
   root publishes, and never also a deeper entry of the same name. A use by a deeper path then has
   no public hop and fails. `tests/test_native_contract_rules.py` holds the shape: no component
   lists one name at its root and at a deeper module.
3. A method call reaches the module of its `impl` block, so it cannot take the root path (#953).
   Its route now carries the publications of its type: the type in the module of the block, each
   name of the crate root that publishes the type, and the definition (`Publications` in
   `native/rust/src/routes.rs`). A method of a type that the root publishes passes through the
   root entry. A root leaf whose route the scan does not prove makes the route not complete.
4. A route of a type skips the macro check of AD-604: a macro call in item place cannot add a
   second type of the name, because it would collide with the `use` or the definition (E0255,
   E0428). A route of a type that ends at another item is not complete.
5. A name that a macro call in item place defines ends its route (AD-604 kept it open). The proof:
   no `use` leaf, glob or `extern crate` of the file binds the name, and each call in item place is
   a call by plain name of the one crate-wide `macro_rules!` of that name. The call tokens write no
   `use` or `extern`, and the expansion writes none at item level (the group after `=>`, with each
   `$( .. )` repetition) and calls only such macros there. A `use` in a block, an `impl` or an inline
   `mod` of the expansion binds no name of the module. Such a call adds a definition, never a
   re-export. Without the proof, `GapFact` of `facts.sections` (`section_facts!`) had an open route,
   so a deep use of it was a gap and not a FAIL.

## Result
The 18 deep uses and the 20 paths through their bindings fail (38 rows, all into `facts`). The
code then uses the root path, and the rule holds for every crate.

## Intent review of the surfaces
AD-604 took each `public` list from the uses of today, so it froze them. Each list was reviewed
against the responsibility of its component. A name that belongs inside is removed, and each of its
uses fails (80 rows). Three causes, one line each in #1291:
- A test hook (`plant` of the Rust and TypeScript collectors) exists only with the test feature
  `dump`. It is no task of the text and input parts that hold it (5 names).
- A re-export for nobody: the crate root publishes the crate to other crates, and no production
  code of another crate uses this name. The part offered it to the root only (70 names).
- Request decoding (`decode`, `hex`, `INFLATE_LIMIT`, `ReplyBytes`, `InsideJson`, `insides` of
  `dual_run`) is the task of `core-requests`, not of `core-frame`, which builds a frame (6 names).
Each other name is kept: it is a type, a vocabulary or a step that the responsibility of its component
offers. 71 more root re-exports have no user in another crate; a sibling part uses the same entry,
so no rule fails them.

## Amendment: a crate root publishes only listed names
The intent review kept 71 root re-exports that no other crate uses, because a sibling part uses the
same entry. The rule now sees the publication itself. The Rust collector states `published_as` on a
`pub use` at module level of the root of a library crate (`*` for a glob; not for `pub(crate)` or a
binary root). `NATIVE-INTERFACE-BOUNDARY` fails such a record when its component does not list
`module:name` (or the whole module): "publication outside the public interface". A published glob
holds the rule. A re-export used only inside its own crate is then no public name. The 70 entries
that the review removed as "re-export for nobody" come back: the root publication is the one place
of that cause, so each dead re-export gives one row and not two. A glob of a child module by one name
(`use child::*;`) gave no edge before; it now names the module.

## Limits
- The root publications come from the scan. A root leaf that a macro writes is not read.
- A procedural macro is not read (as in AD-604): it can only add a FAIL where the truth is PASS.
- A name that the root does not publish is not moved to the root by this rule.
- A `pub` item that the root defines (not a re-export) is not judged as a publication yet.
