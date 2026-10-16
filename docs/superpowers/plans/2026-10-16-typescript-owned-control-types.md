# TypeScript compiler and resolver types implementation plan

> For agentic workers: use superpowers:executing-plans. Existing execution and merging are authorized.

**Goal:** Replace compiler and resolver control strings with types owned by their API components.
**Architecture:** config owns ModuleKind, ModuleResolution and ScriptTarget, converting TSConfig values once. resolve owns ModuleFormat, SourceKind and package protocol conversion; collect consumes these types. Source paths, specifiers and JSON object keys remain data.
**Tech Stack:** Python 3.11+, enum, frozen dataclasses, pytest, native Archkeel.
**Spec:** issue #542 and the explicit user requirement that parser/protocol strings are included.

## Global constraints
Preserve TypeScript 5.9.3 reference behavior, defaults, wire bytes and unsupported/unknown outcomes. Do not increase baseline budgets or change the construct collector. Keep parse.py outside the completed migration claim.

## Review focus
- Case-insensitive options and the node alias normalize once.
- Unknown values remain partial with the same diagnostics.
- Package conditions preserve ordering and unknown-condition refusal.
- Extension substitution and Node10/ESM precedence remain unchanged.
- Annotations and native guard fail on actual source mutations against independently authored intent.

### Task 1: Compiler/resolver API migration
- [ ] Add tests pinning nominal option fields, derived returns, package format and source kinds.
- [ ] Run hosted RED on the unchanged implementation.
- [ ] Add owner-local enum types and convert once at input boundaries; update consumers and existing assertions.
- [ ] Run TS configuration, resolution, collection and compiler differential tests.
- [ ] Add independent bounded Target and native source-mutation controls, with native guard for migrated protocol dispatch.
- [ ] Run Ruff, mypy, hygiene and native baseline; apply hosted format changes.
- [ ] Deliver intended product file list and clean commit to parent for independent Astra review and integration.
