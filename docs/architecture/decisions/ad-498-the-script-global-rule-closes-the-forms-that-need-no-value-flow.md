# AD-498: The script-global rule closes the forms that need no value flow

Status: accepted. Part of #880. It amends AD-460 and AD-492.

## Context

AD-460 and AD-492 list forms that gave PASS: a write through `this` of a class method, a call with
a run-time key, a reflection with a run-time key, a navigation to a built URL, and a destructured
window member. Each can write a global or run code, and a project that holds one could still PASS
a rule that reads a global. The review of #1161 named the rest: a destructured `source` or `view`,
and `java<TAB>script:` text.

## Decision

One check (`script_forms.rs`) adds one unknown write for each node of these forms. An unknown
write blocks each proof of a script global, as in AD-460. The check adds no publication, no
exemption and no PASS.

1. **Method `this`.** A write with a key that is no literal through `this` of a class method,
   accessor or static method (`this[k] = v`, `+=`, `++`, `delete`, a pattern or `for…of` target).
   A caller can extract the method and give it the window. A constructor, a field and an arrow
   field keep their `this` as local.
2. **Run-time key call.** A call, `new`, tagged template, or `call`, `apply` or `bind` of
   `o[k]`, also through parentheses, `as`, `!` and `?.`. The key is no literal, no number. The
   object is not a literal object or array that a name binds once and nothing writes, and not
   `Math`, `JSON`, `Atomics`, `Intl` or `console` when no local name hides it. These reach no
   `Function`. `Reflect` is no namespace here.
3. **Reflection.** `Object.` or `Reflect.` `getOwnPropertyDescriptors`, a method with a run-time
   key (`o[k](…)` on `Object` or `Reflect`), and `get` or `getOwnPropertyDescriptor` with a key
   that is no literal. Each can reach `constructor`.
4. **Navigation.** `location.assign(x)` or `replace(x)`, `location = x`, `x.location = x`,
   `location.href = x` (also `+=`, a string key, and a run-time key on `location`), when `x` is no
   literal. A value that is no literal can be a `javascript:` URL, which runs in the page.
   `open(x, y)` and `window.open(x, y)` with a first argument that is no literal and a second that
   is no literal `_blank`: the target can be this window.
5. **Pattern.** A destructuring pattern (declaration, parameter, `for…of`, `catch`, assignment)
   that takes a window name or a window member out of a value: a key `source`, `view`,
   `currentTarget`, `defaultView`, `contentWindow`, `parentWindow`, `window`, `self`, `top`,
   `parent`, `frames`, `opener`, `global` or `globalThis`, also as a string key or with an escape
   that is not plain. The binding is a window, and a later read of its name does not show it.
6. **Dedup.** A write of the source analysis at the same place held no path of its own for a
   target without a static path. The check now adds the empty path of an unknown name then, so
   `this[k] = v` blocks the proofs. Without this, rule 1 gave no gap.
7. The forms that were gaps before are pinned and not changed: `el['innerHTML'] = t`,
   `x['eval'](t)`, a `java<TAB>script:` text, `this.eval(t)` and `this.Function(t)` in a class
   that a listener uses, `Reflect.get(o, k)`, and a pattern that is followed by `.eval`.

## Price

- 46 plants gave PASS on `b7811a0c0`; each gives UNKNOWN now. 31 plants were gaps before and stay
  gaps (3 of the first 49 plants of this work were gaps already and moved to that group). The 13
  precision plants keep PASS. The precision plants are `Math[k](1)`, a literal table, `xs[0]`, a plain
  pattern, `{ target }`, a literal `location`, `open(x, '_blank')`, `this['x'] = 1`, an arrow
  field, `m[k] = v`.
- The 151 TypeScript corpus cases keep all 1172 rule verdicts, and the fixture matrix keeps its
  46 pinned results. No fixture and no case changes.
- Browser pin: 0 PASS, 0 FAIL, 1 UNKNOWN, 881 gaps, unchanged. It gains 6 sites: 5
  `location.href = …` (`flow.js` 682, 692, 717, 948; `report-canvas.js` 82) and `{ …, frames, … }`
  in `report-layout.js:225`. Studio UI: 0 / 0 / 7 and 269 gaps, unchanged. It gains 1 site:
  `{ left, top } = MAP_CARD` in `map-layout.ts:113`. A gap needs one unknown write for a global, and
  each already had one.

## Mutation table

Each row removes one rule and runs the 46 closed and 13 precision plants through the release core.

| Row | Rule removed | Plants that turn PASS |
|---|---|---|
| 1 | method `this` write | 10 `this-*` |
| 2 | run-time key call | 10 `key-call-*`; `global-function` and `location-runtime-key-call` stay gaps through rows 3 and 4 |
| 3 | reflection | `reflection-descriptor`, `reflection-descriptors` |
| 4 | `location` call and write | 10 `location-*` |
| 5 | `open` target | `open-self`, `window-open-self`, `open-named` |
| 6 | window pattern | 9 `pattern-*` |
| 7 | empty path of the dedup | the same 10 `this-*` as row 1 |
| 8 | wrapper, `call`, `apply`, `bind` | `wrapped`, `constructed-wrapped`, `call-member`, `bind-member` |
| 9 | data and namespace exemption of row 2 | no PASS; `namespace-key` and `data-key` turn UNKNOWN |

## Limits

Not closed, as in AD-460: a window value that reaches a computed write through a parameter or a
call result; `this` of a method that the method passes on (`g(this)`); a stored lookup
(`const f = o[k]; f(t)`) or an alias of `Reflect`; a computed key in a pattern; a non-literal
`href` or `src` on an element and its click. A pattern with such a key reads a window in
`{ top } = rect` too: the rule reads the name, not the object (AD-492).

## Checks

`tests/test_cli_native_global_forms.py` plants each form through the default `validate` and the
release core: 46 closed (PASS on `b7811a0c0`), 31 pinned and 13 precision.
