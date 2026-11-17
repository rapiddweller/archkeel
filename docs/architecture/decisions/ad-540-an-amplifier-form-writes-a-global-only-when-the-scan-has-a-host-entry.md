# AD-540: An amplifier form writes a global only when the scan has a host entry

Status: accepted. Part of #880. It amends AD-460, AD-492 and AD-508. AD-788 amends premise 4.

## Context
One unknown write of a global blocks the proof of every script global. On graphql-js v16.15.0 (134
modules) 49 nodes gave one and none writes a global (33 read a member `source`, 2 read `.parent`, 1
returns `this`, 4 destructure `source`, 9 use a run-time key). So the 393 standard globals got a gap.
4.0.1 read no free name: no gap, and no proof (`window.Lib = ...` in one file and `Lib.run()` in
another was a silent false PASS there).

## Decision
`Reach` (`script_window.rs`) names two kinds of form.
- **Direct.** The form names the global object or runs text: a root name passed on, `eval`,
  `Function`, a used `constructor`, a timer with a text, an HTML sink, a `javascript:` URL,
  navigation, `Object`/`Reflect` passed on, reflection, and **a run-time key that can name
  `constructor`** (a key call `o[k](...)`, a chain `o[a][b]`, `fn[k]`). It blocks as before.
- **Amplifier.** The form says only that a value may be the global object: a member `source`,
  `view`, `currentTarget`, `defaultView`, `contentWindow`, `parentWindow` or a window name, the `this`
  of a function, a window name in a pattern, `this[k] = v` in a class method, a run-time key on such
  a member. It blocks every proof only when the scan has a **host entry**.

The scan has no host entry when 1 to 3 hold (the collector proves them). 4 is a premise.
1. Every file is an ES module by syntax: top-level `import` or `export`, no `export =`, no `with`,
   no syntax error. A script file is an entry (a plain call there has `this` = global object).
2. No direct form exists (its empty path still blocks).
3. Every free name is inert (`script_host.rs`: the ECMAScript value globals, no `globalThis`,
   `eval`, `Function`) or its use is contained: head of a chain of literal members that is the
   operand of `typeof`, `!` or a comparison, the left of `&&`, or a condition. A call, argument,
   stored or returned value, left of `||`/`??` and a run-time key are not contained.
4. PREMISE, not a proof: **code outside the scan roots hands in no global or platform object and
   replaces no global** (AD-788). A caller can give `set(window, 'Math', x)` to `set(o, k, v)`.
   Main relied on it already for a parameter. A written type is no proof, and the rule reads none.

Where the premise does not cover a read the gap stays (a named write `o.Math = v`, a script file,
`declare global`, a merge across files). hono and zod keep their gaps.

**Numeric keys.** A number or symbol cannot name `constructor`, so it is no run-time key: a number,
arithmetic (`- * / % ** & | ^ << >> >>>`), unary `-` `+` `~`, an update, `Symbol.iterator` and the
other well-known symbols, and a name with one declarator of such a value whose every write keeps a
number (`for (let j = 0; j <= n; j++)`). `i = k`, `i += k`, `for (i in o)`, a parameter, `.length`
and a call are refused.

## Soundness
- **Direct stays direct.** A key can build `constructor` (`'con' + 'structor'`, `Object.getOwnPropertyNames`,
  data), and `fn['constructor']` is `Function`: the global object with no free name. AD-508 rule 2
  (43 plants) holds. A design note that read a key call as an amplifier was wrong.
- **A write is direct.** `x.parent[k] = v`, `this[k] = v`: a callback or factory of the caller can
  give the object. Only a read, a pass-on, a pattern or a call is an amplifier.
- **An amplifier needs a window:** from the host (condition 3), a script file (condition 1) or
  outside the scan (the premise). Inert names give no host object and their callbacks run in a
  module. A contained use gives a string, a Boolean, or `a` of `a && b` only when `a` is false.

## What does not close
- graphql-js keeps 397 gaps: two direct forms block all 393 standard globals:
  `execution/execute.ts:1304` `source[info.fieldName](...)` (key text of the caller) and
  `jsutils/suggestionList.ts:129` `rows[aLength % 3][bLength]` (`b.length` is not proven a number).
  With those two lines changed in a copy the same core gives 4 gaps (`process`: no `@types/node`).
  Closing them needs a second premise (key text from outside never names `constructor`) and a
  proof that `.length` is a number. Neither is here.
- **The premise in the report.** The linked collector states it (`Facts.scope_premise`, not on the
  wire). `Model::scope_premise` gives it, the ruling writes the frame key `premise` (none when the
  collector states none), the page shows "Stated assumption: ..." and `validate --text` "Assumption: ..." under the verdict; the shell refuses a non-text premise and a TypeScript scan without one. The `scope`
  word stays `complete`: the shell requires it for a PASS; the shell allows the key `premise` only.

## Mutation table
Removing a condition turns a plant of `script_host_tests.rs`: module syntax, `with`, `export =`
(`a_file_that_is_no_module_is_an_entry`); direct forms (`a_direct_form_blocks_in_a_scan_without_a_host_entry`);
non-inert names (`a_host_entry_makes_an_amplifier_form_write`); contained use (`a_contained_use_of_a_host_name_is_no_entry`,
`a_use_that_leaves_the_place_is_an_entry`); numeric writes (`a_key_that_is_no_number_is_a_run_time_key`).
