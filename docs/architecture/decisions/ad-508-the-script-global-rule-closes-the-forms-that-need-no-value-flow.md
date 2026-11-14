# AD-508: The script-global rule closes the forms that need no value flow

Status: accepted. Part of #880. It amends AD-460 and AD-492.
## Context
AD-460 and AD-492 list forms that gave PASS (`this[k]` in a method, a run-time key call or
reflection, a built URL, a destructured window member): each can write a global or run code.
## Decision
`script_forms.rs` and `script_data.rs` add one unknown write for each node of these forms; it
blocks each proof of a script global (AD-460). They add no PASS.

1. **`this`.** A write with a run-time key through `this` of a class method, accessor or static
   method, through `super`, or through a name bound once to such a `this`.
2. **Key call.** A call, `new`, tagged template, `call`, `apply` or `bind` (name or literal key) of
   `o[k]` with a run-time key, also through parentheses, `as`, `!`, `await`, a comma, a condition
   and `||`, `&&`, `??`. Only `Math`, `JSON`, `Atomics`, `Intl` and `console` are exempt: they hold
   no function that reaches `Function`. A local object literal is no exception (see below).
3. **Reflection.** `getOwnPropertyDescriptors`; `getOwnPropertyDescriptor` and `Reflect.get` with a
   key that is no literal or names `eval`, `Function` or `constructor`; a run-time method on
   `Object` or `Reflect`; each of these members used as a value (stored, passed, `call`).
4. **Navigation.** A target `location`, `x.location`, `location.href` or `location[k]` (assignment
   with a value that is no literal, `+=`, pattern, `for…of`); `location.assign` or `replace` with a
   value that is no literal or used as a value; `open(x, …)` and `window.open(x, …)`, also through a
   comma or a condition, with a first argument that is no literal, whatever the target (a
   `javascript:` URL runs in a same-origin popup too).
5. **Alias of a global.** `Object`, `Reflect`, `location` or `open`, free, and passed, stored or
   returned; a member `x.location` likewise. A call of them is no alias.
6. **Pattern.** A destructuring pattern with a window name or member as key (`source`, `view`,
   `currentTarget`, `defaultView`, `contentWindow`, `parentWindow`, `window`, `self`, `top`,
   `parent`, `frames`, `opener`, `global`, `globalThis`), also as a string key.
7. **Dedup.** An unknown write at the place of a source write adds the empty path (rule 1 needs it).
8. Gaps before stay gaps with a test (`el['innerHTML']`, `x['eval']`, `java<TAB>script:`,
   `this.eval`, `Reflect[k]`). A literal key is the dotted form: `x['setTimeout'](t)` is a timer.
## Data exemption: removed
An exemption for a literal that a name binds once failed its proof twice and is removed. The
literal reached `Function` through an inherited method that returns it (`table.valueOf().__proto__ =
f`, `xs.sort()`), `super` in a method, an escaped key (`\u005f_proto__`) and an export clause. A sound
one needs: each use of the name is `name[expr]` in call position with the result discarded; plain
keys; member values without `this`, `super`, `arguments` or `eval`; no export; a proof over each
`Object.prototype` member. Follow-up: its plants are pinned UNKNOWN in the test file.
## Price
- 112 plants gave PASS on `main` and give UNKNOWN (109 closed, 3 data plants); 33 earlier gaps stay
  gaps; 11 precision plants keep PASS. The 151 corpus cases keep all 1172 verdicts and the fixture
  matrix its 46 results.
- Pins stay: browser 0 / 0 / 1, 881 gaps; Studio UI 0 / 0 / 7, 270 gaps. New sites: browser +6
  (`location.href = …` in `flow.js` 682, 692, 717, 948, `report-canvas.js` 82; `{ frames }` in
  `report-layout.js:225`), Studio UI +2 (`{ top }` `map-layout.ts:113`; `arrows[event.key]?.()`
  `navigation.tsx:211`).
## Mutation table
Each row removes one rule; the closed and precision plants run through the release core.
| Row | Rule removed | Plants that turn PASS |
|---|---|---|
| 1, 7 | `this` (also `super`, alias); the dedup path | 10 `this-*`, 1, 2 (row 7: all 13) |
| 2 | key call | 43: `key-call-*`, `data-*`, `data-again-*`, `callee-*` |
| 8 | callee wrappers and string `call` | 7 `callee-*` (`await` shares the arm of `(…)`) |
| 3 | reflection | 10 (descriptor, stored, passed, `any-object`, `eval-key`, …) |
| 4, 5 | `location`; `open` | 14 `location-*` and targets; 7 `open-*` |
| c | alias of a global | 5 (`alias`, `passed`, `assign-call`, `open-alias`, …) |
| 6 | pattern | 9 `pattern-*` |
| 9 | namespace exemption | none; `namespace-key` turns UNKNOWN |
## Limits
Open false PASS, not accepted: any alias of `this`, `super`, `Object`, `Reflect`, `location`, `open`
or of a looked-up function, except a name bound once to `this`; a looked-up function that is stored,
passed or an argument (`const f = o[k]`, `Function.prototype.call.call(o[k])`); any global that
navigates or opens (`open('', '_self')`, `document.open`); a destructured or aliased `setTimeout`; a
window that reaches a computed write through a parameter or call result; `g(this)` in a method; any
event member that is a window (`ev.target[k]`, `ev.srcElement[k]`); a computed key in a pattern; a
non-literal `href` or `src` of an element and its click. Tests: `test_cli_native_global_forms.py`.
