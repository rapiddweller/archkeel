# AD-325 Every collector process runs in the C locale

**Decision.** `ProcessCollector` sets `LC_ALL=C` in the environment of every collector process.
This applies to the Python, TypeScript, Dart and native collectors. It is a finding of the review
of PR #897, in epic #880.

**Problem.** The tree-sitter scanner calls the C library function `iswspace`. Its answer depends
on the locale. Take the text `const a = 1`, then U+3000, then a line break, then `const b = 2`.
Under `LC_ALL=C` the parser finds one binding. Under `en_US.UTF-8` or `C.UTF-8` it finds two.
The same is true for U+2003, U+2028 and U+2029 before a line break. The native binary never calls
`setlocale`, so it always acts like the C locale. Python sets the locale from the environment at
start (PEP 538 coerces an unset locale to `C.UTF-8`). So on a default Linux or Docker host the
Python collector acted like UTF-8 and the native collector acted like C. The two gave different
facts for the same source.

1. `ProcessCollector.collect_response` builds the child environment from `os.environ` and adds
   `PYTHONDONTWRITEBYTECODE=1` and `LC_ALL=C`. The host does not use an allow-list of variables
   for this environment, and this decision does not add one.
2. `LC_ALL` has precedence over `LANG` and every `LC_*` variable. So `LANG` and `LC_CTYPE` stay
   as the user set them, and they change nothing for the collector.
3. A collector reads and writes bytes and decodes them as UTF-8 by name. Python 3.7 and later
   starts in UTF-8 mode when the locale is `C` (PEP 540). So file names and text that are not
   ASCII keep the same paths and facts under the pinned locale.
4. Windows has no `LC_ALL` semantics: the C runtime ignores the variable. The value is harmless
   there. The end-to-end tests are skipped on Windows for that reason. The environment test runs.

**Rejected.**
- **Call `setlocale` in each collector.** The native binary would need a locale library. Every new
  collector would have to remember the call. One place in the host covers all of them.
- **Make the native collector follow the user locale.** The facts would then depend on the host,
  and a saved report would not be reproducible.
- **Drop `LANG` and `LC_CTYPE` from the child.** `LC_ALL` already overrides them. A longer set
  of variables would add risk and no effect.

**Limit.** The rule covers a collector that the host starts. A collector that a user starts by
hand keeps the locale of the user. A custom `collector_argv` also gets `LC_ALL=C`, but a custom
collector can set its own locale after start. The tests do not cover a collector started by hand
or a custom `collector_argv`. Dart and the native collector are not verified for this divergence.
The oracle of #897 covers the native binary.

**Checked by** `tests/test_collector_locale.py`: the child environment holds `LC_ALL=C` whatever
the user sets; the Python TypeScript collector gives equal facts under a user UTF-8 locale and
under `C` for U+3000, U+2003, U+2028, U+2029 and U+00A0 before a line break; a source tree with a
non-ASCII file name and non-ASCII text keeps its path and facts; and, for U+3000 and U+00A0,
the host gives the facts that the collector entry gives when run directly with `LC_ALL=C`.
