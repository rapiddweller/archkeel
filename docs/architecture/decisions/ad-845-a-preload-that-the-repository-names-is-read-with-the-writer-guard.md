# AD-845: A preload that the repository names is read with the writer guard

Status: accepted (lead decision 2026-11-17 on #1750, option 1 with the loader patch). Part of #880.
Closes #1750. It amends AD-788 and AD-798.

## Context
A tool loads an installed package before the code of the scan runs, with no import of the scan:
`node --require preload src/a/a.js`. In the plant of #1750, `node_modules/preload/index.js`
writes `globalThis.open = require("../../src/b/b").hidden`, and component `a` calls
`window.open()`. Node runs the function of `b`, and main `5e023fda0` gave PASS. The printed
assumption of AD-788 ("code outside the scan roots … replaces no global") covers it, but the guard
of AD-788 does not read installed packages, so visible evidence in the repository was silent.
A preload can also patch the module loader and redirect any import.

## Decision
`collect/package_closure.rs` reads each named preload after the imported-package closure of AD-798.
1. **Names.** Each data file of the repository (installed and version-control directories
   excepted) is read for preload names: the flags `-r`, `--require`, `--import`, `--loader` and
   `--experimental-loader` in a `package.json` script, also inside `NODE_OPTIONS=…`; a
   `NODE_OPTIONS` or `node-options` line of an `.npmrc` or `.env*` file; the jest keys
   `setupFiles`, `setupFilesAfterEnv`, `setupFilesAfterEach` and `globalSetup` (`package.json`,
   `jest.config.json`); the mocha key `require` (`package.json`, `.mocharc.json`, `.mocharc.yml`);
   the quoted names of `setupFiles` in a `vitest.config.*`, `vite.config.*` or
   `vitest.workspace.*`; a computed entry is a gap even when the same list has literal entries.
2. **Entries.** Command flags retain their Node load mode (`--require` is CommonJS; `--import` is
   ESM). Runtime resolution ignores TypeScript's `paths` and `baseUrl`, which Node does not apply.
   If a configuration does not establish a mode, both modes must resolve to readable runtime
   source. A type declaration is never accepted as a runtime entry; if the resolver only finds a
   declaration or cannot establish the runtime target, the run is UNKNOWN. Repository-local source
   files named as preloads are entries too. A builtin gives no entry. A name that resolves to no
   file is a gap of the run: "Preload X named in F:L is no installed package that the scan can
   read". An unreadable or malformed JSON config, or a dynamic preload target, is a gap.
3. **Closure and writer guard.** The AD-798 closure of the entries is checked for project-source
   reach and goes to the writer guard of AD-788 (`script_outside::read`). Node loads an installed
   preload as a module, so its top-level bindings are no globals. Each global write withholds its
   proof as in AD-788, and the gap cites the write.
4. **Loader patch.** A closure file with `require.cache` or `.prototype.require` patches the module
   loader. So does `._load`, `._resolveFilename` or `._cache` when a file reaches the module object
   (`require('module')`, an import of `module`, `module.constructor`, `mainModule`, `require.main`).
   Whitespace between call tokens does not change that recognition. A read of such a member counts
   too. A patch can redirect any import, so it is a gap of the run that names the preload, its data
   file and the line of the patch.

## Soundness
Inside the repository, a named preload is read: its global writes and loader patches are no longer
silent. A preload that a tool adds outside the data files (a JavaScript configuration, a command
line outside the repository) stays under the printed assumption of AD-788, which names code outside
the scan roots. A loader patch through a name that the text does not show (`m[k] = f` on the
module object) stays under the same assumption.

## Price
No PASS turns UNKNOWN on graphql-js v16.15.0 and the TypeScript fixtures F, H, H-uml and L-nest
(see the PR). A project that preloads `tsconfig-paths/register` or `module-alias` (they patch
`Module._resolveFilename`) loses every route, which is true: they redirect imports.

## Tests
`tests/test_collector_false_pass_ts_preload.py`: the plant of #1750 through 11 naming places,
runtime-resolution regressions, local and installed loader patches, multi-project dynamic setup
and unknown names hold the rule; a preload with no write, a class with its own `_cache` and a
builtin keep PASS.
`native/typescript/src/preloads_tests.rs`: the readers and fail-closed handling of malformed configs,
dynamic targets, runtime modes and whitespace around the module loader.
