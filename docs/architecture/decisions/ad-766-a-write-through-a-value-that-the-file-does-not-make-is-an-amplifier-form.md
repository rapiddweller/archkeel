# AD-766: A write through a value that the file does not make is an amplifier form

Status: accepted. Part of #880. Closes #1524. It amends AD-460, AD-508 and AD-540.

## Context
A write with a run-time key was an unknown write only through a window-like value (a window name,
a window member such as `source`, the `this` of a plain function). The audit of #1524 gave 8 PASS
results for a rule that the code violates: an event target (`ev.target[k] = f`, `ev.srcElement[k]`),
the `this` of a class method that a listener receives through an alias of an alias or through
`super.valueOf()`, and such a value passed to a function, returned from one or kept in a member.
With `k = 'open'` each one replaces the global `open` in a browser. Five reflective writes of the
same class gave PASS too: `Reflect.set`, `Reflect.defineProperty`, `Object.defineProperty`,
`Object.defineProperties` and `Object.assign` on an event target.

## Decision
1. **Computed write.** `x[k] = v` with a key that is no literal and no number, on a value that the
   check does not prove local, is an amplifier form of AD-540 (`script_window.rs`, `global_write`).
   On a window-like value it stays direct.
2. **Reflective write.** A call of the free `Object` member `assign`, `defineProperty`,
   `defineProperties` or `setPrototypeOf`, or of the free `Reflect` member `set`, `defineProperty`
   or `setPrototypeOf`, is an amplifier form when its first argument is not proven local, and a
   direct form when it is a window-like value or a spread (`script_forms.rs`, `reflective_write`).
3. **Proven local** (`proven_local`): a new value (an object, array, class or function literal, a
   text, a number), `Object.create(…)` with the free `Object`, a name bound once to a new value and
   never written, and the `this` of a constructor, a field or a static block (as before).
4. **Numeric key.** An assignment gives its right side, so `E[E['A'] = 0] = 'A'` of a compiled enum
   has a numeric key (`script_numeric.rs`).

## Soundness
- AD-540 says when an amplifier form blocks: only with a host entry. A window enters the scan only
  from the host (a free name that is not inert, a script file) or from outside (premise 4). Without a
  host entry no value of the file can be the window, so the write cannot name a global; this keeps
  `export function set(o, k, v) { o[k] = v }` without a gap (`the_premise_is_not_closed`).
- With a host entry, any value that the file does not make can be the window: the platform hands
  out event targets and calls a listener with `this` set to the target; each pass, return or store
  keeps it. The rule reads no flow, so it covers each of these paths at once.
- A proven local value is a new object of the file. No path gives the window to it.
- A named write `x.open = v` through such a value already blocks the global `open` by name (AD-460).

## Price
In a scan with a host entry, a write with a run-time key into a parameter, a member or a call
result blocks every global proof. Rules do not change on the measured projects; no PASS turns
UNKNOWN. graphql-js v16.15.0: 67 gaps, unchanged. TypeScript fixtures F, H, H-uml and L-nest:
unchanged. Explorer scripts (`browser.toml`): 586 to 592 gaps (5 places) (`positions[label] = …` in
`flow.js` 1554, 3116, `report-layout.js` 49, 59; `Object.assign(route, drawn)` in `flow.js` 534).

## Amendment: indirect reflective writes
5. `__defineGetter__` and `__defineSetter__` of any object are reflective writes on their receiver.
   `Object` and `Reflect` read through a window name (`globalThis.Object`, `window['Reflect']`) are
   the free ones. A reflective or accessor member that is no direct callee (stored, passed, called
   through `call` or `apply`, `Reflect.apply(Reflect.set, …)`) is direct: the check cannot read the
   target of the later call (`script_reflective.rs`). A stored free `Object` or `Reflect` was direct
   already (AD-508 rule 5). Measured: graphql-js, the 4 TypeScript fixtures and the Explorer scripts
   keep their gaps and rules (613 Explorer gaps before and after).

## Open
- A global write by code outside the scan roots (#1546).

## Tests
`native/typescript/src/script_window_value_tests.rs`: the 8 plants of #1524, 5 reflective writes,
7 local writes that keep the proof, a named write, 11 indirect reflective writes. `tests/test_collector_false_pass_ts_window_values.py`:
the 8 plants of #1524 and 3 reflective writes through the release core, and one local write that
keeps PASS.
