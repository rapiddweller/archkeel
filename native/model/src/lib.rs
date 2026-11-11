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
//!   the scope of this crate makes one (`Model::scope`, `Scope::complete`). Until slice S4 it
//!   makes none. `Verdict::Pass` holds a mark that only this crate makes.
//! - `Reason` and `Unsupported`: a part that no slice has ported answers with its name, never
//!   with an empty result.
//! - `Section`: the 20 compared sections of `architecture.json` and the slice that ports each.
//! - Slice S1: the modules and packages of the reply, the one owner of each module, the modules
//!   that a rule source selects, and what the reply proves not seen (`Incomplete`).
//!
//! The model names no language: a rule of the native contract and a test check that.

#![deny(unreachable_pub)]

mod coverage;
mod ids;
mod model;
mod modules;
mod ownership;
mod reason;
mod scope;
mod section;
mod verdict;

pub use coverage::Incomplete;
pub use ids::{ComponentId, Id, ModuleId, PackageId, Table};
pub use model::{Model, Rows};
pub use modules::{Module, Package};
pub use ownership::in_scope;
pub use reason::{Input, Reason, Unsupported};
pub use scope::{Scope, ScopeComplete};
pub use section::{Porting, Section, Slice};
pub use verdict::{Decision, Proven, Verdict};
