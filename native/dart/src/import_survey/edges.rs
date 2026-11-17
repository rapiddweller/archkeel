// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import records and their targets (AD-454, rule 4). Each import and export of a library
//! or of an owned part gives one record for each URI: the default URI and each conditional
//! alternative. A URI that gives no proven target gives a named gap and no record.
//!
//! AD-749: the records state the publication surface. A `show` list gives one record for each
//! name that the combinators keep, with the first hop of its route; a directive without `show`
//! binds the whole namespace of its target. An `export` of a library outside `lib/src/` names
//! what it publishes outside the package (`binding.rs`).

use archkeel_facts::identity::{package_of, stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{data::ImportData, envelope::Target, ImportFact, Record};
use archkeel_snapshot::Snapshot;

use super::binding::{published, Binding, Surface};
use super::index::{Index, Kind, Located, Owners};
use super::names::{GapName, Gaps, Place};
use super::package_map::PackageMap;
use super::parts::{directives, missing};
use super::uri::Uri;
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
#[derive(Clone)]
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
    let surface = Surface::of(index, owners);
    for (at, kind) in index.kinds.iter().enumerate() {
        let library = match kind {
            Kind::Library => at,
            Kind::Part => match owners.get(&at) {
                Some(library) => *library,
                // An unowned part already has its gap.
                None => continue,
            },
            Kind::Unknown => continue,
        };
        let module = &index.sources[library].module;
        let publishes = published(&index.sources[library].rel_path);
        let source = &index.sources[at];
        for kind in [DirectiveKind::Import, DirectiveKind::Export] {
            for directive in directives(index, at, kind) {
                let from = From {
                    source,
                    module,
                    publishes,
                };
                let edges = directive_edges(snapshot, (index, &surface), &from, directive, gaps);
                found.extend(edges);
            }
        }
    }
    found.sort_by(|a, b| a.0.id.cmp(&b.0.id));
    found.dedup_by(|a, b| a.0.id == b.0.id);
    let (imports, targets) = found.into_iter().unzip();
    Edges { imports, targets }
}

/// Where a directive sits: its file, the module whose edges it gives, and whether that library
/// publishes outside the package (AD-749).
struct From<'a> {
    source: &'a Source,
    module: &'a str,
    publishes: bool,
}

/// The records of each URI of one directive: one for each name that it binds (AD-749).
fn directive_edges(
    snapshot: &mut Snapshot,
    (index, surface): (&Index<'_>, &Surface),
    from: &From<'_>,
    directive: &Directive,
    gaps: &mut Gaps,
) -> Vec<(Record<ImportFact>, Target)> {
    let binding = Binding::of(directive);
    let mut found = Vec::new();
    for uri in uris(directive) {
        let Some(target) = resolve(snapshot, index, (from.source, directive), uri, gaps) else {
            continue;
        };
        // A route ends at its first hop only in a local library that re-exports nothing.
        let complete = match &target {
            Resolved::Local { rel, .. } => surface.declares(index, rel),
            Resolved::External { .. } | Resolved::Builtin(_) => false,
        };
        for name in binding.names() {
            let named = Named {
                binding: &binding,
                name,
                complete,
            };
            found.push(record(from, directive, uri, target.clone(), &named, gaps));
        }
    }
    found
}

/// One record of a binding: the name that it binds, if any, and whether its route is complete.
struct Named<'a> {
    binding: &'a Binding,
    name: Option<&'a str>,
    complete: bool,
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
    // AD-800: an import of a package that the package map does not prove external keeps its
    // record, whose module has the same name in either case, and a gap that holds its library.
    let package = uri
        .strip_prefix("package:")
        .and_then(|rest| rest.split_once('/'))
        .map(|(name, _)| name);
    let unproven = match package {
        Some(name) if name == index.package => PackageMap::own(&index.packages, name).err(),
        Some(name) => PackageMap::external(&index.packages, name).err(),
        None => None,
    };
    if let Some((name, message)) = unproven {
        gaps.named(name, at, &message);
    }
    let (name, message) = match index.classify(&source.rel_path, uri) {
        // #1706: a module name of another package or of the SDK can also be a module of this
        // scan (a namespace equal to the package name of the URI, and no own package). The store
        // cannot take both, so the import is a gap that names its module.
        Uri::Builtin(module) | Uri::External { module, .. } if index.is_module(&module) => (
            GapName::UnsupportedUri,
            format!("{uri} names the module {module}, which is also a module of this scan"),
        ),
        Uri::Builtin(module) => {
            if module == "dart.mirrors" {
                let message = "dart:mirrors can reach code without an import; the edge stays";
                gaps.named(GapName::Mirrors, at, message);
            }
            if module == "dart.isolate" && index.isolate_loader {
                let message =
                    "dart:isolate can run another library with Isolate.spawnUri; the edge stays";
                gaps.named(GapName::Isolate, at, message);
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
                    GapName::TargetIsPart,
                    format!("{uri} gives the part file {rel}"),
                ),
                Kind::Unknown => (
                    GapName::TargetUnparsed,
                    format!("{uri} gives {rel}, which has no proven module"),
                ),
            },
            Located::NotSelected => (
                GapName::TargetNotSelected,
                format!("{uri} gives {rel}, which is not a selected source"),
            ),
            Located::Missing => (GapName::TargetMissing, missing(&rel)),
        },
        Uri::Outside => (GapName::TargetOutside, format!("{uri} leaves the package")),
        Uri::Unsupported(reason) => (GapName::UnsupportedUri, format!("{uri}: {reason}")),
    };
    gaps.named(name, at, &message);
    None
}

/// The record and the target of one resolved URI of `directive` in `source`, whose edges are
/// edges of `module`.
fn record(
    from: &From<'_>,
    directive: &Directive,
    uri: &str,
    target: Resolved,
    named: &Named<'_>,
    gaps: &mut Gaps,
) -> (Record<ImportFact>, Target) {
    let (source, module) = (from.source, from.module);
    let start = i64::try_from(directive.span.start_byte).unwrap_or(i64::MAX);
    let mut parts = vec![
        Part::Text(&source.rel_path),
        Part::Number(start),
        Part::Text(uri),
    ];
    // A record of a whole namespace keeps the id that it had before AD-749.
    if let Some(name) = named.name {
        parts.push(Part::Text(name));
    }
    let identity = stable_id("DARTIMP", &parts);
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
    named
        .binding
        .state(&mut data, named.name, &target_module, named.complete);
    if export && from.publishes {
        data.published_as = Some(named.name.unwrap_or("*").to_owned());
    }
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
