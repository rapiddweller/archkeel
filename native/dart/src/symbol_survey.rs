// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol facts of one survey (AD-796): the full parse of each library and part that the
//! survey proved, the resolver, and the collection of release 4.0.1 (AD-400) that turns them
//! into symbol records. The reply takes the symbol records only; the import records stay the
//! records of the survey (AD-749).
//!
//! A class inventory is complete only when no form can add a member that the class body does
//! not show (AD-796): a mixin application, an unread part or an extension makes it partial.

use std::collections::BTreeSet;

use archkeel_facts::envelope::{Evidence, Input as Digest};
use archkeel_facts::ids::ModuleName;
use archkeel_facts::request::DartRequest;
use archkeel_facts::vocab::InventoryStatus;
use archkeel_facts::{CallFact, Record, ReferenceFact, SymbolFact};

use crate::collection::types::{Input, Output, Source};
use crate::declarations::types::{Detail, File, Symbol};
use crate::discover::{scan_roots, Discovery};
use crate::import_survey::index::{Index, Kind, Owners};
use crate::parse::DartParser;
use crate::resolve::{class_like, Resolver};
use crate::syntax::{DefinitionKind, MemberKind, Syntax};

/// The symbol, call and reference records of a survey and the evidence that they cite.
#[derive(Debug, Default)]
pub(crate) struct Collected {
    pub(crate) symbols: Vec<Record<SymbolFact>>,
    pub(crate) calls: Vec<Record<CallFact>>,
    pub(crate) references: Vec<Record<ReferenceFact>>,
    pub(crate) evidence: Vec<Evidence>,
}

/// The symbol facts of the libraries and parts of `index`. An error refuses the request; a
/// collection that stops on its limits gives no symbol, so each symbol stays UNKNOWN.
pub(crate) fn collect(
    request: &DartRequest,
    found: &Discovery,
    index: &Index<'_>,
    owners: &Owners,
    inputs: &[Digest],
) -> Result<Collected, String> {
    let mut parser = DartParser::new()?;
    let syntax: Vec<Option<Syntax>> = index
        .kinds
        .iter()
        .zip(index.sources)
        .map(|(kind, source)| (*kind != Kind::Unknown).then(|| parser.parse(&source.content)))
        .collect();
    let resolver = Resolver::new(index, owners, &syntax);
    let mut files = Vec::new();
    for (at, parsed) in syntax.iter().enumerate() {
        let (Some(module), Some(parsed)) = (resolver.module_for(at), parsed) else {
            continue;
        };
        let source = &index.sources[at];
        let content = String::from_utf8_lossy(&source.content).into_owned();
        let mut constructors = Vec::new();
        for definition in parsed
            .definitions
            .iter()
            .filter(|item| class_like(item.kind))
        {
            for member in definition
                .members
                .iter()
                .filter(|item| item.kind == MemberKind::Constructor)
            {
                constructors.push(Resolver::constructor(&resolver, at, definition, member));
            }
        }
        files.push(Source {
            file: File {
                rel: source.rel_path.clone(),
                module: source.module.clone(),
                source_len: Vec::len(&source.content),
                first_line: archkeel_pytext::splitlines(&content)
                    .first()
                    .map(|line| (*line).to_owned()),
                syntax: parsed.clone(),
                constructors,
            },
            content,
            owner: Some(module.to_owned()),
        });
    }
    let input = Input {
        files,
        package_name: found.package_name.clone(),
        sdk_state: found.sdk_state,
        sdk: found.sdk.clone(),
        roots: scan_roots(&request.scope.roots),
        inputs: inputs.to_vec(),
        problems: Vec::new(),
        resolver: Resolver::answers(&resolver),
        git_head: request.snapshot.git_head.clone(),
        dirty: request.snapshot.dirty.clone(),
    };
    let mut output = crate::collection::build(&input);
    bound_inventories(&mut output, &resolver);
    typed(output)
}

