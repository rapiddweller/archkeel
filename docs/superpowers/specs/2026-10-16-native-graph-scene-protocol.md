# Native graph scene protocol design

Base: d08dfaf6a2e6992153a434341465306a88d993a2. Part of expanded #542.

## Intent and accepted scope

The real native graph projection becomes a precisely typed consumer while keeping offline report behavior, graph identity and transport text unchanged. Root accepted this bounded slice on 2026-10-16 after the isolated TypeScript 5.9.3 string-enum feasibility proof. Atlas hydration/scenes, UI routes and DOM filters remain explicit later slices.

## Ownership and data flow

Canonical graph vocabularies stay in archkeel.ir.architecture_graph. A small generator imports only the Enum classes actually consumed by native graph scenes and emits nominal TypeScript string enums plus concrete Map-based membership predicates. It never repeats member spellings by hand. TypeScript5.9.3 is already the compiler pin in Makefile. Compilation produces an ordinary classic script shipped with the Python package; no runtime Node or bundler is required. The actual report/graph ingress owns decoding; existing JSON serialization owns output. Per-enum decode/encode wrappers have no product consumer and are deliberately omitted.

The concrete graph protocol defines only fields consumed by this scene boundary. Structural predicates inspect unknown input and validate closed fields through generated Maps. Successful decoding returns the original object, not a cast or copy. Genuine JavaScript typeof grammar is a private protocol-owned enum; it is not a renamed raw constant. IDs, names, paths, labels and actor data remain text.

Existing scene.create delegates native graph operations to a checked report-graph-scene.js owner. That owner contains the existing graph index, containment, member formatting, assessments and complete native projection. Existing graphIndexes remains the index; there is no new cache framework. The original observed/target graphs are decoded once at create. A separately supplied graph is validated once before the existing index is built. Enums are primitive wire-identical strings, so existing Flow, CSS and Mermaid consumers retain values and object identity without output adapters or graph copies.

The generated protocol artifact is loaded before the native graph scene and the existing scene script. Original report-scene.js retains Atlas hydration/scenes, search and Mermaid serialization; it no longer duplicates the extracted native operations.

## Proof boundaries

Strict checkJs checks the actual extracted JavaScript consumer and its concrete ports. Authored source mutations must reject a raw enum-field value, a different enum with identical PASS spelling and a widened real return. Runtime tests require unknown origin/kind/status rejection, input identity and unchanged full JSON. String-enum literals do not establish native absence of raw control comparisons: the independent JS/TS construct increment remains PARTIAL, and this change makes no whole-browser/native absence claim.

## Compatibility and cost

Keep schema-valid legacy graph data and all existing As-Is/Target/Diff rendering, navigation, filters and Mermaid text. Keep the existing Atlas clone boundary. Do not clone or serialize a second graph on initialization or render. Packaging tests must prove compiled assets are shipped; a deterministic regeneration check must reject stale generated source or compiled output. Record handwritten source, moved source and generated artifacts separately; record initialization/projection timing with the same report data before and after.
