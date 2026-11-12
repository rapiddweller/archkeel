// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The fields of a class that need only its own node (`symbols.py`): the bases as text, the
//! fields, `_class_attribute_declarations`, `_guard_boolean_member_declarations`,
//! `_class_member_names`, `_generic_bases` and `_member_write_scope_evidence`.

use std::collections::{BTreeMap, BTreeSet, HashSet};

use archkeel_facts::envelope::Evidence;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::EvidenceId;
use ruff_python_ast::{Expr, Stmt, StmtAnnAssign, StmtClassDef, StmtFunctionDef};
use ruff_text_size::TextRange;
use serde_json::{json, Map, Value};

use super::scan::Scan;
use super::writes::{self, store_names};
use crate::pyast::{walk, Node};
use crate::unparse::Failure;

/// `MAX_NUMERIC_EVIDENCE_CHARS`: a longer class has no member write scope evidence.
const MAX_EXCERPT_CHARS: usize = 16_384;

pub fn class_data(
    scan: &mut Scan<'_>,
    node: &StmtClassDef,
    witnesses: bool,
    data: &mut Map<String, Value>,
) -> Result<Option<String>, Failure> {
    let bases: &[Expr] = node
        .arguments
        .as_deref()
        .map_or(&[], |arguments| &arguments.args);
    let mut texts = Vec::new();
    for base in bases {
        texts.extend(scan.text(Some(base))?);
    }
    texts.sort();
    data.insert("bases".into(), json!(texts));
    data.insert("fields".into(), fields(scan, node)?);
    data.insert(
        "attribute_declarations".into(),
        attribute_declarations(scan, node)?,
    );
    data.insert(
        "class_members".into(),
        json!(member_names(node, scan.minor)),
    );
    let writes = writes::instance_member_writes(node, scan.minor);
    data.insert("instance_member_writes".into(), json!(writes));
    let scope = if witnesses {
        scope_evidence(scan, node)
    } else {
        None
    };
    data.insert("instance_member_scope_evidence_id".into(), json!(scope));
    let generic = generic_bases(scan, bases)?;
    if !generic.is_empty() {
        data.insert("generic_bases".into(), Value::Array(generic));
    }
    let guards = guard_boolean_members(scan, node)?;
    if !guards.is_empty() {
        data.insert("guard_boolean_members".into(), Value::Array(guards));
    }
    Ok(scope)
}

fn fields(scan: &Scan<'_>, node: &StmtClassDef) -> Result<Value, Failure> {
    let mut found = Vec::new();
    for child in &node.body {
        let Stmt::AnnAssign(assign) = child else {
            continue;
        };
        let Expr::Name(target) = &*assign.target else {
            continue;
        };
        if !target.id.starts_with('_') {
            let annotation = scan.text(Some(&assign.annotation))?;
            found.push(json!({"name": target.id.as_str(), "annotation": annotation}));
        }
    }
    Ok(Value::Array(found))
}

/// `_python_visibility`: private by the leading underscore, except a special name.
pub fn visibility(name: &str) -> Value {
    let special = name.starts_with("__") && name.ends_with("__") && name.chars().count() > 4;
    let kind = if name.starts_with('_') && !special {
        "private"
    } else {
        "public"
    };
    json!({"kind": kind, "basis": "convention", "spelling": name})
}

fn attribute_declarations(scan: &mut Scan<'_>, node: &StmtClassDef) -> Result<Value, Failure> {
    let mut found = Vec::new();
    for child in &node.body {
        let (targets, annotation, value, assign) = match child {
            Stmt::AnnAssign(assign) => match &*assign.target {
                Expr::Name(target) => (
                    vec![target.id.to_string()],
                    scan.text(Some(&assign.annotation))?,
                    assign.value.as_deref(),
                    false,
                ),
                _ => continue,
            },
            Stmt::Assign(assign) => (
                store_names(&assign.targets, scan.minor),
                None,
                Some(&*assign.value),
                true,
            ),
            _ => continue,
        };
        let literal = match value {
            Some(Expr::StringLiteral(text)) => Some(scan.string(text)?),
            _ => None,
        };
        let (line, end_line, column) = scan.module.location(child);
        for name in targets {
            let id = stable_id(
                "ATTR",
                &[
                    Part::Text(&scan.module.rel),
                    Part::Number(line),
                    Part::Number(end_line),
                    Part::Number(column),
                    Part::Text(&name),
                ],
            );
            let mut item = json!({
                "name": name,
                "annotation": annotation,
                "visibility": visibility(&name),
                "definition_id": id,
                "evidence_ids": [scan.evidence(child)],
            });
            if assign {
                item["static"] = json!(true);
            }
            if let Some(literal) = &literal {
                item["literal_value"] = json!(literal);
            }
            found.push(item);
        }
    }
    Ok(Value::Array(found))
}

