# AD-747 A closed class scope passes from a complete member inventory

**Status.** Accepted. Part of #880, closes #1532. Visible change: a closed scope of a class, an
interface or an enum over member kinds can PASS. Before, each closed scope without an unlisted
element was UNKNOWN ("closed scope completeness").

**Reason.** The core never read `MemberInventory.status`, so no real-world showcase fixture could
reach PASS on its UML target (L-nest-realworld has 41 closed class or interface scopes). Release
4.0.1 passed such a scope from a complete direct-member inventory (AD-229).

**Decision.**

1. The core (`native/model/src/uml_inventory.rs`) passes a closed scope without an unlisted element
   only when: its owner is one symbol of the table; the scope lists no relationship kind; each
   listed entity kind has exactly one member inventory of the owner (`attribute` and
   `enum_literal`: the attribute inventory; `method`: the method inventory); each is `complete`;
   and each member of each is an entity whose parent is the owner. Else it is UNKNOWN with a cause
   that starts with `closed scope completeness:`; a partial inventory names the reason of the
   collector. The row still needs the scope proof of the run (AD-494). The core names no language.
2. A closed module, package or component scope and a closed scope over relationships stay UNKNOWN:
   no fact states a complete module or site inventory.
3. The members of a TypeScript classifier are those that `tsc` gives its type. The collector
   states the inventory `complete` only when the body shows all of them: static member names, no
   index signature, no duplicate attribute, at most one supported constructor (as before); the
   file is a TypeScript module (a script shares the global scope, where another file can merge an
   interface into its names; in JavaScript `tsc` reads `this.x = ...` as a member); no namespace
   of the same name in the file; no other definition with the same qualified name. It also keeps
   these forms partial, stricter than the type: `N.prototype`, `N['prototype']`, `Object.f(N)`,
   `Reflect.f(N)` anywhere in the project, `Object.f(this)` inside the class, and `extends` with a
   base that is no name. A module augmentation of a project file is a coverage gap (#976), so the
   run is not complete and no UML row passes. Each partial inventory names its cause in `reason`.
4. Python inventories stay `partial` (AD-518 rule 8); the row names the reason "a base, a
   metaclass, a decorator or a write after the class body can add a member". Rust inventories are
   `partial` (fields are not read; an impl block elsewhere or a macro can add a method). Dart writes
   `complete` inventories but no symbol facts yet (#1533); rule 1 then applies unchanged.

**Truth (TypeScript 5.9.3, `tsc --strict`).** A type member: an index signature, a namespace merge,
a module augmentation, a merge of two global script declarations, `this.extra = 1` in a JavaScript
constructor (`checkJs`), a mixin base (`keyof Client` holds `'extra'`). No type member (TS2339): a
class decorator that returns a subclass, `Object.assign(Client.prototype, ...)`,
`Object.assign(this, ...)`, `declare global` against a class of a module.

**Plants.** `tests/uml_closed_plants.py` (`tests/test_cli_core_uml_closed_members.py`). PASS: a
class over attributes and methods, a class over methods, an interface, an enum, a decorated class.
FAIL: an unlisted method. UNKNOWN: index signature, computed name, interface merge, namespace merge
(also dotted, also on an enum), module augmentation, global script merge, prototype assign and
write, static `Object.defineProperty`, `Object.assign(this)`, mixin base, class expression,
JavaScript `this.x`. With the core change alone, the namespace merge, the prototype and static
writes, the instance spread and the mixin base gave PASS. Unit tests: `uml_inventory_tests.rs`.

**Effect.** L-nest-realworld (resolver inputs copied): 46 → 9 undecided UML assessments; 37 of 41
closed scopes pass. `User`, `Article`, `Comment` and `Tag` stay UNKNOWN: each declares a member
with a computed symbol key (`[EntityName]?: ...`). H-uml-typescript: 3 undecided, as before; its
closed module scopes now name the cause.

**Rejected.** Keeping each decorated class partial: NestJS and MikroORM classes all have decorators,
and `tsc` gives a decorated class the type of its body. The per-library coverage proof of 4.0.1
(AD-229): the scope proof of the run holds the row.
