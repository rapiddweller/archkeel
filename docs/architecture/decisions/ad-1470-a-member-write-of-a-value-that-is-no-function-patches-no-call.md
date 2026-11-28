# AD-1470: A member write of a value that is no function patches no call

Status: accepted. Amends #1674 (member patches of a global) and AD-788 (the repository guard).

## Why

Studio held 5 gaps for `document.documentElement.dataset.theme = dark ? "light" : "dark"` (`studio/src/explorer.ts:425`)
and 9 for ELK's `Error.stackTraceLimit = Error.stackTraceLimit = 64` (`elkjs-0.12.0.bundled.js:4690`). Both write a
string or a number into a member. A call of that member runs nothing of the scan. The rule of #1674 already said "a
literal value can be no function", but it read only a bare literal. And the guard for files outside the scan roots
read every member path as a replacement of its first name (`Error`), without the rule of the scan at all.

## Decision

1. One rule, `no_function` (`script_types.rs`): a value can be no function when it is a literal, a choice between such
   values (`c ? "a" : (d ? "b" : "c")`), or an assignment of one (`a = b = 64`). A value from a call, a name, a member, a
   logical `||` or `&&`, or a choice with one such branch stays a possible function. The rule follows at most 16 nested
   values and then reads the value as a possible function.
2. Only a target that is the whole left side of an assignment has the right side as its value (`Tree::gives_no_function`).
   A destructuring target takes a part of the value or a default (`[Math.max = hidden] = ""` runs `hidden`), and a loop
   target takes the values of the loop. They keep the rule of a possible function. The old rule of #1674 had this
   hole for a literal right side; it is closed too.
3. The scan of a file (`script_patch.rs`) and the reader of a file outside the scan roots (`script_outside_forms.rs`) use
   the rule, so the two read one source of truth.
4. The detector for a file outside the scan roots no longer names the first part of a path of two or more names as a
   replaced global when every write of that path gives a value that is no function (`Script::plain_member_paths`). A
   path that any other write gives a possible function stays a replacement. A path of one name stays a replacement:
   `window.open = "x"` still replaces `open`.

## Rejected

- Exempting `dataset`, `Error` or `stackTraceLimit` by name: it decides by a string and hides a real patch of the same
  member.
- Dropping every member path from the detector: a patch through a wrapper alias (`(function (g) { g.Foo.bar = f })(window)`)
  would pass, because the plain reader does not see through the alias.

## Counter-examples (`native/typescript/src/script_member_patch_tests.rs`)

Before the change two tests fail (the choice of literals, the assignment chain); after it they pass.

- Still held: `= pick()`, `= dark ? "light" : hidden`, `= dark ? hidden : "dark"`, `= other.theme`,
  `= (dark ? "a" : "b") || hidden`, `= value = hidden`, in a scanned file and in a file outside the scan roots.
- Still held, scanned and outside: `[M = hidden] = flag ? '' : ''`, `[M = hidden] = ''`, `({ a: M = hidden } = {})`,
  `[M] = [hidden]`, `for (M of [hidden]) {}` with `M = document.documentElement.dataset.theme` (Codex, round 1).
- Still held outside: `Error.stackTraceLimit = 64;` together with `Error.stackTraceLimit = hidden;` (the path has a second
  write), and with `Error.captureStackTrace = hidden;` (another member).

## Not done

A string that is code (`location.href = "javascript:…"`, `el.innerHTML = "<img onerror=…>"`) is still a literal here. It
runs the text of the file, not a function of another module; the text sinks keep their own forms (AD-540).
