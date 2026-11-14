# AD-492: The browser assets are pinned until their HTML sinks are rewritten

Status: accepted by lead decisions L-167, L-171 and L-176. Part of #880. It amends AD-460.
Amended by AD-498: a destructured window member is a window now.

## Context

After AD-460 the browser contract and the Studio UI contract gave UNKNOWN on `main`.
The write check refused a local name `frames`, every markup literal with `<`, and the members of
platform windows. The platform hands out a window through data members: `UIEvent.view`,
`MessageEvent.source`, `Event.currentTarget` and `opener`. Data that the file makes can carry an
event or a window too, so such a member is a window on every object.

## Decision

1. A member `source`, `view`, `currentTarget` or a window name (`top`, `parent`, `frames`, `self`,
   `window`, `globalThis`, `opener`, `global`) is a window value on every object, as on `main`.
   `defaultView`, `contentWindow` and `parentWindow` are window values too.
2. A member `eval` or `Function`, also with a literal key, is the global on every object.
   A `constructor` member is code on every object.
3. An exemption for data that the file makes is later work with its own proof review. A literal
   can hold an event (`{ e }`), take one later (`o.e = e`) or inherit one (`__proto__`).
4. A name with a local binding is never the global. Only a script wrapper parameter names it.
5. A markup literal is text only when, read in lower case, it holds no `on…=` attribute after a
   byte that is no letter or digit, no element `script`, `iframe`, `frame`, `frameset`, `object`,
   `embed`, `applet`, `base`, `meta`, `link`, `style`, `svg`, `math`, `template`, `a`, `area`,
   `form`, `portal`, `noscript` or `xmp`, and no part `href`, `src`, `action`, `style`, `xlink`,
   `poster`, `background`, `data:`, `javascript:`, `vbscript:`, `&` or `\`. The parts are read
   without tab, line feed and carriage return. A line continuation in a literal stops the reading.
6. A comment is no argument. An HTML member with a literal key, or in a pattern, is a sink.
7. `make browser-architecture-check` compares both results with their pinned files.
   Browser: 1 UNKNOWN rule and 881 gaps from 115 sites. 41 are HTML and element or attribute
   sinks in `flow.js` and `report-canvas.js`. 74 are platform window members, for example `edge.source`, `REPORT_SCENE.parent` and `root.dataset.view`.
   A rewrite of the sinks alone does not reach PASS. Studio UI: 7 UNKNOWN rules and 269 gaps from
   22 sites: 9 `Level.Function` and 13 `source` or `view` members.
   The Studio UI lost its 6 PASS rows: the tool cannot prove its own UI free of platform windows.
   The pins only go down.

## Alternatives and limits

Data members as data, and dynamic HTML sinks as an open class, weaken the rule: rejected.
An exemption for literal data or for the resolved export of an import needs its own proof.
These forms stay open, as on `main`: a destructured member `const { source } = e`, a window
that reaches a computed write through a parameter or a call result, and DOM code from a text
outside the named triggers. The markup refusal is a list: new code-running markup needs an entry.

## Checks

`tests/test_cli_native_global_code.py` holds each form of the review of #1161 and each markup
part, also a literal or a stored value that carries an event. `tests/test_cli_native_global_writes.py`
keeps PASS for a local `frames` and plain markup. `tests/test_make_self_check.py` checks the browser target.
