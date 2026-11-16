// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-contract, slices 0c-1 and 0c-2 of WP6 (AD-359, epic #880).
//!
//! The crate parses the bytes of one architecture contract into typed and closed structures. It
//! accepts and rejects what the Python parser (`ir/codec_contract.py`) accepts and rejects, with
//! the same error kind, and writes the same canonical bytes. It reads no file: the shell sends the
//! bytes. It evaluates nothing, and it does not depend on `archkeel-facts`, so a Target id can
//! never be a source id.
//!
//! It covers the whole grammar of `parse_contract`: components, the 22 rule kinds and the
//! `declarations` object with its UML Target and the checks of `declared_graph`.

#![deny(unreachable_pub)]

#[macro_use]
mod macros;
mod boundary;
mod budgets;
mod canonical;
mod component;
mod construct;
mod contract;
mod declarations;
mod dependency;
mod document;
mod door_reach;
mod error;
mod graph;
mod graph_check;
mod graph_link;
mod json;
mod model;
mod model_constructs;
mod model_declarations;
mod model_rules;
mod model_uml;
mod names;
mod paths;
pub mod policy;
mod python_rules;
mod read;
mod rule;
mod rules;
mod structure;
mod uml;
mod uml_merge;
mod unused_public;
mod version;
mod words;

pub use canonical::canonical_bytes;
#[cfg(test)]
pub(crate) use canonical::canonical_digest;
pub use contract::parse;
pub use document::{Contract, ParsedContract};
pub use door_reach::DoorReach;
pub(crate) use error::ErrorKind;
pub use graph::uml_target_id;
pub use graph_link::bare_reference;
pub use model::{
    CompleteRequires, Component, ComponentLabel, CycleLevel, DecidedBy, ExternalDependencyScope,
    ForbiddenDependency, InterfaceBoundary, LayerOrder, Lifecycle, NoComponentCycles, Package,
    RootLayout, RuleKind, Selector, SelectorMatch, SiblingIsolation, SourceRule, TargetKind,
};
pub use model_constructs::{ConstructSelector, ForbiddenConstruct};
pub use model_declarations::BudgetName;
pub use model_rules::{BoundaryAllowance, BoundaryTypes};
pub use unused_public::{ExternalUser, PublicItemKind, UnusedPublic};
pub use model_uml::{
    CompletenessMode, Entity, EntityKind, ModifierKind, ParameterKind, PresenceKind, Relationship,
    RelationshipKind, ResolutionKind, Signature, Target, TargetScope, VisibilityBasis,
    VisibilityKind,
};
pub use rule::{head_of, kind_of, Rule};
pub use uml_merge::merge_targets;
