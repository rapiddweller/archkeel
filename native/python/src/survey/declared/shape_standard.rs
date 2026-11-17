// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names of the standard library that a written type reads by name (#1718, AD-782).
//!
//! The shape reader writes `typing.List[int]` as a sequence of `int` and `Optional[int]` as a
//! union, by the qualified name that the imports prove. That identity is the premise
//! `standard_library_unchanged`, as for a type of the standard library. The survey lists, for each
//! position of a signature, the collections and special forms that its annotation reads, so the
//! model can ask the premise and the changed names for them. A builtin of the language (`list`,
//! `X | None`) reads no name of a module and is not listed.

use std::collections::{BTreeMap, BTreeSet, HashSet};

use archkeel_facts::type_shape::Binding;
use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::{Expr, Stmt, StmtClassDef, StmtFunctionDef};

use super::found::Found;
use super::scope::type_names;
use super::shape_names::{Hidden, Names};
use super::shapes::{imports_by_module, module_names, read_by_name};
use crate::module::Module;
use crate::survey::binders::Binders;

/// The positions of the records of each module, keyed `<qualified name>:<position>`.
pub(crate) fn positions(
    found: &[Found<'_>],
    (modules, binders): (&[Module], &[Binders]),
    imports: &[Record<ImportFact>],
    sets: (&HashSet<String>, &HashSet<String>),
) -> BTreeMap<String, BTreeSet<String>> {
    let by_module = imports_by_module(imports);
    let mut out = BTreeMap::new();
    for item in found {
        let module = &modules[item.index];
        let names = module_names(module, &binders[item.index], &by_module, sets);
        for source in &item.sources {
            let class = source.class_names.as_ref();
            signature(&names, source.node, (&source.qualname, class), &mut out);
        }
    }
    out
}

/// The positions of the signature of `node`: each parameter by the name that its record writes
/// (`*args`, `**kwargs`), then `return`.
pub(super) fn signature(
    names: &Names<'_>,
    node: &StmtFunctionDef,
    (qualname, class): (&str, Option<&HashSet<String>>),
    out: &mut BTreeMap<String, BTreeSet<String>>,
) {
    let mut hidden = class.cloned().unwrap_or_default();
    hidden.extend(type_names(node));
    let hidden = Hidden {
        names: hidden,
        lazy: None,
    };
    let params = &node.parameters;
    // The positions are keyed by name, so their order does not matter here.
    let named = params
        .posonlyargs
        .iter()
        .chain(&params.args)
        .chain(&params.kwonlyargs);
    let mut items: Vec<(String, Option<&Expr>)> = named
        .map(|item| {
            (
                item.parameter.name.to_string(),
                item.parameter.annotation.as_deref(),
            )
        })
        .collect();
    for (prefix, item) in [("*", &params.vararg), ("**", &params.kwarg)] {
        if let Some(item) = item {
            items.push((format!("{prefix}{}", item.name), item.annotation.as_deref()));
        }
    }
    items.push(("return".to_owned(), node.returns.as_deref()));
    for (position, annotation) in items {
        record(names, (qualname, &position), annotation, &hidden, out);
    }
}

/// The positions of the generated constructor of a dataclass: each annotated field of the body.
pub(super) fn fields(
    names: &Names<'_>,
    node: &StmtClassDef,
    (qualname, hidden): (&str, &Hidden<'_>),
    out: &mut BTreeMap<String, BTreeSet<String>>,
) {
    let constructor = format!("{qualname}.__init__");
    for statement in &node.body {
        if let Stmt::AnnAssign(item) = statement {
            if let Expr::Name(target) = &*item.target {
                let position = target.id.to_string();
                record(
                    names,
                    (&constructor, &position),
                    Some(&item.annotation),
                    hidden,
                    out,
                );
            }
        }
    }
}

/// File the names of one annotation under `<qualname>:<position>`, when it reads any.
fn record(
    names: &Names<'_>,
    (qualname, position): (&str, &str),
    annotation: Option<&Expr>,
    hidden: &Hidden<'_>,
    out: &mut BTreeMap<String, BTreeSet<String>>,
) {
    let mut found = BTreeSet::new();
    read(names, annotation, hidden, &mut found);
    if !BTreeSet::is_empty(&found) {
        out.insert(format!("{qualname}:{position}"), found);
    }
}

/// Add the standard library names that `expr` reads by name to `out`.
fn read(names: &Names<'_>, expr: Option<&Expr>, hidden: &Hidden<'_>, out: &mut BTreeSet<String>) {
    let Some(expr) = expr else {
        return;
    };
    match expr {
        Expr::Name(_) | Expr::Attribute(_) => {
            let (Binding::Builtin { target } | Binding::Imported { target }) =
                Names::binding(names, expr, hidden)
            else {
                return;
            };
            if read_by_name(&target) {
                out.insert(target);
            }
        }
        Expr::Subscript(node) => {
            read(names, Some(&node.value), hidden, out);
            read(names, Some(&node.slice), hidden, out);
        }
        Expr::Tuple(node) => node
            .elts
            .iter()
            .for_each(|e| read(names, Some(e), hidden, out)),
        Expr::List(node) => node
            .elts
            .iter()
            .for_each(|e| read(names, Some(e), hidden, out)),
        Expr::BinOp(node) => {
            read(names, Some(&node.left), hidden, out);
            read(names, Some(&node.right), hidden, out);
        }
        _ => {}
    }
}
