# AD-261 TypeScript standard globals come from TypeScript's own lib files

**Decision.**
- A JSX attribute name (`className`, `onClick`, `data-x`) names a prop. It is never
  a reference to a binding, so it creates no site. A variable with the same name still does.
- The standard-global catalog is generated, not typed. `tools/typescript_libs.py` reads the
  `lib.*.d.ts` files of the pinned `typescript` package (`tools/browser-runtime`) and writes
  `src/archkeel/analyzer/typescript/standard_libs.py`. Per lib file it records the top-level
  `declare var|function|class|namespace|const|let` names, closed over `/// <reference lib>`.
- A `lib` entry resolves to that file by its compiler name (`es5`, `es2015` to `es2024`,
  `esnext`, `dom`, `dom.iterable`). A name outside the pinned set still leaves the
  environment unmodeled, as today.
- When `lib` is absent, the environment is the compiler's default for the target: `lib.d.ts`
  for ES5, otherwise the target's `lib.es20xx.full.d.ts`. That includes DOM.
- Unchanged: `noLib`, `types`, `typeRoots` and `libReplacement` leave the environment
  unmodeled, because ambient declarations may redefine a global.

**Reason.** #682: a Vite/React app (493 files) reports 15,646 gaps. Two causes are separate
from import resolution. Attribute names were collected as free references once ES modules took
part in global handling (94bf278e). And the Vite template's `lib: [ES2020, DOM, DOM.Iterable]`
names two libraries the catalog does not know, so `Math`, `Date` and `document` stay unproved.
The hand-typed DOM list holds 22 names (no `console`); `lib.dom.d.ts` declares 874. A
catalog typed by hand cannot follow the compiler, and the compiler's files are its source.

**Rejected.**
- Map every `ES20xx` to the ES2022 table: it proves `WeakRef` under `lib: es2020`.
- Extend the hand list: it is never complete and drifts from the compiler.
- Ask `tsc` at scan time: it needs Node, and its answer changes with the installed version.
- Treat every global in an ES module as proved: it hides a real undeclared global.

**Limit.** The catalog follows the pinned TypeScript version. A newer `lib` name is
unmodeled until the pin moves. Only top-level values count; types such as `Document` do not.

**Check.**
- `tools/typescript_libs.py --check` regenerates the module and fails on any difference.
- A Vite-style `tsconfig` (`ES2020`, `DOM`, `DOM.Iterable`) with a JSX module reports no
  "Script global" gap for `className`, `Math`, `Date`, `document` or `console`.
- The same file under `lib: ["es5"]` keeps `document` as a gap; `lib: ["es2020"]` does not
  prove `WeakRef`.
- A local `const title` used as `title` is still a reference; the attribute `title=` is not.
- A project with no `lib` and target ES2022 proves `document`.
- `make against` accepts the contract entries for the new modules.
