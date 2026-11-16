// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What a gap leaves unknown, as typed data (AD-564).
//!
//! A collector writes three sorts of facts for each module: its file and its name, the import
//! edges that leave it, and its code (its members, its positions and its constructs). An effect
//! names the facts that can differ from the truth because of one gap. A rule whose reading does
//! not meet the effect of a gap can be decided with that gap.
//!
//! A gap without an effect leaves the whole scope unknown, also the set of the files. So a
//! collector that states no effect never makes a verdict weaker.

use crate::ids::ModuleName;

/// The facts that one gap leaves unknown. Each variant leaves the files of the scan and the
/// names of their modules known.
#[derive(
    Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize, schemars::JsonSchema,
)]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
pub enum GapEffect {
    /// The import edges that leave each module of `sources` are not complete: an edge to any
    /// module or package can be absent. The code of each module is known.
    Edges {
        /// The modules whose outgoing edges are not complete.
        sources: Vec<ModuleName>,
    },
    /// The code of each module of `modules` is not known: its import edges, its members, its
    /// positions and its constructs.
    Modules {
        /// The modules whose code is not known.
        modules: Vec<ModuleName>,
    },
    /// The code of every module is not known: an import of any module can give another module
    /// than the one that it names.
    EveryModule,
    /// The file and the place in the layout of each module of `modules` are not proven: a rule
    /// on the files of the scan cannot judge them. Their code is read and known.
    Layout {
        /// The modules whose file and place in the layout are not proven.
        modules: Vec<ModuleName>,
    },
}
