# AD-726: An empty written class inventory needs a receipt

## Status

Accepted for the Python survey; part of the `symbol_placement` port in #619.

## Decision

A Python file may state `class_inventory_empty: true` only when the collector proves that
the file contains no written class declaration and has a bounded module body. The collector
withholds this receipt for class statements at any nesting depth, decorators or eagerly
evaluated function headers at module scope, star imports, namespace exposure, dynamic class
or code operations, and a cross-module namespace write or import hazard in the scan.

An absent receipt means unread, not empty. Other collectors and older replies do not claim it.
This is a statement about the inventory of written declarations; it does not claim that no
runtime object can be a class. A later placement rule must also retain the scope and coverage
proofs that apply to the selected modules.

## Checks

`stable_tests.rs` checks the receipt and its absence for nested and conditional classes,
namespace writes, dynamic class construction, star imports and unsafe function headers.
