# AD-492: The browser assets are pinned until their HTML sinks are rewritten

Status: accepted by lead decision L-167. Part of #880. It amends AD-460.

## Context

After AD-460 the browser contract and the Studio UI contract gave UNKNOWN on `main`.
Three parts of the write check refused ordinary data: a member `source`, `view`, `top`, `parent`
or `frames` of any object counted as a window; `Level.Function` counted as the global
`Function`; and every markup literal with `<` counted as code.
The browser assets also hold 40 dynamic HTML and attribute sinks that no rule can prove.

## Decision

1. A window name (`top`, `parent`, `frames`, `self`, `window`, `globalThis`, `opener`, `global`)
   is a window value as a member only when its object is a window value.
   `defaultView`, `contentWindow` and `parentWindow` stay window values on any object.
   `source` and `view` are data. Under AD-460 a window value reaches another object only through
   an escape, which already writes an unknown name, or through a parameter, a call result or a
   property, which is the open class of AD-460. A data member adds no new route.
2. A member `eval` or `Function` is the global only when its object is a window value.
   Another object holds the global only after a store of `eval` or `Function`, and that store is
   an escape that writes an unknown name. A `constructor` member stays code on any object.
3. A markup literal is text only when, read in lower case, it holds no `on…=` attribute after a
   byte that is no letter or digit, no element of `script`, `iframe`, `frame`, `frameset`,
   `object`, `embed`, `applet`, `base`, `meta`, `link`, `style`, `svg`, `math`, `template`,
   `a`, `area`, `form`, `portal`, `noscript` or `xmp`, and no part `href`, `src`, `action`,
   `style`, `xlink`, `poster`, `background`, `data:`, `javascript:`, `vbscript:`, `&` or `\`.
   `srcdoc`, `srcset` and `formaction` contain `src` and `action`. `&` stops a character
   reference, and `\` stops an escape. Any other markup literal and every template with a
   substitution stay code.
4. `make browser-architecture-check` compares the browser result with
   `docs/architecture/target/browser-expected.json`, as it does for the Studio UI.
   The pin holds 1 UNKNOWN rule and 881 named gaps of the 40 sinks: `flow.js` has 29 `innerHTML`
   writes, 6 `insertAdjacentHTML` calls and 2 element or attribute calls with a run-time name,
   and `report-canvas.js` has 3. The pin only goes down. A rewrite to DOM APIs and
   `textContent` is a follow-up slice.

## Alternatives and limits

Moving dynamic HTML sinks into an open class weakens the rule without a proof: rejected.
A rewrite of the assets is outside a fix of a red `main`.
`e.source`, `e.view` and `x.parent` that hold a window and reach a computed write or an escape
stay in the open class of AD-460. The markup refusal is a list: a new element or attribute
that runs code needs a new entry.

## Checks

`tests/test_cli_native_global_writes.py` keeps PASS for data members, a data `Function` member
and plain markup, and keeps a gap for a `defaultView` window, a frame, a reference and handlers.
`tests/test_cli_native_global_code.py` refuses each markup part of rule 3 and a `Function`
member of `self`. `tests/test_make_self_check.py` fails the browser target without a result.
