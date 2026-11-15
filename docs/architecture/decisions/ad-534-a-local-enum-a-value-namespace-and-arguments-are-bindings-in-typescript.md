# AD-534: A local enum, a value namespace and `arguments` are bindings in TypeScript

Status: accepted. Part of #880. It amends AD-340 (the script bindings) and AD-460 (script globals).

## Context
The collector bound a declarator, a function, a generator and a class. It did not bind an `enum`, a
`namespace` with a value, or the `arguments` of a function. A read of such a name looked like a read of
a script global and gave the gap "Script global X has no unique unconditional publication". On
graphql-js v16.15.0 this made 90 of 487 gaps (`BreakingChangeType` 37, `TypeKind` 32,
`DangerousChangeType` 15, `arguments` 6). 4.0.1 never read a free name, so it had no such gap.

## Decision
`bind_kinds.rs` answers the question for the two places that bind: the walk (`walk.rs`, for the
sites) and the script tree (`script_bind.rs`, for the writes). A binding is real only where the run
time creates one.

1. **`enum` and `const enum`.** Bound in the scope around the declaration, like a class. A
   `const enum` is erased, but its name is still a lexical binding of the source.
2. **`namespace` and `module`.** Bound when the body has a member that exists at run time: a
   variable, function, class, enum that is not const, a statement, or a nested namespace with such a
   member. A body of types only (interface, type alias, const enum, import alias) binds nothing, and
   a read of the name stays a read of a global. `namespace A.B {}` binds `A`. A statement that the
   list does not know counts as no value: the gap stays.
3. **`declare`.** `declare enum`, `declare namespace` and anything under a `declare` bind nothing:
   they type a value that lives elsewhere. This keeps the behaviour before.
4. **Merge.** An enum and a namespace of one name are both bindings of that name.
5. **`arguments`.** Bound in each function that is no arrow: declaration, expression, generator,
   method, getter, setter. An arrow function reads the one of the function around it. At the top of a
   module nothing binds it, so it stays free. A parameter or local named `arguments` is the one
   binding, not a second one.
6. **Scope.** An `enum` in a block or a function is bound there and not outside.

7. **Only in a module.** Rules 1 to 4 apply only to a file that the collector classifies as a module
   (top-level `import` or `export`, or a module format hint). In a script file an `enum`, a
   `const enum` and a `namespace` are global and merge with the declarations of the same name in
   other files. `E.Other` can then name a member that another file supplies, and `tsc` emits that
   lookup at run time (also for a `const enum` under `isolatedModules`). So a script file keeps the
   behaviour before: the read stays a read of a global, with its gap. Review plants of #1202:
   `enum-merge`, `namespace-merge`, `namespace-merge-root`, `const-enum-isolated`, each with a
   control in a module that is bound.
8. **`arguments` is the exception.** It is function-scoped and never global, so it binds in both
   kinds of files.

The change hides no dependency.

## Price
- graphql-js 487 gaps become 397. The verdict stays UNKNOWN: the 393 standard globals and 4
  `process` remain. hono 805 become 799, zod 956 become 863. No row of `fixtures/matrix.json` moves.
- `script_bindings` of the root frame lists an enum and a value namespace of a module file.
- `arguments` costs one entry for each function in the name index.

## Limits
- A `var arguments` in the body of a function counts as a second binding of the name. The name stays
  bound; a proof that needs exactly one binding does not hold.
- A value member that lies more than 8 namespaces deep does not count: the name stays free. The
  limit keeps a chain of namespaces linear.
- `import x = N.y` in a namespace is not read as a value member.
- mobx `const computedAnnotation` and the rest-parameter names of rxjs overload signatures may be
  other missing kinds. They are not analysed.