fn member_names(node: &StmtClassDef, minor: u32) -> Vec<String> {
    let mut names = BTreeSet::new();
    let mut deleted = HashSet::new();
    for child in &node.body {
        match child {
            Stmt::FunctionDef(def) => {
                names.insert(def.name.to_string());
            }
            Stmt::ClassDef(def) => {
                names.insert(def.name.to_string());
            }
            Stmt::AnnAssign(assign) if assign.value.is_some() => {
                names.extend(store_names(std::slice::from_ref(&*assign.target), minor));
            }
            Stmt::Assign(assign) => names.extend(store_names(&assign.targets, minor)),
            Stmt::Import(import) => names.extend(
                import
                    .names
                    .iter()
                    .map(|alias| alias.asname.as_ref().unwrap_or(&alias.name).to_string()),
            ),
            Stmt::ImportFrom(import) => names.extend(
                import
                    .names
                    .iter()
                    .filter(|alias| alias.name.as_str() != "*")
                    .map(|alias| alias.asname.as_ref().unwrap_or(&alias.name).to_string()),
            ),
            Stmt::Delete(delete) => {
                deleted.extend(delete.targets.iter().filter_map(|target| match target {
                    Expr::Name(name) => Some(name.id.to_string()),
                    _ => None,
                }))
            }
            _ => {}
        }
    }
    names
        .into_iter()
        .filter(|name| !deleted.contains(name))
        .collect()
}

fn generic_bases(scan: &Scan<'_>, bases: &[Expr]) -> Result<Vec<Value>, Failure> {
    let mut found = Vec::new();
    for base in bases {
        let Expr::Subscript(subscript) = base else {
            continue;
        };
        let arguments: Vec<&Expr> = match &*subscript.slice {
            Expr::Tuple(tuple) => tuple.elts.iter().collect(),
            slice => vec![slice],
        };
        let mut texts = Vec::new();
        for argument in &arguments {
            texts.push(scan.text(Some(argument))?.unwrap_or_default());
        }
        found.push(json!({
            "base": scan.text(Some(&subscript.value))?.unwrap_or_default(),
            "arguments": texts,
            "arguments_are_names": arguments.iter().map(|item| matches!(item, Expr::Name(_))).collect::<Vec<_>>(),
        }));
    }
    Ok(found)
}

/// `_guard_boolean_member_declarations`: the members declared `bool` exactly once, in the class
/// body or as `<receiver>.<name>: bool` anywhere in a method.
fn guard_boolean_members(scan: &mut Scan<'_>, node: &StmtClassDef) -> Result<Vec<Value>, Failure> {
    let mut candidates: Vec<(String, TextRange)> = Vec::new();
    for child in &node.body {
        match child {
            Stmt::AnnAssign(assign) => body_guard(scan, assign, &mut candidates)?,
            Stmt::FunctionDef(method) => method_guards(scan, child, method, &mut candidates)?,
            _ => {}
        }
    }
    let mut first: BTreeMap<String, TextRange> = BTreeMap::new();
    let mut ambiguous = HashSet::new();
    for (name, range) in candidates {
        if let std::collections::btree_map::Entry::Vacant(entry) = first.entry(name.clone()) {
            entry.insert(range);
        } else {
            ambiguous.insert(name);
        }
    }
    let mut found = Vec::new();
    for (name, range) in first {
        if !ambiguous.contains(&name) {
            found.push(json!({"name": name, "evidence_ids": [scan.evidence(&range)]}));
        }
    }
    Ok(found)
}

fn body_guard(
    scan: &Scan<'_>,
    assign: &StmtAnnAssign,
    out: &mut Vec<(String, TextRange)>,
) -> Result<(), Failure> {
    let Expr::Name(target) = &*assign.target else {
        return Ok(());
    };
    if scan.text(Some(&assign.annotation))?.as_deref() == Some("bool") {
        out.push((target.id.to_string(), assign.range));
    }
    Ok(())
}

fn method_guards(
    scan: &Scan<'_>,
    child: &Stmt,
    method: &StmtFunctionDef,
    out: &mut Vec<(String, TextRange)>,
) -> Result<(), Failure> {
    let params = &method.parameters;
    let Some(receiver) = params.posonlyargs.iter().chain(&params.args).next() else {
        return Ok(());
    };
    let receiver = receiver.parameter.name.as_str();
    for item in walk(Node::Stmt(child), scan.minor) {
        let Node::Stmt(Stmt::AnnAssign(assign)) = item else {
            continue;
        };
        let Expr::Attribute(target) = &*assign.target else {
            continue;
        };
        let on_receiver =
            matches!(&*target.value, Expr::Name(name) if name.id.as_str() == receiver);
        if on_receiver && scan.text(Some(&assign.annotation))?.as_deref() == Some("bool") {
            out.push((target.attr.to_string(), assign.range));
        }
    }
    Ok(())
}

/// `_member_write_scope_evidence`: the whole class text as one evidence entry.
fn scope_evidence(scan: &mut Scan<'_>, node: &StmtClassDef) -> Option<String> {
    let range = super::sites::Def::Class(node).range(scan.module.text());
    let (line, end_line, column) = scan.module.location(&range);
    // Each line adds at least one character, so a longer class is over the limit.
    if end_line.saturating_sub(line) > i64::try_from(MAX_EXCERPT_CHARS).unwrap_or(i64::MAX) {
        return None;
    }
    let excerpt = scan.module.excerpt(line, end_line)?;
    if excerpt.is_empty() || excerpt.chars().count() > MAX_EXCERPT_CHARS {
        return None;
    }
    let id = stable_id(
        "EVD",
        &[
            Part::Text(&scan.module.rel),
            Part::Number(line),
            Part::Number(end_line),
            Part::Number(column),
            Part::Text("member_write_scope"),
        ],
    );
    let item = Evidence {
        id: EvidenceId::new(id.clone()),
        file: scan.module.rel.clone(),
        line,
        end_line,
        column,
        excerpt,
    };
    scan.evidence_map.insert(id.clone(), item);
    Some(id)
}
