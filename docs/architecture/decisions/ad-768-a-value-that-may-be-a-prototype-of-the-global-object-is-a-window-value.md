# AD-768: A value that may be a prototype of the global object is a window value

Status: accepted. Part of #880. Closes #1527. It amends AD-460 and AD-766.

## Context
The global object inherits members from prototypes: `dispatchEvent` and `addEventListener` from
`EventTarget.prototype` in a browser. A write to such a prototype changes the global as a write to
the window does. The audit of #1527 gave PASS for `Object.defineProperty(EventTarget.prototype,
'dispatchEvent', …)` in `b` and `window.dispatchEvent(…)` in `a`. AD-766 closed that plant: a
reflective write on a value that is not proven local is an amplifier form. Two forms still gave
PASS on main `27cba5fe6`: a prototype that is passed to a function (`g(EventTarget.prototype)`),
and a new `__proto__` of an event target (`ev.target.__proto__ = { dispatchEvent: f }`).

## Decision
`script_prototype.rs` holds the rule. `script_declarations.rs` calls it for each node and each
write target, beside the window check.
1. **Prototype value.** `X.prototype` and `X['prototype']` when `X` is no class of the file,
   `x.__proto__` on any value, and a call of a member `getPrototypeOf`. A member name with an escape
   that is not plain counts as `__proto__`.
2. **Escape.** A prototype value that is passed, stored or returned is a direct form. A member read
   (`Object.prototype.hasOwnProperty.call(…)`), an element (`c.prototype[Symbol.toStringTag]` in
   graphql-js `instanceOf.ts:30`) and a comparison are no escape.
3. **Keyed write.** `p[k] = v` with a run-time key on a prototype value is a direct form.
4. **New prototype.** A write of the member `__proto__` on a value that is not proven local is an
   amplifier form, as each write through such a value is (AD-766).
5. **Class of the file.** A name that one class declaration binds, or a name bound once to a class
   expression, that nothing writes again, has a `prototype` that is no prototype value: the
   `prototype` of a class is neither writable nor configurable. The `prototype` of a function is
   writable, so a function is no such class.

## Soundness
- Each prototype that the global object inherits from is reached from a platform name
  (`EventTarget`, `Object`), from `__proto__` or from `getPrototypeOf`, or from a value that one of
  these gave. The first two are prototype values where they are read; a call of `getPrototypeOf`
  is one where it gives the value. Each pass of such a value is a direct form, so no later read
  needs to see it.
- A platform name gives the prototype without a host entry, so forms 2 and 3 are direct.
  `x.__proto__ = v` changes the members of the global object only when `x` is the window, which
  needs a host entry or a value from outside (AD-540 premise 4).
- A named write through a prototype (`EventTarget.prototype.dispatchEvent = f`) already blocks the
  global of that name (AD-460).

## Price
No PASS turns UNKNOWN on the measured projects. graphql-js v16.15.0: 1 PASS and 7 UNKNOWN, 67 gaps,
unchanged. TypeScript fixtures F, H, H-uml and L-nest: rules and gaps unchanged. A project that
passes the prototype of an imported class or of a parameter (`Object.setPrototypeOf(D.prototype,
B.prototype)` with an imported `B`) keeps every free standard name from a proof.

## Open
A reflective write on the prototype of a class of the file
(`Object.defineProperty(C.prototype, …)`) is an amplifier form of AD-766, because `proven_local` does
not read a class prototype. In a scan with a host entry it is a false UNKNOWN.

## Tests
`tests/test_cli_native_prototype_patch.py`: 18 patch forms that must not PASS, and 4 reads that
keep PASS. Node 26 runs each patch form in a VM with a synthetic `EventTarget` and a window that
inherits from it, and each form reaches the function of `b`.
