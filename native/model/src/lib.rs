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
//!
#![deny(unreachable_pub)]

#[macro_use]
mod rule_kinds;
mod construct_match;
pub use construct_match::matches as construct_matches;
mod constructs;

#[cfg(test)]
mod construct_tests;

#[cfg(test)]
mod construct_replay_tests;

mod boundary_facts;
mod boundary_judge;
mod boundary_positions;
mod published;
mod published_items;
pub use published::{unused as unused_public, Unused};
pub use published_items::PublicItem;
mod boundary_surface;
mod facade_reach;
pub use boundary_positions::{read as boundary_reading, Position};
pub use facade_reach::facade_types;

mod closed_path;
mod condensation;
mod coverage;
mod cycles;
mod door_reach;
pub use door_reach::{Applied, DoorProblem, Doors};
mod edges;
mod gap_class;
mod gap_effects;
mod premises;
pub use premises::{
    kind_word, of_kind_word, premise_words, rule_premises, PremiseKind, UsedPremise,
};
mod gaps;
mod graph;
mod ids;
mod imports;
mod interface;
pub use interface::{interface_crossings, interface_publications, publishes};
mod measures;
mod model;
pub use measures::{measure_facts, Measures};
mod modules;
mod needs;
pub use needs::{Need, Needs};
mod ownership;
mod placement;
mod placement_facts;
pub use placement::violations as placement_violations;
mod reason;
mod reason_key;
pub use reason_key::{gap_kind, stable};
mod scope;
mod scope_order;
mod scope_receipt;
mod section;
mod settings;
mod sides;
mod symbol_inventory;
mod symbol_sites;
mod symbol_table;
mod symbol_values;
mod symbols;
mod topology;
mod uml;
mod uml_declared;
mod uml_details;
mod uml_facts;
mod uml_inventory;
mod uml_scope;
mod uml_scope_symbols;
mod uml_symbols;
mod uml_tree;
mod verdict;

pub use coverage::Incomplete;
pub use cycles::Cycle;
pub use edges::{Edge, Level};
pub use graph::Graph;
pub use ids::{ComponentId, ModuleId};
pub use imports::{Import, Resolved};
pub use model::Model;
pub use modules::Module;
pub use ownership::{claims, in_scope};
pub use reason::{Hygiene, Input, Reason, UmlGap, Unsupported};
pub use section::Section;
pub use settings::{Producer, Settings};
pub use uml::{UmlDiff, UmlOutcome, UmlTarget};
pub use uml_declared::{UmlDeclared, UmlPart};
pub use uml_tree::compare_tree as compare_uml_tree;
pub use verdict::{Decision, Verdict};

// Slice S4: the scope proof (AD-378).
mod causes;
mod limits;
mod observed;
mod proof;
mod subjects;

pub use causes::{Cause, Part};

// Slice S5: the import matchers of the direction kinds and the sides they share (AD-380).
mod direction;
mod selection;

pub use direction::{crossings, forbidden, peers, Judged};

// The run proof (lead decision L-35b, AD-381).
mod run;

pub use run::{RunGap, RunPass};

// Slice S7: the scan roots, the cycle receipts, the component cycles and the rules that each
// pair gap can change (AD-384).
mod brand;
mod component_cycles;
mod dropped_gaps;
mod pair_gaps;
mod receipts;
mod roots;

pub use closed_path::{cycle_path, Link};
pub use component_cycles::cycles_of_components;

pub use gaps::CoverageGap;
pub use sides::{shape, Shape};

// The models of an inside-contract tree (AD-385): one model for each contract of the tree.
mod domain;
mod tree;

pub use tree::ModelTree;
