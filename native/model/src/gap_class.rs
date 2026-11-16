// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The class of each gap and the facts that a gap with an effect leaves unknown (AD-564).
//!
//! A collector can state what one gap leaves unknown (`GapEffect`). A gap without a statement
//! leaves the whole scope unknown, as before. This file gives each gap its class one time, when
//! the graph reads the reply. It reads no contract: `gap_effects.rs` gives the rules that a gap
//! with an effect holds.
//!
//! Each doubt goes to the wider class, so a statement can only make a verdict less certain: a
//! gap with an effect that names no module, or a module that the reply does not have, or that
//! also has the form of a gap between two modules, leaves the whole scope unknown.

use std::fmt;

use archkeel_facts::data::{GapData, GapEffect};
use archkeel_facts::envelope::Coverage;

use crate::coverage::{data_of, droppable};

/// How much one gap leaves unknown.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Class {
    /// The whole scope: no rule has a scope proof.
    Whole,
    /// The edge between two modules (AD-357): `pair_gaps.rs` gives the rules that it holds.
    Pair,
    /// The stated effect: `held` gives the rules that it holds.
    Effect,
}

/// The class of each gap of the coverage, in the order of the reply.
pub(crate) fn classes(coverage: &Coverage, is_module: impl Fn(&str) -> bool) -> Vec<Class> {
    coverage
        .gaps
        .iter()
        .map(|gap| class(data_of(&gap.data), &is_module))
        .collect()
}

fn class(data: &GapData, is_module: &impl Fn(&str) -> bool) -> Class {
    let pair = droppable(data);
    let Some(effect) = &data.effect else {
        return if pair { Class::Pair } else { Class::Whole };
    };
    let named = match effect {
        GapEffect::Edges { sources: names }
        | GapEffect::Modules { modules: names }
        | GapEffect::Layout { modules: names } => {
            !names.is_empty() && names.iter().all(|name| is_module(name.as_str()))
        }
        GapEffect::EveryModule => true,
    };
    if named && !pair {
        Class::Effect
    } else {
        Class::Whole
    }
}

/// One gap with an effect: its id and its effect.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct EffectGap {
    pub(crate) id: String,
    pub(crate) effect: GapEffect,
}

/// The gaps with an effect, in the order of the reply.
pub(crate) fn effect_gaps(coverage: &Coverage, classes: &[Class]) -> Vec<EffectGap> {
    coverage
        .gaps
        .iter()
        .zip(classes)
        .filter(|(_, class)| **class == Class::Effect)
        .filter_map(|(gap, _)| {
            Some(EffectGap {
                id: gap.id.as_str().to_owned(),
                effect: data_of(&gap.data).effect.clone()?,
            })
        })
        .collect()
}

/// Facts that a gap leaves unknown and that a rule reads.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Doubt {
    /// The import edges that leave this module.
    Edges(String),
    /// The code of this module: its import edges, its members and its constructs.
    Code(String),
    /// The code of every module.
    EveryModule,
    /// The file and the place in the layout of this module.
    Layout(String),
}

impl Doubt {
    /// The stable word of the doubt: it holds no gap id and no position (AD-546).
    pub fn word(&self) -> String {
        match self.parts() {
            (word, _, Some(module)) => format!("{word}: {module}"),
            (word, _, None) => word.to_owned(),
        }
    }

    /// The word, the text and the module of the doubt: one table for `word` and `Display`.
    fn parts(&self) -> (&'static str, &'static str, Option<&str>) {
        match self {
            Doubt::Edges(module) => ("edges", "the import edges of", Some(module)),
            Doubt::Code(module) => ("modules", "the code of", Some(module)),
            Doubt::EveryModule => ("every_module", "the code of every module", None),
            Doubt::Layout(module) => ("layout", "the file and the layout of", Some(module)),
        }
    }
}

impl fmt::Display for Doubt {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self.parts() {
            (_, text, Some(module)) => write!(formatter, "{text} {module}"),
            (_, text, None) => formatter.write_str(text),
        }
    }
}

/// The gaps with an effect that hold a rule or the run: their ids, in the order of the reply,
/// and the facts that they leave unknown, sorted and distinct. It is a reason, not a proof: it
/// can only make a rule UNKNOWN.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Scoped {
    ids: Vec<String>,
    doubts: Vec<Doubt>,
}

impl Scoped {
    /// The id of each gap that holds the rule.
    pub fn ids(&self) -> &[String] {
        &self.ids
    }

    /// The facts that the gaps leave unknown and that the rule reads.
    pub fn doubts(&self) -> &[Doubt] {
        &self.doubts
    }
}

impl Scoped {
    /// The gaps `ids` and the facts `doubts` that they leave unknown, or `None` for no gap.
    pub(crate) fn of(ids: Vec<String>, doubts: Vec<Doubt>) -> Option<Scoped> {
        (!ids.is_empty()).then_some(Scoped { ids, doubts })
    }

    /// `{count} gaps leave unknown what the rule reads: ...` (`1 gap leaves` for one) with at most
    /// `limit` doubts, and
    /// the number of the doubts that it does not show.
    pub(crate) fn write(&self, formatter: &mut fmt::Formatter<'_>, limit: usize) -> fmt::Result {
        let shown: Vec<String> = self
            .doubts
            .iter()
            .take(limit)
            .map(Doubt::to_string)
            .collect();
        let count = match self.ids.len() {
            1 => "1 gap leaves".to_owned(),
            many => format!("{many} gaps leave"),
        };
        write!(
            formatter,
            "{count} unknown what the rule reads: {}",
            shown.join(", ")
        )?;
        match self.doubts.len() - shown.len() {
            0 => Ok(()),
            more => write!(formatter, " and {more} more"),
        }
    }
}

#[cfg(test)]
#[path = "gap_class_tests.rs"]
mod tests;
