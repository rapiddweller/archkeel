// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-contract, slice 0c-1 of WP6 (AD-359, epic #880).
//!
//! The crate parses the bytes of one architecture contract into typed and closed structures. It
//! accepts and rejects what the Python parser (`ir/codec_contract.py`) accepts and rejects, with
//! the same error kind, and writes the same canonical bytes. It reads no file: the shell sends the
//! bytes. It evaluates nothing, and it does not depend on `archkeel-facts`, so a Target id can
//! never be a source id.
//!
//! The parser stops with `ErrorKind::Unsupported` at a part of the grammar that slice 0c-2 ports:
//! the `declarations` object and the ten rule kinds that only the Python profile decides.

#![deny(unreachable_pub)]

mod canonical;
mod component;
mod construct;
mod contract;
mod dependency;
mod error;
mod json;
mod model;
mod names;
mod read;
mod rules;
mod structure;
mod version;
mod words;

pub use canonical::{canonical_bytes, canonical_digest};
pub use contract::parse;
pub use error::{ErrorKind, ParseError, Unported};
pub use model::{
    AllowedDependency, CompleteRequires, Component, ComponentLabel, ComponentRole, ConstructKind,
    ConstructSelector, Contract, ContractDigest, CycleLevel, DecidedBy, ExternalDependencyScope,
    ForbiddenConstruct, ForbiddenDependency, InterfaceBoundary, ItemId, LayerOrder, Lifecycle,
    ModuleObjectGrant, NoComponentCycles, Requirement, RootLayout, Rule, RuleHead, RuleKind,
    SelectorMatch, SelectorRole, SiblingIsolation, SourceRule, TargetKind, TypeIgnore,
};
pub use rules::{head_of, kind_of};
pub use version::{version_text, ContractVersion};
