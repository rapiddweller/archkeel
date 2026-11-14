# AD-460: A write through any alias of the global object blocks a global proof

Status: accepted. Part of #880. Refs #740.
Amended by AD-500: the forms of the limits that need no value flow (a run-time key on `this` of a
method, a run-time key call, a reflection, a navigation, a window pattern) are closed.

## Context

The TypeScript collector proves a use such as `window.open()` or `Lib.run()` only when no file
writes that global. The writes skipped one leading `window`, `self`, `globalThis` or `frames` only.
Thus `parent.open = f`, `(window.open as any) = f` and `document.defaultView.open = f` were silent.
Code from a text and a callback `this` also wrote globals that no proof saw. A forbidden edge gave PASS.

## Decision

One check in `script_window.rs` and `script_code.rs` gives the global writes of each node.
Its writes go to the script writes, the source writes and the write paths.
Each proof reads them: a publication, a source origin, a platform, `declare` or vendor global, a
namespace and a factory. A homes test pins each decision site to its gate.

1. Named writes use an allowlist. A write of the property `N` of an object `o` writes the global `N`,
   unless `o` is proven local. Proven local: a name bound once to a new value and never written,
   a function declaration, and the `this` of a constructor, a field initializer or a static block.
   A module `this` at the top level is `undefined`, so it is local too.
   A parameter, an import, a property, a call result and the `this` of a method or a function
   are not proven. A callback receives the window as `this`; an extracted method can too.
2. A member chain below a window value also writes its first member: `parent.Lib.run = f` writes `Lib`.
3. Unknown keys use a list of window values: a window name (`window`, `self`, `globalThis`,
   `frames`, `top`, `parent`, `opener`, `global`), a window member (`defaultView`,
   `contentWindow`, `parentWindow`, `view`, `source`), an element of one, a wrapper alias, and a
   function or script `this`. Such a value with an unknown key, or such a value that escapes,
   writes an unknown name. `source_input.rs` is the one home of the window names.
4. Code from a text writes an unknown name: `eval`, `Function` or a `constructor` member used as
   more than a read; the text `constructor`; a timer without a function; a computed call on a
   function, an element, a `constructor` member or a window value; `document.write`; an `on…` or
   unknown attribute; a `script` element; HTML text with `<`; a `javascript:` text.
   The existing import analysis gives a gap for a dynamic import of a text or of an unknown name.
5. A top-level `enum` or `namespace` of a script writes its name.
6. Each reader of a target unwraps parentheses, `as`, `satisfies`, `!` and `<T>` with one helper.
   It compares the cooked name; an escape that is not plain is an unknown name.

A written name blocks the proofs of that name only. An unknown name blocks every proof of the
project. The rules add writes only. They create no publication, target or PASS maker.

## Alternatives and limits

A denylist of global aliases grows with each plant, so named writes use the allowlist.
An allowlist for unknown keys blocks each `map[k] = v` on a parameter. That blocks every project.
A full value-flow analysis is out of scope. These open false PASS classes stay, not accepted:
a window value that reaches a computed write through a parameter, a call result or a property;
an extracted class method that writes `this[k]`; a computed call with a key built at run time on
a parameter, an import, a property or a global function (`Object[k](text)`); a reflection call
with a run-time key; DOM code from a text outside the named triggers. A broader computed-call
trigger blocked all 117 `Math` proofs of the golden case `excalidraw-math` (`Math[func](x)`). `docs/known-limits.md` lists them and the older open classes.
`assignment_targets` keeps its shape: unwrapping it there makes new publications, a PASS path.

Cost, measured with the release core on the reviewer's plants, the fixtures and the corpus:
11 of 38 ordinary plants change from PASS to UNKNOWN (13 before this round), each for a reason
named above. `fixtures/H-typescript` keeps 9 PASS. `fixtures/L-nest-realworld` is unchanged.
The 151 TypeScript corpus cases keep all 1061 rule verdicts. No plant and no case changes to PASS.

## Checks

`tests/test_cli_native_global_writes.py` and `tests/test_cli_native_global_code.py` plant each
form through the default `validate` and the release core. Precision plants keep PASS for local
values, class `this`, named timers, `constructor` reads, `instanceof Function` and empty HTML.
`tests/test_collector_native_typescript_homes.py` pins the window names and the decision sites.
The native self-check pins and `native/expected-gaps.json` stay unchanged.
