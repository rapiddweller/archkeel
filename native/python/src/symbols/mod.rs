// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The definition table of a module: one record for each class, function and method, with the
//! fields that the module itself decides (`symbols._definition_symbol`, AD-377).
//!
//! The reply does not carry these records yet, and they are not complete: the fields that need
//! the binding proofs, the class kinds or another module are left out (AD-377 lists them). Only
//! the test dump writes them. A text that native cannot write (`Failure::Deep`, `Unseen`) gives
//! a named gap for the module and no record of it.

use std::collections::HashSet;

use archkeel_facts::identity::{stable_id, Part};
use ruff_python_ast::Expr;
use serde_json::{json, Map, Value};

use crate::pyast::{walk, Node};
use crate::survey::module::{EvidenceMap, Module};
use crate::unparse::{self, Failure};
use sites::{Def, Site};

mod callable;
mod class;
mod scan;
mod sites;
mod writes;

use scan::Scan;

/// What one module gives: its records, or the gap that names why it has none.
pub enum Table {
    Records(Vec<Value>),
    Gap { file: String, reason: String },
}

/// The definition table of one module. `witnesses` is `include_member_write_witnesses`.
pub fn table(
    module: &Module,
    all_exports: &HashSet<String>,
    minor: u32,
    witnesses: bool,
    evidence: &mut EvidenceMap,
) -> Table {
    if let Some(failure) = first_failure(module, minor) {
        return gap(module, failure);
    }
    let mut scratch = EvidenceMap::new();
    let mut scan = Scan {
        module,
        minor,
        evidence_map: &mut scratch,
    };
    let sites = sites::sites(&module.tree.body);
    let mut qualnames: Vec<String> = Vec::with_capacity(sites.len());
    let mut bound: Vec<bool> = Vec::with_capacity(sites.len());
    let mut records = Vec::with_capacity(sites.len());
    for site in &sites {
        let parent = site.parent.and_then(|index| qualnames.get(index).cloned());
        let qualname = format!(
            "{}.{}",
            parent.as_deref().unwrap_or(&module.name),
            site.def.name()
        );
        let parent_site = site.parent.and_then(|index| sites.get(index));
        let namespace_bound = match parent_site {
            None => true,
            Some(parent) => {
                matches!(parent.def, Def::Class(_))
                    && site.parent.and_then(|index| bound.get(index).copied()) == Some(true)
            }
        };
        let header = Header {
            qualname: &qualname,
            parent: parent.as_deref(),
            parent_site,
            namespace_bound,
            all_exports,
            witnesses,
        };
        match record(&mut scan, site, &header) {
            Ok(record) => records.push(record),
            Err(failure) => return gap(module, failure),
        }
        qualnames.push(qualname);
        bound.push(namespace_bound);
    }
    evidence.extend(scratch);
    records.sort_by(|left, right| left["id"].as_str().cmp(&right["id"].as_str()));
    Table::Records(records)
}

fn gap(module: &Module, failure: Failure) -> Table {
    let cause = match failure {
        Failure::Deep => format!(
            "an expression nests deeper than {} levels; Python writes its text up to its \
             RecursionError (from about 158 levels)",
            unparse::MAX_DEPTH
        ),
        Failure::Unseen => {
            "a string has a lone surrogate escape that the parser replaced".to_owned()
        }
        Failure::Spec312 => {
            "a format spec that Python 3.12 reads in its own way (\\N{...}, or a backslash in a \
             raw spec)"
                .to_owned()
        }
        Failure::SpecDepth => "a format spec nests deeper than two levels".to_owned(),
        Failure::Version => "the interpreter is outside Python 3.11 to 3.14".to_owned(),
        Failure::Invalid => "an expression has no text (ValueError)".to_owned(),
    };
    Table::Gap {
        file: module.rel.clone(),
        reason: format!("Symbols unseen: {}: {cause}", module.rel),
    }
}

/// The first string of the module whose CPython value or tree native cannot write.
fn first_failure(module: &Module, minor: u32) -> Option<Failure> {
    if !unparse::MINORS.contains(&minor) {
        return Some(Failure::Version);
    }
    module
        .tree
        .body
        .iter()
        .flat_map(|stmt| walk(Node::Stmt(stmt), minor))
        .filter_map(|node| node.expr())
        .find_map(|expr| unparse::string_failure(expr, module.text(), minor))
}

