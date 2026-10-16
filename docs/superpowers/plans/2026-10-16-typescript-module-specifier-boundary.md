# TypeScript module-specifier boundary implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline for this isolated increment. Root arranges the independent final Astra review before merge.

**Goal:** Classify TypeScript module-specifier grammar once at its resolver-owned input boundary and consume nominal results.

**Architecture:** The resolver owns one frozen ModuleSpecifier record and its plain SpecifierKind enum. Public string-input convenience APIs remain adapters; the collector passes one normalized record through the explicit nominal resolver API and its local-target projection. File suffix/path/glob grammar and Snapshot input roles are separate follow-up increments.

**Tech Stack:** Python 3.11, plain Enum/frozen slots dataclass, existing native Python observation/Target, pinned TypeScript 5.9.3 differential.

**Spec:** docs/architecture/typescript-control-types.md (remaining #542 migration); user request explicitly forbids parser/protocol string comparisons.

## Global constraints

- Existing compiler outputs, deterministic fact IDs, unknown semantics and source/wire bytes must stay unchanged.
- Actual module/path/package identities stay string data; reserved node:/#/@/relative grammar becomes nominal.
- No Final/string-alias or .value comparison bypass, no generic enum factory, no allowance or new observation authority.
- Preserve all #551 Wire, #553 physical-evidence and #558 syntax APIs/guards.
- Baselines only ratchet to measured lower values; final normal v2 amendment and no-write validation bind the actual predecessor.
- Use remote isolated GitHub branches and hosted tests; no executor/filesystem access. Existing user authorization covers implementation/PR; Root owns merge.

## Review focus

- Exact "."/".." are relative, but only "./"/"../" count as a runtime relative prefix.
- node:unknown must preserve the previous fallback behavior rather than becoming an invented builtin.
- Scoped incomplete/empty-segment names such as @scope, @scope/ and @scope/name/sub preserve package/types-package identity.
- Bare data names that merely resemble reserved tokens must keep ordinary package semantics.
- Trailing separators, absolute paths, path-map precedence, package self-references and type-only builtin handling keep compiler behavior.

### Task 1: Author native intent and observe RED

**Files:** tests/test_typescript_module_specifiers.py; tests/test_typescript_control_target.py; docs/architecture/contracts/typescript.json; docs/architecture/typescript-module-specifiers.md.

**Interfaces:** Produce independent authored Target entities for SpecifierKind, ModuleSpecifier.kind and Resolver.resolve_module.specifier. Keep existing39 entities intact.

- [ ] Add native positive API/Target controls against existing source; require proven PASS and inspect the genuine missing-API FAIL before implementation.
- [ ] Add exact behavior cases for node:fs/node:test/node:unknown/fs/test, ./x/../x/./.././../, #imports, scoped names, ordinary names, absolute names and trailing slashes.
- [ ] Add actual-source kind-field/typed-parameter widening mutations against fixed intent bytes.
- [ ] Commit the RED checkpoint and record hosted run IDs.

### Task 2: Implement the owned boundary and its consumers

**Files:** src/archkeel/analyzer/typescript/resolve.py; src/archkeel/analyzer/typescript/collect.py; existing tests/test_typescript_resolve.py where convenience behavior needs explicit coverage.

**Produces:**
- SpecifierKind(Enum): RELATIVE, ABSOLUTE, NODE, PACKAGE_IMPORT, SCOPED_PACKAGE, BARE.
- ModuleSpecifier frozen slots record: text:str, kind:SpecifierKind, payload:str, relative_prefix:bool, directory:bool.
- ModuleSpecifier.parse(text:str)->ModuleSpecifier; builtin:bool, package_name:str, types_package:str computed owned properties.
- Resolver.resolve_module(specifier:ModuleSpecifier, importer:str, mode:ModuleFormat|None, *, prefer_builtin:bool=False)->Found|Unknown|None.
- Existing Resolver.resolve(str,...), is_builtin(str), is_relative(str), package_name(str) remain input adapters over that owner.

- [ ] Implement one real prefix lexer and nominal conversion; unknown ordinary names remain data rather than a known protocol mode.
- [ ] Preserve builtin inventory identity semantics; no protocol-string dispatch leaves the boundary.
- [ ] Route collector _target and _local through one ModuleSpecifier record and resolve_module; private resolver package consumers use the normalized record where they need its grammar.
- [ ] Preserve the difference between relative paths and relative prefixes; preserve all existing priority/fallback ordering.
- [ ] Run RED controls to GREEN, existing resolve/collect/native Target tests, Ruff/mypy/hygiene and the full pinned compiler/differential corpus.

### Task 3: Verify actual guard scope and freeze a clean PR

**Files:** Makefile; docs/architecture/typescript-control-types.md; architecture-baseline.json only if measured reduction; docs/architecture/decisions/issue-542-typescript-module-specifier-amendment.json.

- [ ] Add the new focused tests to existing TS/pr-test lists and update the remaining ledger, leaving file/path/role work explicit.
- [ ] On Root's separately reviewed prefix observer, replay actual source startswith/endswith literal mutations and require trace-valid violations with unchanged contract bytes. Before that observer exists, record this gate as pending; never infer prefix-call PASS from the current Compare-only guard.
- [ ] Run the actual native source baseline without extra allowances and capture exact measured scalars.
- [ ] Generate a normal v2 amendment against the actual integrated predecessor; commit only intended product files.
- [ ] Validate the exact final commit without --write-amendment, publish a separate Part of #542 PR, and freeze its source for Root's independent Astra review.

## Execution ledger

Pre-flight: the collector consumes the same ModuleSpecifier and resolve_module signatures produced by Task2; convenience wrappers retain existing string-input test/API compatibility. No interface conflict.
Ruling: remote GitHub branches/commits and hosted Actions replace local worktree/scripts because the assigned execution environment is GitHub-MCP-only; this preserves isolated ancestry, real RED/GREEN and reviewable final deltas.
Ruling: existing user authorization and Root's explicit instruction to continue remove any extra plan-approval pause; native inline execution and final independent Astra review remain the chosen method.
Task1: pending; no production implementation written.
