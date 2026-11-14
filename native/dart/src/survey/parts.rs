// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The owner of each part file (AD-450, rule 3). A part has an owner only when exactly one
//! library claims it with `part` and its one `part of` names that library, by URI or by the
//! name of the `library` directive. Each other case is a named gap.

use std::collections::BTreeMap;

use archkeel_snapshot::Snapshot;

use super::names::{GapName, Gaps, Place};
use super::uri::{classify, generated, Uri};
use super::{Index, Kind, Located, Owners};
use crate::syntax::{Directive, DirectiveKind};

/// The owner of each part that has one. The claims of the libraries are read first.
pub(crate) fn owners(snapshot: &mut Snapshot, index: &Index<'_>, gaps: &mut Gaps) -> Owners {
    let mut claims: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
    for library in libraries(index) {
        for directive in directives(index, library, DirectiveKind::Part) {
            if let Some(part) = claimed(snapshot, index, library, directive, gaps) {
                claims.entry(part).or_default().push(library);
            }
        }
    }
    let mut owners = Owners::new();
    for (part, kind) in index.kinds.iter().enumerate() {
        if *kind != Kind::Part {
            continue;
        }
        let rel = &index.sources[part].rel_path;
        match claims.get(&part).map(Vec::as_slice) {
            Some([library]) if names(snapshot, index, part, *library) => {
                owners.insert(part, *library);
            }
            Some([library]) => {
                let message = format!(
                    "the part of directive does not name the library {} that claims it",
                    index.sources[*library].rel_path
                );
                gaps.named(GapName::DartPartUnowned, Place::File(rel), &message);
            }
            Some(libraries) if libraries.len() > 1 => {
                let paths: Vec<&str> = libraries
                    .iter()
                    .map(|at| index.sources[*at].rel_path.as_str())
                    .collect();
                let message = format!(
                    "more than one library claims the part: {}",
                    paths.join(", ")
                );
                gaps.named(GapName::DartPartConflict, Place::File(rel), &message);
            }
            _ => {
                let message = "no selected library claims the part with a part directive";
                gaps.named(GapName::DartPartUnowned, Place::File(rel), message);
            }
        }
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
    let rel = match classify(&source.rel_path, uri, index.package) {
        Uri::Local(rel) => rel,
        Uri::Outside => {
            gaps.named(
                GapName::DartTargetOutside,
                at,
                "the part URI leaves the package",
            );
            return None;
        }
        _ => {
            let message = "the part URI is not a path of this package";
            gaps.named(GapName::DartUnsupportedUri, at, message);
            return None;
        }
    };
    match index.locate(snapshot, &rel) {
        Located::Source(part) if index.kinds[part] == Kind::Part => Some(part),
        // The source without a proven kind already has its gap.
        Located::Source(part) if index.kinds[part] == Kind::Unknown => None,
        Located::Source(_) => {
            let message = format!("the part URI gives {rel}, which has no part of directive");
            gaps.named(GapName::DartPartNotPart, at, &message);
            None
        }
        Located::NotSelected => {
            let message = format!("the part {rel} is not a selected source");
            gaps.named(GapName::DartTargetNotSelected, at, &message);
            None
        }
        Located::Missing => {
            gaps.named(GapName::DartTargetMissing, at, &missing(&rel));
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

/// The one `part of` of `part` names `library`: its URI gives the library, or its text equals
/// the name of the one `library` directive of the library.
fn names(snapshot: &mut Snapshot, index: &Index<'_>, part: usize, library: usize) -> bool {
    let owners: Vec<&Directive> = directives(index, part, DirectiveKind::PartOf).collect();
    let [owner] = owners.as_slice() else {
        return false;
    };
    let Some(text) = owner.target.as_deref() else {
        return false;
    };
    let source = &index.sources[part];
    if let Uri::Local(rel) = classify(&source.rel_path, text, index.package) {
        if matches!(index.locate(snapshot, &rel), Located::Source(at) if at == library) {
            return true;
        }
    }
    let declared: Vec<&str> = directives(index, library, DirectiveKind::Library)
        .filter_map(|directive| directive.target.as_deref())
        .collect();
    matches!(declared.as_slice(), [name] if library_name(name) == library_name(text))
}

/// The dotted name of a `library` or `part of` directive without white space.
fn library_name(text: &str) -> String {
    text.chars().filter(|c| !c.is_whitespace()).collect()
}
