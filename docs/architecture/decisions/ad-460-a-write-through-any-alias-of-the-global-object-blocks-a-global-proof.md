# AD-460: A write through any alias of the global object blocks a global proof

Status: accepted. Part of #880. Refs #740.

## Context

The TypeScript collector proves a use such as `window.open()` as the platform global `open` only
when no file of the project writes the path `open` on the global object.
The write paths skipped one leading `window`, `self`, `globalThis` or `frames` only.
Thus `parent.open = f`, `top.open = f` and `window.window.open = f` wrote `parent.open` and
`window.open`, not `open`. The use stayed proven, and a forbidden edge gave PASS.
Code that runs text, and `this` in a sloppy script, also wrote globals that no path showed.

## Decision

1. A write path drops all its leading global names: the roots, `top`, `parent` and `opener`.
   `parent.self.open = f` writes `open`. A path of only such names writes an unknown name.
   A local binding of the same name is not a global name.
2. A node that runs text as code writes an unknown name, in any file.
   These nodes are `eval`, `Function`, a `constructor` member and a timer without a function.
   A literal computed key with one of these names counts too. A type position does not count.
3. A `this` that can be the global object writes through its members.
   This `this` is in a file without module syntax, and not in a class body, method or static block.
   `this.open = f` writes `open`. A computed member directly on `this` writes an unknown name.
   Such a `this` that escapes, for example `var g = this`, writes an unknown name.
4. An unknown write blocks each platform, `declare` and vendor proof of a global.
   The use then keeps the existing named gap `Script global <name> has no unique unconditional
   publication`, so the scope is incomplete and the rule is UNKNOWN.

The rules add writes only. They never create a publication, a target or a PASS.
The use side, the frame roots of a use and the existing makers of PASS stay unchanged.

## Alternatives and limits

Do not mark only the reported `parent` form: the same cause covers every chain of global names.
Do not make every intrinsic effect an unknown write in a module file.
`Reflect`, `Object.defineProperty` and `Object.assign` need the global object as a value.
The existing escape gap already covers that value.
A module file is strict, so its `this` is never the global object.
TypeScript 5.9 removed `noImplicitUseStrict`, so emitted module code stays strict.
A computed key that is not a literal can still reach `Function` in a module file.
This limit is not new: the collector does not bound computed member calls in module files.

## Checks

`tests/test_cli_native_global_writes.py` plants each form in a file of `b` through the default
`validate` and the release core. A use in `a` through `window.open()` or `open()` must not give PASS.
Precision plants keep PASS for a strict `this`, a local `parent`, a timer callback and a type.
A mutation table in the pull request removes each condition and names the test that fails.
The native self-check pins and `native/expected-gaps.json` stay unchanged.
