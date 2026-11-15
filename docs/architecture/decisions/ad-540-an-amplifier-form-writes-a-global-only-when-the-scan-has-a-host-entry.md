# AD-540: An amplifier form writes a global only when the scan has a host entry

Status: accepted. Part of #880. It amends AD-460, AD-492 and AD-508.

## Context
AD-460, AD-492 and AD-508 read many forms as a possible write of an unknown global. One such write
blocks the proof of every script global of the project. On graphql-js v16.15.0 (134 modules) 49
nodes gave this write, and none of them writes a global: 33 read a member `source` that is passed
on, 2 read `.parent`, 1 returns `this`, 4 destructure `source`, 9 use a run-time key. So the 393
standard globals (`Object`, `Error`, `Symbol`, ...) each got the gap "Script global X has no unique
unconditional publication". 4.0.1 never read a free name, so it had no such gap. It also had no
proof: `window.Lib = ...` in one file and `Lib.run()` in another was a silent false PASS there.

## Decision
The forms are of two kinds. `Reach` (`script_host.rs`) names them.

- **Direct.** The form names the global object or runs text: a root name (`window`, `self`,
  `globalThis`, `frames`, `parent`, `top`) that is passed on, `eval`, `Function`, a `constructor`
  member that is used, a timer with a text, an HTML sink, a `javascript:` URL, a navigation,
  `Object` or `Reflect` passed on, a reflection, and **a run-time key that can name `constructor`**
  (a key call `o[k](...)`, a chain `o[a][b]`, `fn[k]`). It blocks every proof, as before.
- **Amplifier.** The form says only that a value may be the global object: a member `source`,
  `view`, `currentTarget`, `defaultView`, `contentWindow`, `parentWindow` or a window name on any
  object, the `this` of a function, a window name in a destructuring pattern, `this[k] = v` in a
  class method, a run-time key on a value that is such a member. It blocks every proof only when the
  scan has a **host entry**.

The scan has no host entry when all of this holds. The collector proves 1 to 3.

1. Each file is an ES module by syntax: top-level `import` or `export`, no `export =`, no
   `import x = require()`, no `with`, no syntax error. A script file gives a host entry, because a
   plain call there gives `this` as the global object and a `var` there makes a global.
2. No direct form exists. The empty path of a direct form still blocks (AD-460).
3. Each free name is on the inert list (`script_host.rs`, the value globals of the ECMAScript `lib`
   without `globalThis`, `eval`, `Function`) or its use is contained: the head of a chain of literal
   members, and the chain is the operand of `typeof`, `!` or a comparison, the left side of `&&`, or
   a condition (`typeof window !== 'undefined'`, `globalThis.process && process.env.NODE_ENV ===
   'production'`). A call, an argument, a stored or returned value, the left side of `||` or `??`
   and a run-time key are not contained. A new name is a host entry until someone adds it.
4. PREMISE, not a proof: **code outside the scan roots hands in no global object and no platform
   object** (an event, a document, a frame). A caller can give `set(window, 'Math', x)` to
   `export function set(o, k, v) { o[k] = v }`, and the collector cannot see it. Main relied on this
   already for a plain parameter (`o[k] = v` gave no gap), and refused it only for a member
   (`e.source`). A written type is no proof (`as any`), and the rule reads no type.

The premise is a stated limit. Where it does not cover a read, the gap stays: a write of a global
by scanned code (a named write `o.Math = v` still blocks `Math`), a script file, `declare global`
(only a write publishes), a merge across files.

**Numeric keys.** A key that is a number or a symbol cannot name `constructor` or `parent`, so it is
no run-time key (`runtime_object`, `global_write`): a number, an arithmetic result (`- * / % ** & |
^ << >> >>>`), unary `-`, `+`, `~`, an update, `Symbol.iterator` and the other well-known symbols,
and a name that is bound once to such a value and whose every write keeps a number (`for (let j = 0;
j <= n; j++)`; `i += k` with `k` unknown, `i = k` and `for (i in o)` are refused). A parameter, a
`.length` and a call are not numeric: a value of the file may be any text.

## Soundness arguments
- **Direct stays direct.** A run-time key can build the text `constructor` from literal parts
  (`'con' + 'structor'`), from `Object.getOwnPropertyNames` or from data. `fn['constructor']` is
  `Function`, which makes the global object with no free name and no host entry. So AD-508 rule 2
  (key call, 43 plants) holds. The design note that read a key call as an amplifier is wrong.
- **An amplifier needs a window.** A member `source` or `parent`, `this`, or a window pattern is the
  global object only when the program received it: from the host (E1: a free name that is not
  inert), from a script file (E2: a plain call has `this` as window, `with`, an implicit global) or
  from outside the scan (E3: the premise).
- **E1.** An inert name gives no host object: no value of the list is `globalThis`, and no method
  of it returns the global object. A callback that the inert names call runs in a module, so its
  `this` is `undefined`. A contained use reads a value and keeps no reference: `typeof`, `!`, a
  comparison and a condition give a string or a Boolean; `a && b` gives `a` only when `a` is false.
- **E2.** An ES module is strict: no `this` as window, no `with`, no implicit global. The collector
  does not read the format of a file, so a file with `export =`, `import = require` or `with` is a
  host entry.
- **Reflection and `Object`.** `Object` passed on, `Reflect`, a descriptor read and a method with a
  run-time key on `Object` stay direct.

## What does not close
- graphql-js keeps 397 gaps. Two nodes are direct forms of AD-508, and one direct form blocks all
  393 standard globals: `execution/execute.ts:1304` `source[info.fieldName](args, ...)` (the key is
  text of the caller) and `jsutils/suggestionList.ts:129` `rows[aLength % 3][bLength]` (`bLength` is
  `b.length`, not proven numeric). With those two lines changed in a copy the same core gives 4
  gaps (`process`, `jsutils/instanceOf.ts:5,7`: no `@types/node`, so nothing declares it). Closing
  the two needs a decision on a second premise (the text of a key from outside never names
  `constructor`) and a proof that `.length` is a number. Neither is in this record.
- hono and zod keep their gaps: a real host entry (`document`, `globalThis` passed on) and a direct
  form (`new Function`).
- The scope text of a report does not yet state the premise. The text of `scope` is `complete` or a
  reason, and many readers compare it. A new field of the collector reply is needed (a follow-up
  slice).

## Price
- A scan that has only inert names, contained uses and amplifier forms gives a complete scope where
  it gave a gap. Every other scan decides as before.
- A key that is proven numeric is no run-time key. A wrong proof would hide a direct form; the plants
  `a_key_that_is_no_number_is_a_run_time_key` pin the refusals.
- Cost: one pass over the nodes of a file for the host entry; one walk of the writes of a numeric
  name, cached by scope and name.

## Mutation table
Each row removes one condition; the plants of `script_host_tests.rs` turn.

| Row | Condition removed | Plants that turn |
|---|---|---|
| 1 | module by syntax | `a_file_that_is_no_module_is_an_entry` |
| 2 | direct forms stay direct | `a_direct_form_blocks_in_a_scan_without_a_host_entry` |
| 3 | non-inert free name is an entry | `a_host_entry_makes_an_amplifier_form_write` |
| 3b | contained use | `a_contained_use_of_a_host_name_is_no_entry`, `a_use_that_leaves_the_place_is_an_entry` |
| 4 | numeric keys: each write keeps a number | `a_key_that_is_no_number_is_a_run_time_key` |
| 5 | named write blocks its name | `a_named_write_or_a_syntax_error_still_blocks` |
