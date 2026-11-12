// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The settings of one TSConfig with what it inherits.
//!
//! `config.rs` builds a layer, `discover.rs` reads its file specs and `options.rs` turns it into
//! `Options`. The type is here so that none of the three needs the others for it.

use std::collections::BTreeMap;

use serde_json::{Map, Value};

/// The compiler placeholder for the directory of the root TSConfig.
pub(crate) const CONFIG_DIRECTORY: &str = "${configDir}";

/// The settings of one TSConfig with what it inherits, its paths relative to the snapshot.
#[derive(Clone, Debug, Default)]
pub struct Layer {
    pub compiler: Map<String, Value>,
    /// `files`, `include` and `exclude` of the nearest config that sets each.
    pub specs: BTreeMap<&'static str, Vec<String>>,
    /// `outDir` and `declarationDir`, which exclude by default.
    pub outputs: BTreeMap<&'static str, Option<String>>,
    /// The directory of `baseUrl`, and of the config that sets `paths`.
    pub base_url: Option<String>,
    pub paths_directory: String,
    /// A setting that changes resolution could not be read.
    pub partial: bool,
}
