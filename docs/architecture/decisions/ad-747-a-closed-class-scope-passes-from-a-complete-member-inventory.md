# AD-747 A closed class scope passes from a complete member inventory

**Status.** Accepted. Part of #880, closes #1532. Visible change: a closed scope of a class, an
interface or an enum over member kinds can PASS. Before, each closed scope without an unlisted
element was UNKNOWN ("closed scope completeness").

**Reason.** The core never read `MemberInventory.status`. No real-world showcase fixture could
reach PASS on its UML target: L-nest-realworld declares 41 closed class or interface scopes.
Release 4.0.1 passed such a scope from a complete direct-member inventory (AD-229).

**Decision.**

1. The core (`native/model/src/uml_inventory.rs`) passes a closed scope without an unlisted element
   only when all of these hold:
   - its owner is one symbol of the table (a class, an interface or an enum);
   - the scope lists no relationship kind, and each listed entity kind has a member inventory:
     `attribute` and `enum_literal` the attribute inventory, `method` the method inventory;
   - the owner has exactly one inventory of each such kind, and its status is `complete`;
   - each member of the inventory is an entity of the table whose parent is the owner.

   Any other case is UNKNOWN with a named cause that starts with `closed scope completeness:`. A
   partial inventory names the reason of the collector. The row still passes only with the scope
   proof of the run (AD-494). The core names no language: the collector decides the status.
2. A closed module, package or component scope stays UNKNOWN: no fact states a complete module
   inventory. A closed scope over relationships stays UNKNOWN: no fact states a complete site
   inventory.
3. The members of a TypeScript classifier are the members that `tsc` gives its type. The
   TypeScript collector states the inventory `complete` only when the body shows all of them:
   - the body has only static member names, no index signature, no duplicate attribute and at
     most one supported constructor (`members_complete`, as before);
   - the file is a TypeScript module (`.ts`, `.tsx`, `.mts`, `.cts`, `.d.ts` with `import` or
     `export`, or a module suffix). A script shares the global scope, where another file can
     merge an interface into its names. In a JavaScript file `tsc` reads `this.x = ...` as a
     member;
   - no namespace of the same name is in the file;
   - no other definition has the same qualified name (an interface and a class merge);
   - no file of the project has `N.prototype`, `N['prototype']`, `Object.f(N, ...)`,
     `Reflect.f(N, ...)`, `Object.f(this, ...)` inside the class, or `extends` with a base that is
     no name or member name. `N` is the name of the class. These forms add no type member, except
     the computed base, but they change the object at run time. The collector keeps them
     partial: stricter than the type, never weaker.

   A module augmentation (`declare module "./x"`) of a project file is a coverage gap of its file
   (#976). The run is then not complete, and no UML row passes. Each partial inventory names its
   cause in `reason`.
4. Python inventories stay `partial` (AD-518 rule 8). The row names the reason: "a base, a
   metaclass, a decorator or a write after the class body can add a member".
5. Rust inventories are `partial` (`native/rust/src/symbols.rs`: fields are not read; an impl
   block in another module or a macro can add a method). The row names that reason.
6. Dart: the collector writes a `complete` inventory (`native/dart/src/declarations/types.rs`) and
   sets it `partial` for an incomplete declaration. It states no symbol facts yet (#1533). When it
   does, rule 1 applies without a change in the core.

**Truth (TypeScript 5.9.3, `tsc --strict`).** A member that the type has: an index signature
(`c.extra()` compiles), a namespace merge (`Client.extra()`), a module augmentation, a merge of two
global script declarations, `this.extra = 1` in a JavaScript constructor (`checkJs`) and a mixin
base (`keyof Client` holds `'extra'`). No type member (TS2339): a class decorator that returns a
subclass, `Object.assign(Client.prototype, ...)`, `Object.assign(this, ...)`, and `declare global`
against a class of a module.

**Plants.** `tests/uml_closed_plants.py`, run by `tests/test_cli_core_uml_closed_members.py`. PASS:
a complete class over attributes and methods, a class over methods, an interface, an enum, a
decorated class. FAIL: an unlisted method. UNKNOWN: index signature, computed name, interface merge,
namespace merge (also dotted, also with an enum), module augmentation, global script merge,
prototype assign, prototype write, static `Object.defineProperty`, `Object.assign(this, ...)`,
mixin base, class expression, JavaScript `this.x`. Before the collector change, the core change
alone gave PASS for the namespace merge, the prototype and static writes, the instance spread and
the mixin base. Unit tests: `native/model/src/uml_inventory_tests.rs`.

**Effect.** L-nest-realworld (resolver inputs copied): 46 → 9 undecided UML assessments. 37 of the
41 closed scopes pass. `User`, `Article`, `Comment` and `Tag` stay UNKNOWN: each declares a
member with a computed symbol key (`[EntityName]?: ...`). H-uml-typescript: unchanged, 3
undecided; its two closed module scopes now name the cause.

**Rejected.** A run-time member definition that keeps every decorated class partial: NestJS and
MikroORM classes all have decorators, and `tsc` gives a decorated class the type of its body.
Keeping the 4.0.1 coverage proof per library (AD-229): the scope proof of the run holds the row.
