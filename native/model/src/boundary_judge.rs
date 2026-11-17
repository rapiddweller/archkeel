// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The verdict of one written type for `boundary_types` (AD-550).
//!
//! The judge reads a shape and nothing else of the source. A leaf is allowed, a violation or a
//! named gap. It is allowed only when the binding that the collector proved reaches a record that
//! the rule accepts: a scalar, an enum, a plain literal, or `None`. A leaf that reaches a class of
//! the repository outside every `public` list is a violation. Anything else is a gap with a
//! cause, never an accepted type: an alias, a user generic, a type outside the scan, a class whose
//! fields the rule would walk, a name with no record, a missing annotation.

use std::collections::HashSet;

use archkeel_facts::standard::Wrapped;
use archkeel_facts::type_shape::{Binding, Family, TypeShape, Unproven};
use archkeel_facts::vocab::ClassKind;

use crate::boundary_facts::{standard_of, wrapped_of, BoundaryFacts, Entry, Origin, Standard};

/// Why a position or an entry of a facade is not decided by syntax. The causes are closed.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum GapCause {
    /// A position with no annotation.
    MissingAnnotation,
    /// An annotation that is a string naming a type that the syntax does not resolve.
    ForwardReference,
    /// A user generic: its arguments are not decided by syntax.
    Generic,
    /// A type alias: its target is not read.
    Alias,
    /// A dotted name that no import binding resolves.
    DottedName,
    /// A type outside the scan.
    ExternalType,
    /// A name that no binding of the module resolves.
    UnresolvedName,
    /// A method annotation that is evaluated late, in a class namespace that can hold the name
    /// (#1523).
    LazyClassNamespace,
    /// An `Any` type, which proves nothing about its content.
    AnyType,
    /// A class whose fields the rule would walk.
    FieldWalk,
    /// An allowance that the rule does not read.
    AllowanceNotRead,
    /// A surface that a class inherits from a base that the scan does not read.
    InheritedSurface,
    /// A member of the surface that has no record.
    MemberNoRecord,
    /// A name with no record in the scan.
    NoRecord,
    /// An entry of a facade that does not resolve.
    UnresolvedFacadeEntry,
    /// A facade whose exports are computed at run time.
    DynamicExports,
    /// A collector that does not write the shapes of types.
    ShapesNotWritten,
    /// Any other reason that syntax does not decide.
    Other,
}

impl GapCause {
    /// The word of the cause in a row of the report.
    pub fn as_str(self) -> &'static str {
        match self {
            GapCause::MissingAnnotation => "missing_annotation",
            GapCause::ForwardReference => "forward_reference",
            GapCause::Generic => "generic",
            GapCause::Alias => "alias",
            GapCause::DottedName => "dotted_name",
            GapCause::ExternalType => "external_type",
            GapCause::UnresolvedName => "unresolved_name",
            GapCause::LazyClassNamespace => "lazy_class_namespace",
            GapCause::AnyType => "any_type",
            GapCause::FieldWalk => "field_walk",
            GapCause::AllowanceNotRead => "allowance_not_read",
            GapCause::InheritedSurface => "inherited_surface",
            GapCause::MemberNoRecord => "member_no_record",
            GapCause::NoRecord => "no_record",
            GapCause::UnresolvedFacadeEntry => "unresolved_facade_entry",
            GapCause::DynamicExports => "dynamic_exports",
            GapCause::ShapesNotWritten => "shapes_not_written",
            GapCause::Other => "other",
        }
    }
}

/// What the user can do about a late class annotation (#1523). The shell says it in the words of
/// the language of the scan.
const LATE_REMEDY: &str = "the class namespace can hold the name when the annotation is \
    evaluated: narrow the version range of the project, make the annotations strings, or remove \
    the namespace write";

/// One named gap: a position or an entry that syntax does not decide.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GapRow {
    /// The facade position or entry that the gap is about.
    pub subject: String,
    /// The closed cause of the gap.
    pub cause: GapCause,
    /// The written detail of the gap.
    pub text: String,
}

