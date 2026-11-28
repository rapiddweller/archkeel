# AD-1530 A word in a Rust comment names no module for an extension

**Status.** Accepted. Builds on AD-770 and AD-1220. Closes #2243.

**Decision.** The search for the modules that an extension file names (`outside_native.rs`) skips
the bytes of a comment in a Rust file (`//`, `///`, `//!`, `/* */` with nesting). The state of the
comment is read with a small lexer that tracks strings, raw strings (`r"`, `r#"`, `br#"`), characters
and lifetimes, so that `//` or `/*` inside a string never starts a comment. In a doubt the byte stays
code. A word in a string, in an attribute (`#[doc = "..."]`) or in code names the module as before.
The files of every other extension language (`.c`, `.pyx`, `.so`, ...) are read as before, comments
included.

**Reason.** EE holds 13 imports of `datamimic_ee.native` as `outside_write`. Measured: the only word
that names the module in an extension file is one comment, `src/fastops.rs:5`
(`// ... Python calls datamimic_ee.native.`). The compiled module of EE is `datamimic_ee_native`; the
module `datamimic_ee.native` is a Python facade in the scan (`datamimic_ee/native.py`, a literal
`__all__`, re-exports from the extension). Replacing the word in the comment removes the 13 holds
and changes nothing else (EE: 223 UNKNOWN, 256 PASS before and after).

**Limit.** A comment cannot import a module, so the skip loses no write. An extension source that
does name the module in code still escapes it, and the frame still names the module and not the
extension file (a follow-up).

**Tests.** `outside_tests.rs`: eight comment forms that name no module; twelve forms of code (a string
with `//`, raw strings, nested block comments, character literals, lifetimes, an attribute string)
that still name it; a C comment that still names it. Removing the lexer fails the first test.
