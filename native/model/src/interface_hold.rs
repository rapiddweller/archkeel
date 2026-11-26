// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The causes that hold an `interface_boundary` rule: the missing fact of an import, the class of
//! the cause that the collector states, and the origin of a held module pair (#2086, AD-1170).

use std::collections::BTreeMap;
use std::fmt;

use archkeel_facts::data::{RouteWithheld, SurfaceForm};

/// The largest number of imports that a hold shows.
const HELD_SHOWN: usize = 5;
/// The most held imports that a hold keeps for the frame.
const HELD_KEPT: usize = 20;

/// A missing fact of the interface import verdict, not a lifecycle diagnosis.
#[derive(
    Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, serde::Serialize, schemars::JsonSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum InterfaceGap {
    /// The binding of the import is not read.
    UnreadBinding,
    /// The route by which the target publishes the name is not proven.
    PublicationRoute,
    /// The published surface of the target is not read.
    PublicationSurface,
    /// The type that the interface publishes is not proven.
    TypePublication,
}

impl InterfaceGap {
    /// The short form of the gap, as one import reads it.
    pub fn form(&self) -> &'static str {
        match self {
            Self::UnreadBinding => "unread import binding",
            Self::PublicationRoute => "unproven publication route",
            Self::PublicationSurface => "incomplete publication surface",
            Self::TypePublication => "unproven named type publication",
        }
    }
}

impl fmt::Display for InterfaceGap {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "interface_boundary: {}", self.form())
    }
}

/// How a held import is classed in the frame: the cause that the collector states, or that it
/// states none (#2086).
#[derive(
    Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, serde::Serialize, schemars::JsonSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum HoldClass {
    /// The collector states no cause for the gap.
    NotStated,
    /// An ambiguous re-export.
    AmbiguousReexport,
    /// A hop that is not proven.
    UncertainHop,
    /// A module whose `__all__` is not one literal list.
    UnreadAll,
    /// A module that code outside the scan roots can write to.
    OutsideWrite,
    /// A module whose object a use inside the scan hands on.
    Escaped,
    /// A re-export under `TYPE_CHECKING`.
    TypeCheckingReexport,
}

impl HoldClass {
    /// The class of the cause that the collector states.
    pub fn of(cause: Option<&RouteWithheld>) -> HoldClass {
        match cause {
            None => HoldClass::NotStated,
            Some(RouteWithheld::AmbiguousReexport) => HoldClass::AmbiguousReexport,
            Some(RouteWithheld::UncertainHop { .. }) => HoldClass::UncertainHop,
            Some(RouteWithheld::OpaqueSurface { form, .. }) => match form {
                SurfaceForm::UnreadAll => HoldClass::UnreadAll,
                SurfaceForm::OutsideWrite => HoldClass::OutsideWrite,
                SurfaceForm::Escaped => HoldClass::Escaped,
            },
            Some(RouteWithheld::TypeCheckingReexport) => HoldClass::TypeCheckingReexport,
        }
    }
}

/// One import that an `interface_boundary` rule could not decide, with the gap and the cause.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HeldImport {
    /// The missing fact of the verdict.
    pub gap: InterfaceGap,
    /// The importing module.
    pub source: String,
    /// The module that the import names.
    pub target: String,
    /// The imported name.
    pub name: Option<String>,
    /// The cause that the collector states for the withheld route.
    pub cause: Option<RouteWithheld>,
    /// The evidence ids of the import.
    pub evidence: Vec<String>,
}

impl HeldImport {
    /// The text of the import as one line of the hold.
    fn line(&self) -> String {
        let name = self
            .name
            .as_deref()
            .map_or_else(String::new, |n| format!(":{n}"));
        let cause = match &self.cause {
            None => String::new(),
            Some(RouteWithheld::AmbiguousReexport) => ", ambiguous re-export".to_owned(),
            Some(RouteWithheld::UncertainHop { hop }) => format!(", unproven hop {hop}"),
            Some(RouteWithheld::OpaqueSurface { module, form }) => match form {
                SurfaceForm::UnreadAll => format!(", unread __all__ of {module}"),
                SurfaceForm::OutsideWrite => format!(", code outside the scan can write {module}"),
                SurfaceForm::Escaped => format!(", the object of {module} escapes"),
            },
            Some(RouteWithheld::TypeCheckingReexport) => {
                ", re-export under TYPE_CHECKING".to_owned()
            }
        };
        format!(
            "{} -> {}{name} ({}{cause})",
            self.source,
            self.target,
            self.gap.form()
        )
    }
}

/// The imports that an `interface_boundary` rule could not decide. The gap of the first one is the
/// stable key of the reason; the display lists the imports (#1963).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InterfaceHold {
    gap: InterfaceGap,
    shown: Vec<HeldImport>,
    total: usize,
    classes: BTreeMap<(InterfaceGap, HoldClass), usize>,
}

impl InterfaceHold {
    /// A hold with no import: the gap holds the rule before any import is read.
    pub fn bare(gap: InterfaceGap) -> InterfaceHold {
        InterfaceHold {
            gap,
            shown: Vec::new(),
            total: 0,
            classes: BTreeMap::new(),
        }
    }

    /// The hold of the undecided imports, or `None` for no import.
    pub fn of(undecided: impl Iterator<Item = HeldImport>) -> Option<InterfaceHold> {
        let mut found: Option<InterfaceHold> = None;
        for held in undecided {
            let hold: &mut InterfaceHold =
                found.get_or_insert_with(|| InterfaceHold::bare(held.gap));
            hold.total += 1;
            let class = HoldClass::of(held.cause.as_ref());
            *hold.classes.entry((held.gap, class)).or_default() += 1;
            if Vec::len(&hold.shown) < HELD_KEPT {
                hold.shown.push(held);
            }
        }
        found
    }

    /// The gap of the first undecided import.
    pub fn gap(&self) -> InterfaceGap {
        self.gap
    }

    /// The number of undecided imports.
    pub fn total(&self) -> usize {
        self.total
    }

    /// The first undecided imports.
    pub fn imports(&self) -> &[HeldImport] {
        &self.shown
    }

    /// The count of undecided imports for each gap and class.
    pub fn classes(&self) -> impl Iterator<Item = (InterfaceGap, HoldClass, usize)> + '_ {
        self.classes
            .iter()
            .map(|((gap, class), count)| (*gap, *class, *count))
    }
}

impl fmt::Display for InterfaceHold {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.gap)?;
        if self.total == 0 {
            return Ok(());
        }
        let unit = if self.total == 1 { "import" } else { "imports" };
        write!(f, ": {} {unit}", self.total)?;
        let shown = Vec::len(&self.shown).min(HELD_SHOWN);
        if self.total > shown {
            write!(f, " (showing {shown})")?;
        }
        let lines: Vec<String> = self
            .shown
            .iter()
            .take(shown)
            .map(HeldImport::line)
            .collect();
        write!(f, ": {}", lines.join(", "))?;
        match self.total - shown {
            0 => Ok(()),
            more => write!(f, " and {more} more"),
        }
    }
}

/// Why a module pair holds an `interface_boundary` rule (#2086): the form of the gap or site.
#[derive(
    Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, serde::Serialize, schemars::JsonSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum PairOrigin {
    /// A module of the pair is not a module of the reply.
    UnobservedModule,
    /// An unresolved internal dispatch: a method call whose callee the collector does not name.
    Dispatch,
    /// A gap that is no internal dispatch and not only about executing an impl.
    NotExecutionOnly,
    /// The gap is only about executing an impl, but a module of the pair has no single owner.
    UnownedEnd,
    /// A named import across components whose publication is not proven.
    NamedSite,
}