struct Header<'h> {
    qualname: &'h str,
    parent: Option<&'h str>,
    parent_site: Option<&'h Site<'h>>,
    namespace_bound: bool,
    all_exports: &'h HashSet<String>,
    witnesses: bool,
}

/// `definition_id`: the qualified name and the location of the `def` or `class` keyword.
fn definition_id(module: &Module, def: Def<'_>, qualname: &str) -> String {
    let (line, _, column) = module.location(&def.range(module.text()));
    stable_id(
        "SYM",
        &[
            Part::Text(qualname),
            Part::Text(&module.rel),
            Part::Number(line),
            Part::Number(column),
        ],
    )
}

fn record(scan: &mut Scan<'_>, site: &Site<'_>, header: &Header<'_>) -> Result<Value, Failure> {
    let module = scan.module;
    let def = site.def;
    let name = def.name();
    let classifier = matches!(
        header.parent_site.map(|parent| parent.def),
        Some(Def::Class(_))
    );
    let mut data = Map::new();
    data.insert("qualified_name".into(), json!(header.qualname));
    data.insert("module".into(), json!(module.name));
    data.insert("package".into(), json!(module.package));
    data.insert("name".into(), json!(name));
    let visibility = if name.starts_with('_') {
        "private"
    } else {
        "public_name"
    };
    data.insert("visibility".into(), json!(visibility));
    data.insert("visibility_detail".into(), class::visibility(name));
    data.insert(
        "declared_in_all".into(),
        json!(header.all_exports.contains(name)),
    );
    data.insert("parent".into(), json!(header.parent));
    data.insert("decorators".into(), json!(decorators(scan, def)?));
    let mut scope = None;
    let kind = match def {
        Def::Class(node) => {
            data.insert("symbol_category".into(), json!("class"));
            scope = class::class_data(scan, node, header.witnesses, &mut data)?;
            "class"
        }
        Def::Function(node) => {
            callable::signature(scan, node, &mut data)?;
            data.insert(
                "parameters_contained".into(),
                json!(callable::parameters_contained(node, scan.minor)),
            );
            if name == "__init__" {
                data.insert(
                    "stored_field_writes".into(),
                    callable::stored_field_writes(scan, node),
                );
            }
            let category = if classifier { "method" } else { "function" };
            data.insert("symbol_category".into(), json!(category));
            let (shape, nodes) = callable::shape(node, scan.minor);
            data.insert("shape".into(), json!(shape));
            data.insert("shape_nodes".into(), json!(nodes));
            category
        }
    };
    data.insert("namespace_bound".into(), json!(header.namespace_bound));
    let contexts: Vec<Value> = site
        .contexts
        .iter()
        .map(|context| {
            json!({
                "kind": context.kind,
                "branch": context.branch,
                "evidence_ids": [scan.evidence(&context.site)],
            })
        })
        .collect();
    data.insert("definition_contexts".into(), Value::Array(contexts));
    let lexical_parent = match (header.parent_site, header.parent) {
        (Some(parent), Some(qualname)) => Some(definition_id(module, parent.def, qualname)),
        _ => None,
    };
    data.insert("lexical_parent_id".into(), json!(lexical_parent));
    let mut evidence_ids = vec![scan.evidence(&def.range(module.text()))];
    evidence_ids.extend(scope);
    evidence_ids.sort();
    let mut subjects = vec![header.qualname.to_owned(), module.name.clone()];
    subjects.sort();
    Ok(json!({
        "id": definition_id(module, def, header.qualname),
        "evidence_class": "FACT",
        "area": "repository_topology",
        "kind": kind,
        "title": name,
        "subjects": subjects,
        "evidence_ids": evidence_ids,
        "data": Value::Object(data),
    }))
}

/// `decorator_names`: the sorted text of each decorator, of its callee for a call.
fn decorators(scan: &Scan<'_>, def: Def<'_>) -> Result<Vec<String>, Failure> {
    let list = match def {
        Def::Function(node) => &node.decorator_list,
        Def::Class(node) => &node.decorator_list,
    };
    let mut names = Vec::new();
    for decorator in list {
        let target = match &decorator.expression {
            Expr::Call(call) => &*call.func,
            expression => expression,
        };
        match unparse::unparse(target, scan.minor, scan.module.text()) {
            Ok(text) => names.push(text),
            Err(Failure::Invalid) => {}
            Err(failure) => return Err(failure),
        }
    }
    names.sort();
    Ok(names)
}

#[cfg(test)]
#[path = "symbols_tests.rs"]
mod tests;
