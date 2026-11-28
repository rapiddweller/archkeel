// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the survey sees of each written construct (AD-737). A `forbidden_construct` rule passes on
//! the absence of a construct only when the reply states the construct `supported` (the model
//! reads `ConstructSupport`). The survey starts each construct `supported`, and each form that can
//! hide the construct downgrades it to `partial` in its module. A construct of `PER_MODULE` leaves
//! the run `supported` and names each such module in an `unseen_form` record (#1537); another construct is `partial`
//! for the run when one module cannot be seen completely (the meet of the modules).

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
    Placeholder,
    Hasattr,
    Setattr,
    Delattr,
    Eval,
    Exec,
}

impl Construct {
    /// Each construct, in the order of the reply.
    pub(crate) const ALL: [Construct; 16] = [
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
        Construct::Placeholder,
        Construct::Hasattr,
        Construct::Setattr,
        Construct::Delattr,
        Construct::Eval,
        Construct::Exec,
    ];

    /// The constructs whose hidden forms the survey places in one module (#1537). The reply states
    /// them `supported`, and a module with a form that can hide a site gets an `unseen_form` record, so
    /// only a rule that judges that module is held. The others are
    /// run-wide: `string_literal_compare` needs the type of an operand, `any_annotation` needs the
    /// premise that `typing` is unchanged, and `placeholder_body` has its own coverage.
    pub(crate) const PER_MODULE: [Construct; 13] = [
        Construct::Assert,
        Construct::BroadExcept,
        Construct::DunderDict,
        Construct::Vars,
        Construct::Getattr,
        Construct::DynamicImport,
        Construct::Cast,
        Construct::TypeIgnore,
        Construct::Hasattr,
        Construct::Setattr,
        Construct::Delattr,
        Construct::Eval,
        Construct::Exec,
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
            Construct::Placeholder => "placeholder_body",
            Construct::Hasattr => "hasattr",
            Construct::Setattr => "setattr",
            Construct::Delattr => "delattr",
            Construct::Eval => "eval",
            Construct::Exec => "exec",
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

/// The interpretation of a written placeholder candidate.
#[derive(Clone, Copy)]
pub(crate) enum PlaceholderDecision {
    Declaration,
    Unread,
}

/// How much the placeholder walk can decide.
#[derive(Clone, Copy)]
pub(crate) enum PlaceholderCoverage {
    Complete,
    UsesProtocol,
    Incomplete,
}

/// The support of each construct, keyed by construct.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Support(BTreeMap<Construct, Seen>, bool);

impl Support {
    /// The support before a module is read. A typing signal is never seen completely: an
    /// annotation can name `Any` through an alias or a string, and an import call can be built
    /// from any text, so these two start partial.
    pub(crate) fn start() -> Support {
        let seen = |c: Construct| match c {
            Construct::AnyAnnotation => Seen::Partial,
            _ => Seen::Supported,
        };
        Support(
            Construct::ALL.iter().map(|c| (*c, seen(*c))).collect(),
            false,
        )
    }

    /// A form that can hide a site of the construct.
    pub(crate) fn downgrade(&mut self, construct: Construct) {
        self.0.insert(construct, Seen::Partial);
    }

    /// The run states each construct of `PER_MODULE` `supported`: its modules carry the gaps.
    pub(crate) fn settle(&mut self) {
        for construct in Construct::PER_MODULE {
            self.0.insert(construct, Seen::Supported);
        }
    }

    /// Add the placeholder evidence of a source module.
    pub(crate) fn observe_placeholder(&mut self, coverage: PlaceholderCoverage) {
        match coverage {
            PlaceholderCoverage::Complete => {}
            PlaceholderCoverage::UsesProtocol => self.1 = true,
            PlaceholderCoverage::Incomplete => Self::downgrade(self, Construct::Placeholder),
        }
    }

    /// True when the placeholder inventory is complete under a stable standard library.
    pub(crate) fn placeholder_under_premise(&self) -> bool {
        self.1 && self.of(Construct::Placeholder) == Seen::Supported
    }

    /// The support of two parts together: each construct is the worse of the two.
    pub(crate) fn meet(&mut self, other: &Support) {
        self.1 |= other.1;
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
            .map(|c| {
                let seen = if self.1 && *c == Construct::Placeholder {
                    Seen::Partial
                } else {
                    self.of(*c)
                };
                (c.word(), seen.word())
            })
            .collect()
    }
}

#[cfg(test)]
#[path = "support_tests.rs"]
mod tests;
