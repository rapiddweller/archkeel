// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-model, slice 0b of WP6 (AD-363, epic #880).
//!
//! The model is the typed derivation of one run: the components of the contract and, slice by
//! slice, the modules, packages, edges, cycles and the scope proof of the reply. This skeleton has
//! the ids, the tables, the components and the vocabulary of a decision:
//!
//! - `Verdict` and `Decision`: a PASS needs a `ScopeComplete` proof of the same model, and only
//!   the scope of this crate makes one (`Model::scope`, `Scope::complete`). `Verdict::Pass`
//!   holds a mark that only this crate makes.
//! - `Reason` and `Unsupported`: a part that no slice has ported answers with its name, never
//!   with an empty result.
//! - `Section`: the 20 compared sections of `architecture.json` and the slice that ports each.
//! - Slice S1: the modules and packages of the reply, the one owner of each module, the modules
//!   that a rule source selects, and what the reply proves not seen (`Incomplete`).
//! - Slice S2: the resolved imports with their typed targets, the module and package edges, the
//!   unresolved imports that no gap names, and the settings that the shell sends (`Settings`).
//! - Slice S3: the condensation ranks of the edges, modules and packages, the fan counts with the
//!   macro bodies (`Measure`) and the module and package cycles (`Cycle`). The part
//!   that needs no contract is the `Graph`; a run derives it one time and moves it into the model.
//!
//! - Slice S4: the scope proof (`proof.rs`, AD-378): the causes that make the scope of a run
//!   incomplete in the reference engine (pair gaps, the work tree, the runtime, the producer, the
//!   profile limits, the subject check of every rule), made one time per model, and the receipt
//!   and the undecided positions of each rule (`Scope::complete`).
//!
//! - Slice S5: the import matchers of the direction kinds (`direction.rs`, AD-380): one matcher
//!   per kind serves the violations of the evaluator and the undecided positions of the scope
//!   proof, and the receipt and the dynamic import reach of each direction kind.
//!
//! - Slice S7: the scan roots that the shell sends, bound to the scope of the reply; the cycle
//!   receipts and the receipt of `complete_requires` that read them (`receipts.rs`); the
//!   component cycles (`component_cycles.rs`); and the rules that each kept pair gap can change
//!   (`pair_gaps.rs`, AD-384).
//! - The tree (`tree.rs`, AD-385): one model for each contract of an inside-contract tree, with
//!   the source domain of its mount and the one scope state of the tree.
//!
//! The model names no language: a rule of the native contract and a test check that.

#![deny(unreachable_pub)]

mod construct_match;
pub use construct_match::matches as construct_matches;
mod constructs;
pub use constructs::{ConstructMatch, ConstructSite};

#[cfg(test)]
mod construct_tests;

#[cfg(test)]
mod construct_replay_tests;

mod closed_path;
mod condensation;
mod coverage;
mod cycles;
mod edges;
mod gaps;
mod graph;
mod ids;
mod imports;
mod interface;
pub use interface::interface_crossings;
mod model;
mod modules;
mod needs;
pub use needs::{Need, Needs};
mod ownership;
mod reason;
mod scope;
mod section;
mod settings;
mod sides;
mod symbol_sites;
mod symbol_table;
mod symbol_values;
mod symbols;
pub use symbols::Symbols;
mod topology;
mod uml;
mod uml_details;
mod uml_facts;
mod uml_scope;
mod uml_scope_symbols;
mod uml_symbols;
mod verdict;

pub use coverage::Incomplete;
pub use cycles::Cycle;
pub use edges::{Edge, Level};
pub use graph::Graph;
pub use ids::{ComponentId, Id, ModuleId, PackageId, Table};
pub use imports::{Import, Resolved};
pub use model::{Model, Rows};
pub use modules::{Module, Package};
pub use ownership::{claims, in_scope};
pub use reason::{Hygiene, Input, Reason, Refusal, UmlGap, Unsupported};
pub use scope::{Scope, ScopeComplete};
pub use section::{Porting, Section, Slice};
pub use settings::{Producer, Settings, STANDARD_LIBRARY_LIMIT, STANDARD_NAME_LIMIT};
pub use topology::Measure;
pub use uml::{compare as compare_uml, UmlDiff, UmlOutcome, UmlTarget};
pub use verdict::{Decision, Proven, Verdict};

// Slice S4: the scope proof (AD-378).
mod causes;
mod limits;
mod observed;
mod proof;
mod subjects;

pub use causes::{Cause, InterfaceGap, Part};

// Slice S5: the import matchers of the direction kinds and the sides they share (AD-380).
mod direction;
mod selection;

pub use direction::{crossings, forbidden, peers, Crossing, Judged};
pub use selection::{dependency_sides, layer_components, Selection};

// The run proof (lead decision L-35b, AD-381).
mod run;

pub use run::{RunComplete, RunGap, RunPass};

// Slice S7: the scan roots, the cycle receipts, the component cycles and the rules that each
// pair gap can change (AD-384).
mod brand;
mod component_cycles;
mod dropped_gaps;
mod pair_gaps;
mod receipts;
mod roots;

pub use causes::{Held, HELD_SHOWN};
pub use closed_path::{cycle_path, Link, Step};
pub use component_cycles::{cycles_of_components, ComponentCycle};
pub use gaps::CoverageGap;
pub use pair_gaps::{reads, Reads};
pub use receipts::{GapScope, ScanProof};
pub use sides::{shape, Direction, Shape};

// The models of an inside-contract tree (AD-385): one model for each contract of the tree.
mod domain;
mod tree;

pub use tree::ModelTree;
