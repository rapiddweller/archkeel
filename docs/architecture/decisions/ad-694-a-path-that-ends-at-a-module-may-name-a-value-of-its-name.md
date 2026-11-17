# AD-694 A path that ends at a module may name a value of its name

**Status.** Accepted (owner order: a false PASS is fixed before anything else). Part of #880. It
closes #1405 and amends AD-604.

**Reason.** A module shares the type namespace with each type, but not the value namespace. So a
root can declare `pub mod reply;` and `pub fn reply() {}`, and `use base::reply; reply();` calls the
function. The Rust collector resolved such a path to the module only, so these two rules gave a
wrong PASS (rustc plants):
- a `forbidden_dependency` with `target_symbol: "reply"`;
- an `interface_boundary` whose `public` list names only the module.

A second cause was older. A path into another crate of the workspace that the index could not
read became an import of the whole crate root with no name, not a gap.

**Decision.**
1. A path of a value, or a `use` leaf, that ends at a child module is a gap when the parent module
   may hold a value of the same name. That is the case when the file declares the name more than
   once, or when a glob or a macro at module level of the parent can add such a value. A glob path
   names a module or an enum only, so it keeps its edge.
2. A path into another crate of the workspace that the index cannot read is a gap with its
   reason, as the same path inside one crate is. A declared dependency without an index stays a
   whole-crate import.
3. In `native/`, the Rust collector root had this form (`mod reply` and `pub fn reply`). The
   function is now `encoded_reply`. The drawn edge `rs-entry -> rs-reply` and its `requires` entry
   existed only because of the false module edge, so both are removed.

**Why it is sound.** Each path that can name the value is a gap or a named import; no path writes
the module alone while it may name the value. A gap holds every rule that reads the edges of its
module (AD-634).

**Measured.** Native self-check: 89 PASS, 4 FAIL, 0 UNKNOWN, the same as before. The first form put
the check into the shared resolver. That made glob resolutions of the derive check a gap, and its
helper made a module cycle; both were found by the gates and fixed.

**Tests.** `tests/test_collector_false_pass_rust_module_and_item.py`: 5 plants that rustc accepts.
On main `f6d1ed543`, the first two give PASS for both rules.
