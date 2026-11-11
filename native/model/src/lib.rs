// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-model, slice 0b of WP6 (AD-363, epic #880).
//!
//! The model is the typed derivation of one run: the components of the contract and, slice by
//! slice, the modules, packages, edges, cycles and the scope proof of the reply. This skeleton has
//! the ids, the tables, the components and the vocabulary of a decision:
//!
//! - `Verdict` and `Decision`: a PASS needs a `ScopeComplete` value, and only the scope proof of
//!   this crate makes one (`Model::scope_complete`). Until slice S4 it makes none.
//! - `Reason` and `Unsupported`: a part that no slice has ported answers with its name, never
//!   with an empty result.
//! - `Section`: the 20 compared sections of `architecture.json` and the slice that ports each.
//!
//! The model names no language: a rule of the native contract and a test check that.

#![deny(unreachable_pub)]

mod ids;
mod model;
mod reason;
mod scope;
mod section;
mod verdict;

pub use ids::{ComponentId, Id, ModuleId, PackageId, Table};
pub use model::{Model, Rows};
pub use reason::{Reason, Unsupported};
pub use scope::ScopeComplete;
pub use section::{Porting, Section, Slice};
pub use verdict::{Decision, Verdict};
