# AD-772 A path through a re-exported module names the module at its end

**Status.** Accepted (owner order: fix the false PASS). Part of #880, closes #1517. It extends the module resolver of AD-335 and keeps the publication route of AD-604.

**Reason.** The module resolver went down a path only through child modules and aliases of `extern crate self`. It stopped at the first other name and gave an edge to the module before that name. rustc resolves the path through the name when it is a `use` of a module, a crate root or a glob. In each form below, `a` calls `g` of `b`, `cargo check` accepts the plant, and `NO-A-TO-B` gave PASS on main `157dc8851`:
- `pub use crate::b as other;` or `pub use crate::b;` in `c`, then `crate::c::other::g()`;
- `pub use crate::name as other;` with `pub extern crate self as name;`, or `pub use crate as other;`, then `crate::c::other::b::g()`, also through a second re-export, a re-export in another module, and a `use crate::c::other;` leaf;
- `pub use crate::*;` in `c`, then `crate::c::b::g()` or `crate::c::name::b::g()`;
- `pub use base as other;`, `pub use base;`, `pub use base::hidden as other;` or `pub use base::*;` in `c` for a crate `base` of the workspace, then a path into `base::hidden`;
- `use base::*; hidden::g()`: a glob of a crate of the workspace was read as a glob of an external crate.

**Decision.**
1. A name after a module that is no child module of it, with more names after it, is a member of that module. The resolver reads it by the rules of a bare name in that module (`bare`): one `use` leaf at module level is followed, a glob of the module is followed, and a name that the module declares more than once is UNKNOWN.
2. When the member names a module (an empty last name, as for a glob), the walk goes on from that module. When it names an item (a type, a trait, an enum), the edge stays at the module before it, with its publication route (AD-604). The facade semantics of an item re-export do not change.
3. A `use` leaf whose path starts at a crate of the workspace goes on from the root of that crate. A registry name of a crate of the workspace is UNKNOWN (AD-704).
4. A glob whose path starts at a crate of the workspace brings in the names of the module that it names in that crate, as a glob of a module of the own crate does.
5. A name that the module does not declare is UNKNOWN when a macro call at module level of its file may bind it (`filled::binds_nothing` fails). `binds_nothing` now accepts a leaf `use name;` of the one name of the call: it re-exports the `macro_rules!` of the crate, since no `extern crate` can bring in a macro (the proof already requires that) and a crate is no macro.
6. The steps of the walk call each other, so they stay in one file (`modules/walk.rs`). The entry points of the resolver stay in `modules.rs`, so that the method calls of the other modules keep their edge to it.

**Why it is sound.** A followed route is the route of rustc: each step is the one declaration of its name. A step that the scan cannot prove (two declarations, a glob that a macro may fill, a macro call that may write a `use`, more than 8 hops, a registry name of a crate of the workspace) is UNKNOWN with a gap of the module of the path. No step removes an edge that the old resolver gave, except when the old edge stopped before the module that rustc resolves.

**Price.** On the frozen public Serde workspace, the gaps go from 4439 to 4518 and the rule rows stay the same (0 PASS, 1 FAIL, 3 UNKNOWN). 78 new gaps are paths such as `crate::de::X::Y` in `serde`, whose root writes `pub use` items by `crate_root!()`; the old resolver gave an edge to the root there. 3 gaps are generic parameters (`S::Ok`) in a module with `pub use serde::*;`: the scan does not know generic parameters. The native self-check stays 92 PASS, 0 gaps. itoa stays 0/0/4, 33 gaps.

**Rejected.**
- Keep the module before the name and mark the route incomplete: the module rules do not read the route, so the false PASS stays.
- Follow an item re-export to the module of its definition: it changes the facade semantics of AD-604 for every `crate::c::Type::new()`.
- Read a qualified member through the extern prelude: rustc does not, and only a path that does not compile could reach it.

**Tests.** `tests/test_collector_false_pass_rust_root_reexports.py`: 14 forms FAIL, a route that a macro writes and an alias chain of 12 hops are UNKNOWN, a re-exported enum gives no module edge. `cargo check` accepts each plant.
