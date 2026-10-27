# AD-274 `types` adds globals, and a project declaration publishes its name

**Decision.** This amends AD-261.
1. `compilerOptions.types` and `typeRoots` no longer turn the standard-global catalog off. The
   catalog that `target` and `lib` give stays proven. A name that a types package adds
   (`process`, `__dirname`, `describe`) is not in the catalog. It stays a gap, unless rule 2
   publishes it. `noLib`, an unsupported `lib` and `libReplacement` still turn the catalog off.
2. A top-level `declare var|let|const|function|class|namespace|enum NAME` in a scanned script file
   (no top-level `import` or `export`), and the same inside a `declare global { }` block, publishes
   NAME as a project-declared host global. A use of NAME resolves with the declaration as its
   evidence (file and line). No import edge and no runtime publisher are invented.
3. `/// <reference types="vite/client" />` is observed as a `types` entry. It creates no gap. The
   names it adds follow rule 1.

**Premise.** The project type-checks. TypeScript reports a conflicting redeclaration of a lib
value, so a types package cannot give `Math` another meaning in a project that compiles. A project
that does not compile may get a wrong catalog. This is a documented limit.

**Reason.** #682. Peter's Vite app (402 files) reports 2,688 gaps. With `"types": []` it reports 28,
so rule 1 removes 2,660 (`Math`, `Date`, `document`, `Number`, ...). The Vite React template sets
`"types": ["vite/client"]`, so most Vite apps hit this. Rule 2 removes the 8 gaps for
`__APP_VERSION__`, which `src/vite-env.d.ts` declares; we reproduced it on a small project.
Rule 3 removes one gap. Peter's second suggestion, the `fetch` gaps, is not a catalog defect: the
catalog holds `fetch`, and the gaps appear only because one module assigns `window.fetch`.
That gap is correct and stays.

**Rejected.**
- Read the declarations of each types package at scan time: `node_modules` is not in a git
  snapshot, so the result would change with the install state of the machine.
- Keep `types` unmodeled: every Vite app then has thousands of false gaps.
- Treat every undeclared global as published: it hides a real undeclared global.

**Kept conditions.** Today `_script_standard_global` proves a standard name only when no publisher
exists, the config is not partial, no scanned file has a syntax error, no scanned script binds the
name, and nothing writes to it (`window.fetch = ...`). A project declaration (rule 2) obeys the same
conditions. A declaration is not a publisher, so a second declaration of the name does not conflict.

**Also.** A vendored classic-browser script is no longer blocked by `types` or `typeRoots`. A
types package adds declarations only; the vendor proof rests on the bundle bytes.

**Not changed.** `window.fetch = ...` and `window` as a default parameter value keep their gap
("Escaped or computed global host dependency"). An `open` gap that Peter reports could not be
reproduced; we asked for the two modules.

**Check.** Each class has a test on a small project:
- `types` absent, `[]`, one entry, several entries, `typeRoots` only: `Math`, `Date` and `document`
  are proven; `process` stays a gap. `libReplacement`, `noLib` and an unsupported `lib` keep the
  catalog off.
- Declaration kinds `var`, `let`, `const`, `function`, `class`, `namespace`, `enum` in a script
  `.d.ts` publish their name. A `declare const` in a module without `declare global` is local and
  publishes nothing. Two declarations of one name do not conflict.
- A declaration and a runtime publisher of the same name: the existing rule decides. A syntax error in
  any scanned file, a script that binds the name, and a write to the name still withhold the proof.
- Peter's `tsconfig` (`ES2023`, `DOM`, `DOM.Iterable`, three `types` entries) reports no gap for
  the standard globals.
- Regeneration of the catalog does not change (`tools/typescript_libs.py --check`).
