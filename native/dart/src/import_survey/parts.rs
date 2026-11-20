// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The owner of each part file (AD-454, rule 3). A part has an owner only when exactly one
//! library claims it with `part` and its one `part of` names that library, by URI or by the
//! name of the `library` directive. Each other case is a named gap.

use std::collections::BTreeMap;

use archkeel_snapshot::Snapshot;

use super::index::{Index, Kind, Located, Owners};
use super::names::{GapName, Gaps, Place};
use super::uri::{generated, Uri};
use crate::syntax::{Directive, DirectiveKind};

/// The owner of each part that has one. The claims of the libraries are read first.
pub(crate) fn owners(snapshot: &mut Snapshot, index: &Index<'_>, gaps: &mut Gaps) -> Owners {
    let mut claims: BTreeMap<usize, Vec<(usize, &Directive)>> = BTreeMap::new();
    for library in libraries(index) {
        for directive in directives(index, library, DirectiveKind::Part) {
            if let Some(part) = claimed(snapshot, index, library, directive, gaps) {
                claims.entry(part).or_default().push((library, directive));
            }
        }
    }
    let mut owners = Owners::new();
    for (part, kind) in index.kinds.iter().enumerate() {
        if *kind != Kind::Part {
            continue;
        }
        let source = &index.sources[part];
        let declared: Vec<&Directive> = directives(index, part, DirectiveKind::PartOf).collect();
        let claimants: &[(usize, &Directive)] = claims.get(&part).map_or(&[], Vec::as_slice);
        let (name, message) = match claimants {
            [(library, _)] if names(index, part, *library, &declared) => {
                owners.insert(part, *library);
                continue;
            }
            [(library, _)] => (
                GapName::PartUnowned,
                format!(
                    "the part of directive does not name the library {} that claims it",
                    index.sources[*library].rel_path
                ),
            ),
            libraries if libraries.len() > 1 => {
                let paths: Vec<&str> = libraries
                    .iter()
                    .map(|(at, _)| index.sources[*at].rel_path.as_str())
                    .collect();
                (
                    GapName::PartConflict,
                    format!(
                        "more than one directive claims the part: {}",
                        paths.join(", ")
                    ),
                )
            }
            _ => (
                GapName::PartUnowned,
                "no selected library claims the part with a part directive".to_owned(),
            ),
        };
        let site = declared
            .first()
            .map_or(Place::File(&source.rel_path), |owner| {
                Place::Span(source, &owner.span)
            });
        let related = declared
            .iter()
            .skip(1)
            .map(|owner| (source, &owner.span))
            .chain(
                claimants
                    .iter()
                    .map(|(at, directive)| (&index.sources[*at], &directive.span)),
            );
        gaps.named_with_related(name, site, &message, related);
    }
    owners
}

/// The index of each library.
fn libraries<'a>(index: &'a Index<'_>) -> impl Iterator<Item = usize> + 'a {
    (0..index.kinds.len()).filter(|at| index.kinds[*at] == Kind::Library)
}

/// The directives of `kind` of the source at `at`.
pub(crate) fn directives<'a>(
    index: &'a Index<'_>,
    at: usize,
    kind: DirectiveKind,
) -> impl Iterator<Item = &'a Directive> + 'a {
    index.syntax[at]
        .iter()
        .flat_map(|syntax| syntax.directives.iter())
        .filter(move |directive| directive.kind == kind)
}

/// The part that the `part` directive of `library` claims, or a gap when it gives no part.
fn claimed(
    snapshot: &mut Snapshot,
    index: &Index<'_>,
    library: usize,
    directive: &Directive,
    gaps: &mut Gaps,
) -> Option<usize> {
    let source = &index.sources[library];
    let at = Place::Span(source, &directive.span);
    // A URI that is not a plain string already has its gap from the parse.
    let uri = directive.target.as_deref()?;
    let rel = match index.classify(&source.rel_path, uri) {
        Uri::Local(rel) => rel,
        Uri::Outside => {
            gaps.named(
                GapName::TargetOutside,
                at,
                "the part URI leaves the package",
            );
            return None;
        }
        _ => {
            let message = "the part URI is not a path of this package";
            gaps.named(GapName::UnsupportedUri, at, message);
            return None;
        }
    };
    match index.locate(snapshot, &rel) {
        Located::Source(part) if index.kinds[part] == Kind::Part => Some(part),
        // The source without a proven kind already has its gap.
        Located::Source(part) if index.kinds[part] == Kind::Unknown => None,
        Located::Source(_) => {
            let message = format!("the part URI gives {rel}, which has no part of directive");
            gaps.named(GapName::PartNotPart, at, &message);
            None
        }
        Located::NotSelected => {
            let message = format!("the part {rel} is not a selected source");
            gaps.named(GapName::TargetNotSelected, at, &message);
            None
        }
        Located::Missing => {
            gaps.named(GapName::TargetMissing, at, &missing(&rel));
            None
        }
    }
}

/// The message of a URI that gives no file.
pub(crate) fn missing(rel: &str) -> String {
    if generated(rel) {
        format!("the generated file {rel} does not exist; run the build step before the scan")
    } else {
        format!("the file {rel} does not exist")
    }
}

/// The one `part of` of `part` names `library` in the syntax that the directive uses.
fn names(index: &Index<'_>, part: usize, library: usize, owners: &[&Directive]) -> bool {
    let [owner] = owners else {
        return false;
    };
    let Some(text) = owner.target.as_deref() else {
        return false;
    };
    if owner.part_owner_is_uri {
        let source = &index.sources[part];
        let Uri::Local(rel) = index.classify(&source.rel_path, text) else {
            return false;
        };
        return index.by_rel.get(rel.as_str()) == Some(&library);
    }
    let declared: Vec<&str> = directives(index, library, DirectiveKind::Library)
        .filter_map(|directive| directive.target.as_deref())
        .collect();
    matches!(declared.as_slice(), [name] if *name == text)
}
