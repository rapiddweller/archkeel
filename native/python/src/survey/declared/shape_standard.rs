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

use archkeel_facts::standard::ProtocolMembers;
use archkeel_facts::type_shape::{Binding, TypeShape};
use archkeel_facts::{FactData, ImportFact, Record, SymbolFact};
use ruff_python_ast::{Expr, Stmt, StmtClassDef, StmtFunctionDef};

use super::found::Found;
use super::scope::type_names;
use super::shape_names::{Hidden, Lazy, Names};
use super::shapes::{imports_by_module, module_names, no_nested_classes, read_by_name, Shaper};
use crate::module::EvidenceMap;
use crate::module::Module;
use crate::survey::binders::Binders;
use crate::survey::bound::Bound;
use crate::survey::class_writes::{future_annotations, ClassWrites};
use ruff_text_size::Ranged;

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

/// Read known members and account for unread classes in each module.
pub(crate) fn protocol_positions(
    found: &[Found<'_>],
    (modules, binders): (&[Module], &[Binders]),
    imports: &[Record<ImportFact>],
    sets: (&HashSet<String>, &HashSet<String>),
    (evidence, writes, lazy): (&mut EvidenceMap, &ClassWrites, bool),
) -> BTreeMap<String, (bool, ProtocolMembers)> {
    let by_module = imports_by_module(imports);
    let mut out = BTreeMap::new();
    for item in found {
        let module = &modules[item.index];
        let names = module_names(module, &binders[item.index], &by_module, sets);
        let late = lazy || future_annotations(&module.tree);
        let shaper = Shaper {
            names: &names,
            lazy: late.then_some(writes),
        };
        out.insert(
            module.name.clone(),
            at_module(item, module, &shaper, (evidence, writes)),
        );
    }
    out
}

fn at_module(
    found: &Found<'_>,
    module: &Module,
    shaper: &Shaper<'_>,
    (evidence, writes): (&mut EvidenceMap, &ClassWrites),
) -> (bool, ProtocolMembers) {
    let mut closed = true;
    let mut members = Vec::new();
    for stmt in &module.tree.body {
        match stmt {
            Stmt::ClassDef(node) => {
                if let Some(rows) = class_members(found, module, shaper, (evidence, writes), node) {
                    members.extend(rows);
                } else {
                    closed = false;
                }
            }
            Stmt::Import(_) | Stmt::ImportFrom(_) | Stmt::Pass(_) => {}
            Stmt::Expr(expr) if matches!(&*expr.value, Expr::StringLiteral(_)) => {}
            Stmt::FunctionDef(node) if no_nested_classes(&node.body) => {}
            _ => closed = false,
        }
    }
    (closed, members)
}

fn class_members(
    found: &Found<'_>,
    module: &Module,
    shaper: &Shaper<'_>,
    (evidence, writes): (&mut EvidenceMap, &ClassWrites),
    node: &StmtClassDef,
) -> Option<ProtocolMembers> {
    let owner = format!("{}.{}", module.name, node.name);
    let closed = found.records.iter().any(|record| {
        matches!(&record.data, SymbolFact::Class(class) if class.class_members.is_some())
            && record.data.fields().qualified_name == Some(String::as_str(&owner))
    });
    if !closed
        || node.type_params.is_some()
        || !matches!(node.decorator_list.as_slice(), [])
        || node
            .arguments
            .as_ref()
            .is_some_and(|args| !matches!(args.keywords.as_slice(), []))
    {
        return None;
    }
    let bound = Bound::of(&node.body);
    if !bound.unbound("__annotations__")
        || !bound.unbound("__annotate__")
        || shaper.lazy.is_some_and(|writes| {
            !bound.unbound("__slots__")
                || ClassWrites::can_write(writes, "__annotations__")
                || ClassWrites::can_write(writes, "__annotate__")
        })
    {
        return None;
    }
    let no_slots = HashSet::new();
    let hidden = Hidden {
        names: bound.names(),
        lazy: shaper.lazy.map(|writes| Lazy {
            writes,
            slots: Some(&no_slots),
        }),
    };
    let mut members = Vec::new();
    for stmt in &node.body {
        let (name, annotation) = match stmt {
            Stmt::AnnAssign(assign) => (plain_name(&assign.target)?, Some(&*assign.annotation)),
            Stmt::Assign(assign) => {
                let [target] = assign.targets.as_slice() else {
                    return None;
                };
                (plain_name(target)?, None)
            }
            Stmt::Expr(expr) if matches!(&*expr.value, Expr::StringLiteral(_)) => continue,
            Stmt::FunctionDef(func)
                if matches!(func.decorator_list.as_slice(), [])
                    && no_nested_classes(&func.body) =>
            {
                continue
            }
            Stmt::Pass(_) => continue,
            _ => return None,
        };
        if !bound.sole(name, stmt.start()) {
            return None;
        }
        let shape = shaper.position(annotation, &hidden);
        if annotation_binding_can_change(&shape, writes) {
            return None;
        }
        let cite = module.evidence(evidence, stmt);
        members.push((owner.clone(), name.to_owned(), shape, cite));
    }
    Some(members)
}

fn annotation_binding_can_change(shape: &TypeShape, writes: &ClassWrites) -> bool {
    let name = match shape {
        TypeShape::Dynamic { name, .. } | TypeShape::Primitive { name, .. } => name,
        TypeShape::Named {
            binding: Binding::Defined { target } | Binding::Imported { target },
            ..
        } => target
            .rsplit_once('.')
            .map_or(String::as_str(target), |(_, name)| name),
        _ => return false,
    };
    ClassWrites::can_write(writes, name)
}

fn plain_name(expr: &Expr) -> Option<&str> {
    match expr {
        Expr::Name(name) => Some(ruff_python_ast::name::Name::as_str(&name.id)),
        _ => None,
    }
}
