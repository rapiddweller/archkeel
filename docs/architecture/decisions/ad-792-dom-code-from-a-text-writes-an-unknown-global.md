# AD-792: DOM code from a text writes an unknown global

Status: accepted. Part of #880. Closes #1526. It amends AD-460, AD-508 and AD-540.

## Context
A page runs a text as code in more places than `eval`. The text checks of `script_code.rs` read a
literal text and the direct call `document.write(…)`. The audit of #1526 gave PASS where `b`
replaces the global `open` that `a` calls: `const d = document.open(); d.write('<script>…')`, and
`a.href = ['java', 'script:open=…'].join(''); a.click()`. The same class gave PASS on main
`f856a0e0a` for 20 more forms: a document that the file keeps or passes on, `document.write` used
through `call`, `bind` or a literal key, a frame `src`, a form `action`, an SVG `href.baseVal`,
`setAttribute('href', t)` and `execCommand('insertHTML', false, t)`. The third audit plant,
`open('', '_self')[k] = f`, is UNKNOWN on main since AD-766.

## Decision
`script_dom.rs` holds the rule. Only `script_declarations.rs` calls it, for each node and each
write target, beside the window check.
1. **Document code.** A member `write`, `writeln` or `open` (a name or a literal key) of a document
   (`document`, or a member `document`, `ownerDocument` or `contentDocument`) is a direct form,
   in each use but the direct call `document.write(…)`, which `script_code.rs` reads already.
2. **Document value.** The free name `document`, or a member `document`, `ownerDocument` or
   `contentDocument`, that is passed, stored or returned is an amplifier form. So is a
   destructuring pattern that takes one of these members. No later read of such a value sees its
   `write`.
3. **Address.** A write of a member `href`, `src`, `action`, `formAction`, `data` or `baseVal` with
   a value that is no literal, also by a literal key or a compound assignment, is an amplifier form.
   So is `setAttribute` or `setAttributeNS` of the attribute `href`, `src`, `action`, `formaction`,
   `data` or `xlink:href` (in any letter case) with a value that is no literal. A target on
   `location` keeps its own check (AD-508).
4. **Markup command.** `execCommand` with the command `insertHTML` or a command that is no literal,
   and with markup that is no inert literal, is a direct form.

## Soundness
- Each form hands a text to the page, and the text can be `<script>…`, an `on…` handler or a
  `javascript:` address that writes any global. A literal text is read by the text checks: a
  `javascript:` literal and markup with code are gaps there already.
- A document and an element need a page. A page gives them only through a host entry (the free
  `document` is one) or from outside (AD-540 premise 4), so forms 2 and 3 are amplifiers. Forms 1
  and 4 run the text with no value flow, so they are direct.
- A run-time key write (`el[k] = t`) and `Object.assign(el, { href: t })` are amplifier forms of
  AD-766 already.

## Truth
Chrome 157 (headless, `--dump-dom`) runs each form in a fresh same-origin frame with a real
payload and checks the global `open` of the frame (`/tmp`, not in the repository). 18 forms replace
it: each document form, the link click, a literal-key `href`, a compound `href`, `setAttribute` in
two letter cases, a frame `src` (through `parent.open`), a form `action`, a button `formAction`, an
SVG `href.baseVal`, `setAttributeNS` of `xlink:href` and `insertHTML`. An object `data` address does
not run in Chrome 157. It stays in the rule because another engine can run it. A literal `#home`
address and a `class` attribute do not replace it.

## Price
No PASS turns UNKNOWN on the measured projects. graphql-js v16.15.0: 1 PASS and 7 UNKNOWN, 67 gaps,
unchanged. TypeScript fixtures F, H, H-uml and L-nest: rules and gaps unchanged. In a scan with a
host entry, a write of a member `data` or `src` with a value that is no literal keeps every free
standard name from a proof, for example `node.data = text` on a text node.

## Open
A framework that renders an address from data (`<a href={url}>` in JSX, a template binding) runs
outside the scan roots. Premise 4 does not name it: it hands in no platform object, it receives a
text. The text checks read no JSX attribute. Issue #1662 tracks it.

## Tests
`tests/test_cli_native_dom_code.py`: 24 forms that must not PASS (22 gave PASS on main `f856a0e0a`),
and 6 forms that keep PASS (a literal address, `document.title`, a member read, a `class` attribute,
`execCommand('copy')`, a `_blank` popup).
