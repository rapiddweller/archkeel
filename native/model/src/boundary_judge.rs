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

use crate::boundary_facts::{
    positions_of, standard_of, wrapped_of, BoundaryFacts, Entry, Origin, Standard,
};

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

/// The judge of the shape of one position, keyed `<qualified name>:<position>`. A collection or a
/// special form that the shape reads by its qualified name (`typing.List`, `typing.Optional`)
/// counts only under the premise `standard_library_unchanged` and while the repository leaves the
/// name unchanged (#1718); otherwise the position is a gap that names why.
pub(crate) fn judge_position(shape: &TypeShape, surface: &Surface<'_>, key: &str) -> Judged {
    judge_position_seen(shape, surface, key, &mut HashSet::new())
}

/// Judge a position while preserving the dataclass path for recursive field types.
fn judge_position_seen(
    shape: &TypeShape,
    surface: &Surface<'_>,
    key: &str,
    seen: &mut HashSet<String>,
) -> Judged {
    let mut assumed = false;
    for name in positions_of(surface.facts, key).into_iter().flatten() {
        let gate = standard(name, name, surface);
        if !Vec::is_empty(&gate.gaps) {
            return gate;
        }
        assumed |= gate.assumed;
    }
    let mut found = judge_seen(shape, surface, 0, seen);
    found.assumed |= assumed;
    found
}

/// Judge a shape while keeping the dataclass types on the current field path.
fn judge_seen(
    shape: &TypeShape,
    surface: &Surface<'_>,
    depth: u32,
    seen: &mut HashSet<String>,
) -> Judged {
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
                found.merge(judge_seen(arg, surface, depth + 1, seen));
            }
            found
        }
        TypeShape::Union { arms, .. } => {
            let mut found = Judged::default();
            for arm in arms {
                found.merge(judge_seen(arm, surface, depth, seen));
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
        TypeShape::Annotated { inner, .. } => judge_seen(inner, surface, depth, seen),
        TypeShape::Named { text, binding } => named(text, binding, surface, seen),
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

fn named(
    text: &str,
    binding: &Binding,
    surface: &Surface<'_>,
    seen: &mut HashSet<String>,
) -> Judged {
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
            reached(text, target, surface, seen)
        }
    }
}

/// The verdict of a name that one plain binder gives to the qualified name `target`.
fn reached(text: &str, target: &str, surface: &Surface<'_>, seen: &mut HashSet<String>) -> Judged {
    match surface.facts.origin_of(target) {
        Origin::Defined(name, Entry::Class(class)) => {
            if class.kind == Some(ClassKind::Enum) {
                Judged::default()
            } else if surface.declared.contains(name) {
                dataclass_fields(text, name, surface, seen)
                    .unwrap_or_else(|| Judged::gap(GapCause::FieldWalk, text))
            } else {
                undeclared_class(text, false)
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
            match wrapped_of(surface.facts, &qualified) {
                Some(Wrapped::Unread(reason)) => {
                    return Judged::gap(GapCause::UnresolvedName, &format!("{text}: {reason}"));
                }
                Some(Wrapped::Class { .. }) if surface.premise => {
                    if surface.declared.contains(&qualified) {
                        dataclass_fields(text, &qualified, surface, seen)
                            .unwrap_or_else(|| Judged::gap(GapCause::FieldWalk, text))
                    } else {
                        undeclared_class(text, true)
                    }
                }
                Some(Wrapped::Class { .. }) => Judged::gap(
                    GapCause::FieldWalk,
                    &format!("{text}: the standard dataclass field model requires {NEEDS_PREMISE}"),
                ),
                _ => Judged::gap(GapCause::UnresolvedName, text),
            }
        }
    }
}

/// A repository class that no component declares is a violation, also under the premise.
fn undeclared_class(text: &str, assumed: bool) -> Judged {
    Judged {
        leaves: vec![Leaf {
            text: text.to_owned(),
            why: "a class that no component declares".to_owned(),
            depth: 0,
            broad: false,
        }],
        gaps: Vec::new(),
        assumed,
    }
}

/// Walk only a complete field inventory from the collector's guarded dataclass model.
fn dataclass_fields(
    text: &str,
    target: &str,
    surface: &Surface<'_>,
    seen: &mut HashSet<String>,
) -> Option<Judged> {
    if !surface.premise {
        return None;
    }
    let Some(Wrapped::Class {
        init: Some(fields),
        attributes,
        ..
    }) = wrapped_of(surface.facts, target)
    else {
        return None;
    };
    // The current fact carries types only for generated __init__ parameters. If any class
    // attribute is absent from that inventory, do not assume it is not an instance field.
    let names: HashSet<&str> = fields.iter().map(|field| field.name.as_str()).collect();
    if attributes
        .iter()
        .any(|attribute| !names.contains(attribute.as_str()))
    {
        return None;
    }
    if !seen.insert(target.to_owned()) {
        return Some(Judged::gap(
            GapCause::FieldWalk,
            &format!("{text}: recursive dataclass field walk"),
        ));
    }
    let mut found = Judged {
        assumed: true,
        ..Judged::default()
    };
    for field in fields {
        let field_text = format!("{target}.{}", field.name);
        let judged = if let Some(shape) = &field.shape {
            let key = format!("{target}.__init__:{}", field.name);
            let mut judged = judge_position_seen(shape, surface, &key, seen);
            for leaf in &mut judged.leaves {
                leaf.text = format!("{field_text}: {}", leaf.text);
            }
            for (_, detail) in &mut judged.gaps {
                *detail = format!("{field_text}: {detail}");
            }
            judged
        } else {
            Judged::gap(GapCause::MissingAnnotation, &field_text)
        };
        found.merge(judged);
    }
    seen.remove(target);
    Some(found)
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