impl GapRow {
    /// The reason of the row: the cause and the written text.
    pub fn reason(&self) -> String {
        let reason = format!("{}: {}", self.cause.as_str(), self.text);
        match self.cause {
            GapCause::LazyClassNamespace => format!("{reason} ({LATE_REMEDY})"),
            _ => reason,
        }
    }
}

/// One leaf that breaks the rule.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Leaf {
    /// The text of the leaf as written.
    pub text: String,
    /// Why the leaf breaks the rule.
    pub why: String,
    /// How many collections hold the leaf: 0 for the position itself.
    pub depth: u32,
    /// A broad type (a mapping, `object`): the only kind that an exact exception can allow.
    pub broad: bool,
}

/// What the judge finds in one shape.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct Judged {
    pub(crate) leaves: Vec<Leaf>,
    pub(crate) gaps: Vec<(GapCause, String)>,
    /// True when a leaf is allowed only under the premise `standard_library_unchanged` (AD-782).
    pub(crate) assumed: bool,
}

impl Judged {
    fn merge(&mut self, other: Judged) {
        self.leaves.extend(other.leaves);
        self.gaps.extend(other.gaps);
        self.assumed |= other.assumed;
    }

    fn gap(cause: GapCause, text: &str) -> Judged {
        Judged {
            leaves: Vec::new(),
            gaps: vec![(cause, text.to_owned())],
            assumed: false,
        }
    }
}

/// The words of a gap that the premise `standard_library_unchanged` would close (AD-782).
pub(crate) const NEEDS_PREMISE: &str =
    "it counts only under the contract premise standard_library_unchanged";

/// What a name can reach: the records, the names that a `public` list declares and the modules of
/// the scan.
pub(crate) struct Surface<'a> {
    pub(crate) facts: &'a BoundaryFacts,
    /// The qualified names of the definitions that some component declares.
    pub(crate) declared: &'a HashSet<String>,
    pub(crate) scanned: &'a HashSet<&'a str>,
    /// True when the contract declares the premise `standard_library_unchanged` (AD-782).
    pub(crate) premise: bool,
}

/// The judge of one shape; `depth` counts the collections around it.
pub(crate) fn judge(shape: &TypeShape, surface: &Surface<'_>, depth: u32) -> Judged {
    match shape {
        TypeShape::Unannotated {} => Judged::gap(GapCause::MissingAnnotation, ""),
        TypeShape::Nothing {} | TypeShape::Primitive { .. } => Judged::default(),
        TypeShape::Dynamic { text, name } if name == "Any" => Judged::gap(GapCause::AnyType, text),
        TypeShape::Dynamic { text, .. } => broad(text, "a type that holds anything", depth),
        TypeShape::Collection {
            text, family, args, ..
        } => {
            let mut found = Judged::default();
            if *family == Family::Mapping {
                found.merge(broad(text, "a mapping is an open record", depth));
            } else if args.is_empty() {
                found.merge(Judged::gap(GapCause::Generic, text));
            }
            for arg in args {
                found.merge(judge(arg, surface, depth + 1));
            }
            found
        }
        TypeShape::Union { arms, .. } => {
            let mut found = Judged::default();
            for arm in arms {
                found.merge(judge(arm, surface, depth));
            }
            found
        }
        TypeShape::Literal { text, plain } => {
            if *plain {
                Judged::default()
            } else {
                Judged::gap(GapCause::Other, text)
            }
        }
        TypeShape::Annotated { inner, .. } => judge(inner, surface, depth),
        TypeShape::Named { text, binding } => named(text, binding, surface),
        // The head is a type that this reading does not model (`Callable`, a user generic): what
        // it holds is not read, so no leaf of it is a violation either.
        TypeShape::Applied { text, .. } => Judged::gap(GapCause::Generic, text),
        TypeShape::Forward { text } => Judged::gap(GapCause::ForwardReference, text),
        TypeShape::Unreadable { text, .. } => Judged::gap(GapCause::Other, text),
    }
}

