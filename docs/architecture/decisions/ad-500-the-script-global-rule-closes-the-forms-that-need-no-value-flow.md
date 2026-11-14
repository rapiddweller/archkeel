# AD-500: The script-global rule closes the forms that need no value flow

Status: accepted. Part of #880. It amends AD-460 and AD-492.

## Context

AD-460 and AD-492 list forms that gave PASS: a write through `this` of a class method, a call
with a run-time key, a reflection with a run-time key, a navigation to a built URL and a
destructured window member. Each can write a global or run code.

## Decision

One check (`script_forms.rs`) adds one unknown write for each node of these forms. An unknown
write blocks each proof of a script global (AD-460). The check adds no publication, no exemption
and no PASS.

1. **Method `this`.** A write with a run-time key through `this` of a class method, accessor or
   static method (`=`, `+=`, `++`, `delete`, a pattern or `for…of` target). A caller can extract
   the method and give it the window. A constructor, a field and an arrow field stay local.
2. **Run-time key call.** A call, `new`, tagged template, `call`, `apply` or `bind` of `o[k]`,
   also through parentheses, `as`, `!` and `?.`, when `k` is no literal. Not for a literal object
   or array that a name binds once and nothing writes, and not for `Math`, `JSON`, `Atomics`,
   `Intl` or `console` when no local name hides them: these reach no `Function`.
3. **Reflection.** `Object` or `Reflect` with `getOwnPropertyDescriptors`, a method with a
   run-time key, and `get` or `getOwnPropertyDescriptor` with a key that is no literal.
4. **Navigation.** `location.assign(x)`, `replace(x)`, `location = x`, `x.location = x` and
   `location.href = x` (also `+=`, a string key, a run-time key), when `x` is no literal: it can be
   a `javascript:` URL. `open(x, y)` and `window.open(x, y)` with a first argument that is no
   literal and a second that is no literal `_blank`: the target can be this window.
5. **Pattern.** A destructuring pattern (declaration, parameter, `for…of`, `catch`, assignment)
   with a key `source`, `view`, `currentTarget`, `defaultView`, `contentWindow`, `parentWindow` or a
   window name (`window`, `self`, `top`, `parent`, `frames`, `opener`, `global`, `globalThis`),
   also as a string key or an escape. The binding is a window that its later reads do not show.
6. **Dedup.** The source write of a target with no static path held no path, so the check now
   adds the empty path of an unknown name. Without it rule 1 gave no gap.
7. Forms that were gaps stay gaps and only get a test: `el['innerHTML'] = t`, `x['eval'](t)`,
   `java<TAB>script:` text, `this.eval(t)` in a listener class, `Reflect.get(o, k)`.

## Price

- 46 plants gave PASS on `b7811a0c0` and give UNKNOWN now; 31 earlier gaps stay gaps; the 13
  precision plants keep PASS (`Math[k](1)`, a literal table, `xs[0]`, `{ name }`, `{ target }`,
  literal `location`, `open(x, '_blank')`, `this['x'] = 1`, an arrow field, `m[k] = v`).
- The 151 TypeScript corpus cases keep all 1172 rule verdicts; the fixture matrix keeps its 46
  results. No fixture and no case changes.
- Browser pin 0 / 0 / 1 and 881 gaps, Studio UI 0 / 0 / 7 and 269 gaps: unchanged, because each
  global already had an unknown write. New sites: browser +6 (`location.href = …` in `flow.js` 682,
  692, 717, 948 and `report-canvas.js` 82; `{ frames }` in `report-layout.js:225`), Studio UI +1
  (`{ left, top } = MAP_CARD`, `map-layout.ts:113`).

## Mutation table

Each row removes one rule; the 46 closed and 13 precision plants run through the release core.

| Row | Rule removed | Result |
|---|---|---|
| 1, 7 | method `this`; the empty path | 10 `this-*` plants turn PASS (each row alone) |
| 2 | run-time key call | 10 `key-call-*` turn PASS; 2 more stay gaps through rows 3 and 4 |
| 3 | reflection | `reflection-descriptor`, `reflection-descriptors` turn PASS |
| 4, 5 | `location`; `open` target | 10 `location-*`; 3 `open` plants turn PASS |
| 6 | window pattern | 9 `pattern-*` turn PASS |
| 8 | wrappers, `call`, `apply`, `bind` | 4 `key-call-*` turn PASS |
| 9 | data and namespace exemption | `namespace-key`, `data-key` turn UNKNOWN |

## Limits

Open as in AD-460: a window that reaches a computed write through a parameter or call result;
`g(this)` in a method; a stored lookup (`const f = o[k]`) or an alias of `Reflect`; a computed key
in a pattern; a non-literal `href` or `src` on an element. A pattern reads the key, not the
object: `{ top } = rect` is a gap too. `tests/test_cli_native_global_forms.py` holds each plant.
