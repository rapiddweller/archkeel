// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import records and their targets (AD-454, rule 4). Each import and export of a library
//! or of an owned part gives one record for each URI: the default URI and each conditional
//! alternative. A URI that gives no proven target gives a named gap and no record.

use archkeel_facts::identity::{package_of, stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{data::ImportData, envelope::Target, ImportFact, Record};
use archkeel_snapshot::Snapshot;

use super::index::{Index, Kind, Located, Owners};
use super::names::{GapName, Gaps, Place};
use super::parts::{directives, missing};
use super::uri::{classify, Uri};
use crate::discover::Source;
use crate::records::cite;
use crate::syntax::{Directive, DirectiveKind};

/// The records sorted by id, and the target of each record in the same order.
#[derive(Default)]
pub(crate) struct Edges {
    pub(crate) imports: Vec<Record<ImportFact>>,
    pub(crate) targets: Vec<Target>,
}

/// The resolved target of one URI, before it has a record id.
enum Resolved {
    Local { module: String, rel: String },
    External { package: String, module: String },
    Builtin(String),
}

/// The edges of each library and each owned part.
pub(crate) fn edges(
    snapshot: &mut Snapshot,
    index: &Index<'_>,
    owners: &Owners,
    gaps: &mut Gaps,
) -> Edges {
    let mut found: Vec<(Record<ImportFact>, Target)> = Vec::new();
    for (at, kind) in index.kinds.iter().enumerate() {
        let module = match kind {
            Kind::Library => &index.sources[at].module,
            Kind::Part => match owners.get(&at) {
                Some(library) => &index.sources[*library].module,
                // An unowned part already has its gap.
                None => continue,
            },
            Kind::Unknown => continue,
        };
        let source = &index.sources[at];
        for kind in [DirectiveKind::Import, DirectiveKind::Export] {
            for directive in directives(index, at, kind) {
                let edges = directive_edges(snapshot, index, (source, module), directive, gaps);
                found.extend(edges);
            }
        }
    }
    found.sort_by(|a, b| a.0.id.cmp(&b.0.id));
    found.dedup_by(|a, b| a.0.id == b.0.id);
    let (imports, targets) = found.into_iter().unzip();
    Edges { imports, targets }
}

/// The records of each URI of one directive of `source`, whose edges are edges of `module`.
fn directive_edges(
    snapshot: &mut Snapshot,
    index: &Index<'_>,
    (source, module): (&Source, &str),
    directive: &Directive,
    gaps: &mut Gaps,
) -> Vec<(Record<ImportFact>, Target)> {
    let mut found = Vec::new();
    for uri in uris(directive) {
        if let Some(target) = resolve(snapshot, index, (source, directive), uri, gaps) {
            found.push(record((source, module), directive, uri, target, gaps));
        }
    }
    found
}

/// The default URI and each alternative of `directive`, without a repeat, in their order.
/// A URI that is not a plain string has no text here: the parse already gave it the gap
/// `DartUriNotLiteral` (`directives.rs`).
fn uris(directive: &Directive) -> Vec<&str> {
    let mut uris: Vec<&str> = directive.target.as_deref().into_iter().collect();
    for (_, alternative) in &directive.alternatives {
        if !uris.contains(&alternative.as_str()) {
            uris.push(alternative);
        }
    }
    uris
}

/// The target of `uri`, or a named gap.
fn resolve(
    snapshot: &mut Snapshot,
    index: &Index<'_>,
    (source, directive): (&Source, &Directive),
    uri: &str,
    gaps: &mut Gaps,
) -> Option<Resolved> {
    let at = Place::Span(source, &directive.span);
    let (name, message) = match classify(&source.rel_path, uri, index.package) {
        Uri::Builtin(module) => {
            if module == "dart.mirrors" {
                let message = "dart:mirrors can reach code without an import; the edge stays";
                gaps.named(GapName::DartMirrors, at, message);
            }
            return Some(Resolved::Builtin(module));
        }
        Uri::External { package, module } => return Some(Resolved::External { package, module }),
        Uri::Local(rel) => match index.locate(snapshot, &rel) {
            Located::Source(target) => match index.kinds[target] {
                Kind::Library => {
                    let module = index.sources[target].module.clone();
                    return Some(Resolved::Local { module, rel });
                }
                Kind::Part => (
                    GapName::DartTargetIsPart,
                    format!("{uri} gives the part file {rel}"),
                ),
                Kind::Unknown => (
                    GapName::DartTargetUnparsed,
                    format!("{uri} gives {rel}, which has no proven module"),
                ),
            },
            Located::NotSelected => (
                GapName::DartTargetNotSelected,
                format!("{uri} gives {rel}, which is not a selected source"),
            ),
            Located::Missing => (GapName::DartTargetMissing, missing(&rel)),
        },
        Uri::Outside => (
            GapName::DartTargetOutside,
            format!("{uri} leaves the package"),
        ),
        Uri::Unsupported(reason) => (GapName::DartUnsupportedUri, format!("{uri}: {reason}")),
    };
    gaps.named(name, at, &message);
    None
}

/// The record and the target of one resolved URI of `directive` in `source`, whose edges are
/// edges of `module`.
fn record(
    (source, module): (&Source, &str),
    directive: &Directive,
    uri: &str,
    target: Resolved,
    gaps: &mut Gaps,
) -> (Record<ImportFact>, Target) {
    let start = i64::try_from(directive.span.start_byte).unwrap_or(i64::MAX);
    let identity = stable_id(
        "DARTIMP",
        &[
            Part::Text(&source.rel_path),
            Part::Number(start),
            Part::Text(uri),
        ],
    );
    let import_id = FactId::new(identity.clone());
    let (target_module, target_package, resolved) = match target {
        Resolved::Local {
            module: target,
            rel,
        } => (
            target.clone(),
            package_of(&target).to_owned(),
            Target::Local {
                import_id,
                module: ModuleName::new(target),
                file: rel,
                runtime_file: None,
                declaration_file: None,
            },
        ),
        Resolved::External { package, module } => (
            module,
            package.clone(),
            Target::External {
                import_id,
                package: PackageName::new(package),
            },
        ),
        Resolved::Builtin(module) => (
            module.clone(),
            "dart".to_owned(),
            Target::Builtin {
                import_id,
                name: module,
            },
        ),
    };
    let export = directive.kind == DirectiveKind::Export;
    let mut data = ImportData::statement();
    data.specifier = None;
    data.type_only = None;
    data.source_module = ModuleName::new(module);
    data.source_package = PackageName::new(package_of(module));
    data.target_module = ModuleName::new(&target_module);
    data.target_package = PackageName::new(target_package);
    data.binding = if export {
        None
    } else {
        directive.prefix.clone()
    };
    data.reexport = export;
    data.module_level_import = true;
    let mut subjects = vec![module.to_owned(), target_module];
    subjects.sort();
    subjects.dedup();
    let evidence = cite(&mut gaps.evidence, source, &directive.span);
    let record = Record {
        id: FactId::new(identity),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: format!("{module} imports {uri}"),
        subjects,
        evidence_ids: vec![EvidenceId::new(evidence)],
        fact_ids: Vec::new(),
        data: if export {
            ImportFact::Reexport(data)
        } else {
            ImportFact::Import(data)
        },
    };
    (record, resolved)
}
