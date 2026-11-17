// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the survey sees of each written construct (AD-737). A `forbidden_construct` rule passes on
//! the absence of a construct only when the reply states the construct `supported` (the model
//! reads `ConstructSupport`). The survey starts each construct `supported`, and each form that can
//! hide the construct downgrades it to `partial`. The support of the run is the meet of the
//! support of each module: one module that cannot be seen completely makes the construct partial.

use std::collections::BTreeMap;

/// A written construct of the reply, in the order of the reply (AD-658, AD-666, AD-680, AD-682,
/// AD-684, AD-686).
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) enum Construct {
    Assert,
    BroadExcept,
    DunderDict,
    Vars,
    StringLiteralCompare,
    Getattr,
    AnyAnnotation,
    DynamicImport,
    Cast,
    TypeIgnore,
}

impl Construct {
    /// Each construct, in the order of the reply.
    pub(crate) const ALL: [Construct; 10] = [
        Construct::Assert,
        Construct::BroadExcept,
        Construct::DunderDict,
        Construct::Vars,
        Construct::StringLiteralCompare,
        Construct::Getattr,
        Construct::AnyAnnotation,
        Construct::DynamicImport,
        Construct::Cast,
        Construct::TypeIgnore,
    ];

    /// The word of the construct in the reply and in the contract.
    pub(crate) fn word(self) -> &'static str {
        match self {
            Construct::Assert => "assert",
            Construct::BroadExcept => "broad_except",
            Construct::DunderDict => "dunder_dict",
            Construct::Vars => "vars",
            Construct::StringLiteralCompare => "string_literal_compare",
            Construct::Getattr => "getattr",
            Construct::AnyAnnotation => "any_annotation",
            Construct::DynamicImport => "dynamic_import",
            Construct::Cast => "cast",
            Construct::TypeIgnore => "type_ignore",
        }
    }
}

/// How completely the survey sees one construct. The order is the order of the meet: `Partial`
/// wins.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) enum Seen {
    /// Each site of the construct is a record: its absence is proven.
    Supported,
    /// A form can hide a site: its absence is not proven.
    Partial,
}

impl Seen {
    fn word(self) -> &'static str {
        match self {
            Seen::Supported => "supported",
            Seen::Partial => "partial",
        }
    }
}

/// The support of each construct, keyed by construct.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Support(BTreeMap<Construct, Seen>);

impl Support {
    /// The support before a module is read. A typing signal is never seen completely: an
    /// annotation can name `Any` through an alias or a string, and an import call can be built
    /// from any text, so these two start partial.
    pub(crate) fn start() -> Support {
        let seen = |c: Construct| match c {
            Construct::AnyAnnotation | Construct::DynamicImport | Construct::Cast => Seen::Partial,
            Construct::Assert
            | Construct::BroadExcept
            | Construct::DunderDict
            | Construct::Vars
            | Construct::StringLiteralCompare
            | Construct::Getattr
            | Construct::TypeIgnore => Seen::Supported,
        };
        Support(Construct::ALL.iter().map(|c| (*c, seen(*c))).collect())
    }

    /// A form that can hide a site of the construct.
    pub(crate) fn downgrade(&mut self, construct: Construct) {
        self.0.insert(construct, Seen::Partial);
    }

    /// The support of two parts together: each construct is the worse of the two.
    pub(crate) fn meet(&mut self, other: &Support) {
        for (construct, seen) in &other.0 {
            let mine = self.0.entry(*construct).or_insert(*seen);
            *mine = (*mine).max(*seen);
        }
    }

    /// How completely the survey sees the construct.
    pub(crate) fn of(&self, construct: Construct) -> Seen {
        self.0.get(&construct).copied().unwrap_or(Seen::Partial)
    }

    /// The construct capabilities of the reply: each construct with its word, in reply order.
    pub(crate) fn reply(&self) -> Vec<(&'static str, &'static str)> {
        Construct::ALL
            .iter()
            .map(|c| (c.word(), self.of(*c).word()))
            .collect()
    }
}

#[cfg(test)]
#[path = "support_tests.rs"]
mod tests;
