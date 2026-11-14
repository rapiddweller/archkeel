// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the definition table (AD-377) and the symbol declarations of the survey (AD-514) read in
//! the same way: the parameters of a function as text, the visibility of a name and the id of a
//! definition. Each caller brings its own writer of text.

use archkeel_facts::identity::{stable_id, Part};

use crate::module::definition::Def;
use crate::module::{Location, Module};

mod parameters;

pub(crate) use parameters::{signature, visibility};

/// `definition_id`: the qualified name and the location of the `def` or `class` keyword.
pub(crate) fn definition_id(module: &Module, def: Def<'_>, qualname: &str) -> String {
    let Location { line, column, .. } = module.location(&def.range(module.text()));
    stable_id(
        "SYM",
        &[
            Part::Text(qualname),
            Part::Text(&module.rel),
            Part::Number(line),
            Part::Number(column),
        ],
    )
}
