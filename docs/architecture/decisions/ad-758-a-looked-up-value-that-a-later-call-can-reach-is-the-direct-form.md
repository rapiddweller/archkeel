# AD-758: A looked-up value that a later call can reach is the direct form

Status: accepted. Part of #880. Closes #1547 and #1525. It amends rule 2 of AD-508.

## Context
Rule 2 of AD-508 reads only a call at the place of the read: `o[k](t)`. `const p = o[k]; p(t)()`
gave PASS. With `o = () => 1` and `k = 'constructor'` the value is `Function`, and node v26 shows
that each of 20 such forms overwrites a global. The premise of AD-540 does not cover it: the caller
hands in a function and two texts, no global or platform object.

## Decision
`script_lookup.rs` adds rule 2b. A member read with a run-time key (the receiver is no namespace of
rule 2, the read is no write target) is the direct form of rule 2 when a call can reach its value.
The check follows the value from the read and stops at the first use that reaches:
- **Followed.** A wrapper of rule 2 (parentheses, `as`, `!`, `await`, the last of a comma, a branch
  of a condition, `||`, `&&`, `??`); a local name of a declarator or of a later assignment (each
  reference in the scope of the binding); an array or object literal that holds the value (each
  member or element read of the literal is the value again); a member `call`, `apply` or `bind`.
- **Reaches.** A call, `new` or tag of the value; each use that leaves the walk: an argument (so
  also `Reflect.apply` and `Function.prototype.call.call`), a `return`, a `throw`, a `yield`, a write
  to a member or a free name, an export, a class field, a default value, a pattern of a literal that
  holds it, a spread outside a literal, a local name in a script file, a name with an escape, and
  more than 256 steps.
- **Ends.** A use that cannot call the value: a discarded value, `typeof`, `!`, `void`, `delete`, a
  comparison or arithmetic, an update, a text, a computed key, a condition, a `for…of` or `for…in`
  over it, an array pattern of it, an object pattern of plain names other than `call`, `apply` and
  `bind`, and a member with another plain name.

## Soundness
- Inside the scan, `o[k]` can be `Function` only through the run-time key: premise 4 of AD-540
  keeps a platform object of the caller out. The walk lists each use that passes the value on
  unchanged. Each other use leaves the walk (Reaches) or gives another value.
- A member with a plain name other than `call`, `apply`, `bind` and `constructor` (a direct form
  already) gives a member of `Function`, `Object` or a prototype. None of these builds code from a
  text without a direct form.
- The elements of a value that a key names are no such value: an inherited member is not iterable,
  or it iterates to nothing (`Array.prototype` is empty).
- A script file can share a top-level name with another file, and `with` can give a name to an
  object, so a local name of a script leaves the walk. A module is strict code: it has no `with`,
  and its `eval` declares no name.

## Price
Each read that is returned, passed or stored is now a blocker. Rules do not change on the measured
projects; no PASS turns UNKNOWN.

| project | blocker gaps | all gaps |
|---|---|---|
| graphql-js v16.15.0 | 2 to 67 | 2 to 67 |
| Explorer scripts (`browser.toml`) | 37 to 101 | 457 to 583 |
| fixtures F-typescript-story, H-typescript, H-uml-typescript, L-nest-realworld | 0 to 0 | unchanged |

The golden reply of `excalidraw-laser-pointer` gets one gap: `simplify.ts:27` passes `points[maxIndex]`
on, and `maxIndex` comes from a pattern, so it is not proven a number.

## Open
- A value that a namespace of rule 2 gives (`Math[k]` is `Object` at most) stays exempt.
- Precision, not soundness: a return to a caller in the scan is not followed into the caller.

## Tests
`native/typescript/src/script_lookup_tests.rs`: 20 node-checked forms, 13 data forms that keep the
proof, 4 hostile keys, 8 forms that leave the walk. `tests/test_collector_false_pass_ts_lookup.py`:
the 3 plants of #1525 and 6 of #1547 through the release core, and one data plant that keeps PASS.