fn broad(text: &str, why: &str, depth: u32) -> Judged {
    Judged {
        leaves: vec![Leaf {
            text: text.to_owned(),
            why: why.to_owned(),
            depth,
            broad: true,
        }],
        gaps: Vec::new(),
        assumed: false,
    }
}

fn named(text: &str, binding: &Binding, surface: &Surface<'_>) -> Judged {
    match binding {
        Binding::Unproven { cause } => Judged::gap(
            match cause {
                Unproven::Dotted => GapCause::DottedName,
                Unproven::StarImport
                | Unproven::Hidden
                | Unproven::NotSole
                | Unproven::UnreadImport
                | Unproven::Unbound => GapCause::UnresolvedName,
                Unproven::LazyClassNamespace => GapCause::LazyClassNamespace,
            },
            text,
        ),
        Binding::Builtin { .. } => Judged::gap(GapCause::Other, text),
        Binding::Defined { target } | Binding::Imported { target } => {
            reached(text, target, surface)
        }
    }
}

/// The verdict of a name that one plain binder gives to the qualified name `target`.
fn reached(text: &str, target: &str, surface: &Surface<'_>) -> Judged {
    match surface.facts.origin_of(target) {
        Origin::Defined(name, Entry::Class(class)) => {
            if class.kind == Some(ClassKind::Enum) {
                Judged::default()
            } else if surface.declared.contains(name) {
                // The rule walks the fields of a declared class; syntax does not.
                Judged::gap(GapCause::FieldWalk, text)
            } else {
                Judged {
                    leaves: vec![Leaf {
                        text: text.to_owned(),
                        why: "a class that no component declares".to_owned(),
                        depth: 0,
                        broad: false,
                    }],
                    gaps: Vec::new(),
                    assumed: false,
                }
            }
        }
        Origin::Defined(_, Entry::Value) => Judged::gap(GapCause::Alias, text),
        Origin::Defined(_, Entry::Callable(_)) | Origin::Module => {
            Judged::gap(GapCause::Other, text)
        }
        Origin::Missing { module, qualified } => {
            if !surface.scanned.contains(module.as_str()) {
                return standard(text, &qualified, surface);
            }
            // A class whose standard decorator keeps it a class (AD-782).
            let class = matches!(
                wrapped_of(surface.facts, &qualified),
                Some(Wrapped::Class { .. })
            );
            match (
                class && surface.premise,
                surface.declared.contains(&qualified),
            ) {
                (true, true) => Judged {
                    assumed: true,
                    ..Judged::gap(GapCause::FieldWalk, text)
                },
                (true, false) => Judged {
                    leaves: vec![Leaf {
                        text: text.to_owned(),
                        why: "a class that no component declares".to_owned(),
                        depth: 0,
                        broad: false,
                    }],
                    gaps: Vec::new(),
                    assumed: true,
                },
                (false, _) => Judged::gap(GapCause::UnresolvedName, text),
            }
        }
    }
}

/// A name outside the scan: a type of the standard library that the collector names counts under
/// the premise `standard_library_unchanged` (AD-782); every other name is a type outside the scan.
pub(crate) fn standard(text: &str, qualified: &str, surface: &Surface<'_>) -> Judged {
    match standard_of(surface.facts, qualified) {
        None => Judged::gap(GapCause::ExternalType, text),
        Some(Standard::Changed(reason)) => Judged::gap(
            GapCause::ExternalType,
            &format!("{text}: the repository may change the standard library name {qualified} ({reason})"),
        ),
        Some(Standard::Type) if surface.premise => Judged {
            assumed: true,
            ..Judged::default()
        },
        Some(Standard::Type) => Judged::gap(
            GapCause::ExternalType,
            &format!("{text}: a type of the standard library; {NEEDS_PREMISE}"),
        ),
    }
}

#[cfg(test)]
#[path = "boundary_judge_tests.rs"]
mod tests;