/// Make partial each class inventory that a form outside the class body can extend.
fn bound_inventories(output: &mut Output, resolver: &Resolver<'_>) {
    let libraries_with_unread_parts: BTreeSet<&str> = resolver
        .index
        .kinds
        .iter()
        .enumerate()
        .filter(|(at, kind)| **kind == Kind::Library && !resolver.parts_complete(*at))
        .filter_map(|(at, _)| resolver.module_for(at))
        .collect();
    let extended: BTreeSet<String> = extended_types(resolver);
    for symbol in &mut output.symbols {
        let Some(reason) = open_reason(symbol, resolver, &libraries_with_unread_parts, &extended)
        else {
            continue;
        };
        if let Detail::Class {
            member_inventories: Some(inventories),
            ..
        } = &mut symbol.data.detail
        {
            for inventory in inventories {
                inventory.status = InventoryStatus::Partial;
                inventory.reason = Some(reason.to_owned());
            }
        }
    }
}

/// The names of the types that a project extension names as its `on` type. An extension type is
/// a type of its own: it adds no member to the type that it wraps.
fn extended_types(resolver: &Resolver<'_>) -> BTreeSet<String> {
    let extensions = resolver
        .syntax
        .iter()
        .flatten()
        .flat_map(|parsed| &parsed.definitions)
        .filter(|item| item.kind == DefinitionKind::Extension);
    // An extension whose `on` type is not a simple name may extend any class: the empty name.
    extensions
        .map(|item| {
            let on = item
                .extends
                .first()
                .and_then(|text| crate::resolve::types::nominal(text));
            on.map_or_else(String::new, |(_, name)| name.to_owned())
        })
        .collect()
}

/// Why the inventory of the class `symbol` may miss a member, or `None` when no form outside
/// its body can add one.
fn open_reason(
    symbol: &Symbol,
    resolver: &Resolver<'_>,
    libraries_with_unread_parts: &BTreeSet<&str>,
    extended: &BTreeSet<String>,
) -> Option<&'static str> {
    if !matches!(
        symbol.data.detail,
        Detail::Class {
            member_inventories: Some(_),
            ..
        }
    ) {
        return None;
    }
    let module = ModuleName::as_str(&symbol.data.location.module);
    let name = String::as_str(&symbol.data.name);
    let declarations = resolver.local(module, name);
    let [decl] = declarations.as_slice() else {
        return Some("the class has no single declaration");
    };
    if !Vec::is_empty(&decl.definition.with_types) {
        return Some("a mixin application adds members that the class body does not show");
    }
    if libraries_with_unread_parts.contains(module) {
        return Some("not every part of the library was read");
    }
    if extended.contains(name) || extended.contains("") {
        return Some("an extension adds members that the class body does not show");
    }
    None
}

/// The records as typed facts: the collection writes the record form of release 4.0.1, which
/// the facts decode as a wire reply does. The facts parameter has no `super_formal` and no
/// `evidence_ids`, and no rule reads them, so the form drops both keys. A top-level function
/// has no method kind.
fn typed(output: Output) -> Result<Collected, String> {
    Ok(Collected {
        symbols: decode(&output.symbols, "symbol")?,
        calls: decode(&output.calls, "call")?,
        references: decode(&output.references, "reference")?,
        evidence: output.evidence,
    })
}

/// Each record of `records` as a typed record of the section `what`.
fn decode<R: serde::Serialize, T: serde::de::DeserializeOwned>(
    records: &[R],
    what: &str,
) -> Result<Vec<T>, String> {
    records
        .iter()
        .map(|record| {
            let mut value = serde_json::to_value(record).map_err(|error| error.to_string())?;
            // A top-level function is no method: it has no method kind, as TypeScript writes it.
            // 4.0.1 wrote `static`, which the model reads as a static method (AD-518).
            if value.get("kind").and_then(serde_json::Value::as_str) == Some("function") {
                let data = value
                    .get_mut("data")
                    .and_then(serde_json::Value::as_object_mut);
                data.map(|data| data.remove("method_kind"));
            }
            let parameters = value
                .get_mut("data")
                .and_then(|data| data.get_mut("parameters"))
                .and_then(serde_json::Value::as_array_mut);
            if let Some(parameters) = parameters {
                for parameter in parameters
                    .iter_mut()
                    .filter_map(serde_json::Value::as_object_mut)
                {
                    parameter.remove("super_formal");
                    parameter.remove("evidence_ids");
                }
            }
            serde_json::from_value::<T>(value)
                .map_err(|error| format!("a Dart {what} record does not decode: {error}"))
        })
        .collect()
}
