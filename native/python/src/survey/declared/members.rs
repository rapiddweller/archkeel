// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The members of a class that its body binds once (AD-518, rules 3, 5 and 7): the attributes
//! with the enum literals, and the decorator of a method.
//!
//! The reader looks at the direct statements of the body only. Whatever another statement binds
//! (`if`, `for`, `del`, a walrus, `global`) makes `Bound::sole` false for that name, so a name is
//! never written when anything else can bind it.

use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::nested::{AttributeDeclaration, VisibilityDetail};
use archkeel_facts::vocab::MethodKind;
use std::collections::HashSet;

use ruff_python_ast::{Expr, Number, Stmt, StmtClassDef, StmtFunctionDef, UnaryOp};
use ruff_text_size::Ranged;

use super::kind::Kind;
use super::reader::{Reader, Unwritable};
use crate::declare::visibility;
use crate::module::builtin_roles::{self, Role};
use crate::survey::binders::Binders;
use crate::survey::bound::Bound;
use crate::survey::class_writes::ClassWrites;
use crate::survey::value::assignment_parts;

/// The attributes of a class and, for an enum, the names of its literals.
pub(super) struct Attributes {
    pub declarations: Vec<AttributeDeclaration>,
    pub literals: Option<Vec<String>>,
}

/// The declared attributes of a class body. An enum lists a name only when the whole body is
/// proven: constants for literals, methods, a docstring and `pass`; else it lists none.
pub(super) fn attributes(
    scan: &mut Reader<'_, '_>,
    node: &StmtClassDef,
    bound: &Bound,
    kind: Kind,
) -> Result<Attributes, Unwritable> {
    let enumeration = kind == Kind::Enum;
    let mut found = Vec::new();
    let mut keys = HashSet::new();
    for statement in &node.body {
        let start = statement.range().start();
        let (names, annotation) = match statement {
            // A bare annotation declares an instance attribute without binding a value (AD-748).
            Stmt::AnnAssign(assign) => match (&*assign.target, assign.value.as_deref()) {
                (_, _) if enumeration => return Ok(open()),
                (Expr::Name(name), Some(value)) if constant(value) => {
                    (vec![name.id.as_str()], scan.text(Some(&assign.annotation))?)
                }
                (Expr::Name(name), None)
                    if matches!(&*assign.annotation, Expr::Name(annotation)
                        if builtin_roles::named(Role::ANNOTATION).any(|builtin| builtin == annotation.id.as_str())
                        && !bound.names().contains(annotation.id.as_str())
                        && !namespace_holds(scan, &node.body, annotation.id.as_str())) =>
                {
                    (vec![name.id.as_str()], scan.text(Some(&assign.annotation))?)
                }
                _ => continue,
            },
            Stmt::Assign(assign) => {
                let names: Vec<&str> = assign.targets.iter().filter_map(plain_name).collect();
                let plain = names.len() == assign.targets.len();
                if enumeration && !(plain && enum_literal(assign, &names)) {
                    return Ok(open());
                }
                if !plain || (!enumeration && !constant(&assign.value)) {
                    continue;
                }
                let key = value_key(&assign.value);
                if enumeration && !key.is_some_and(|key| keys.insert(key)) {
                    return Ok(open());
                }
                (names, None)
            }
            other => {
                if enumeration && !inert(other) {
                    return Ok(open());
                }
                continue;
            }
        };
        for name in names {
            if mangled(name) && enumeration {
                return Ok(open());
            }
            if mangled(name) {
                continue;
            }
            if bound.sole(name, start) {
                found.push(declaration(scan, statement, name, annotation.clone()));
            } else if enumeration {
                return Ok(open());
            }
        }
    }
    let literals = enumeration.then(|| found.iter().map(|item| item.name.clone()).collect());
    Ok(Attributes {
        declarations: found,
        literals,
    })
}

/// An enum whose body is not proven lists no member: a literal that the scan does not name is
/// absent, never an attribute.
pub(super) fn open() -> Attributes {
    Attributes {
        declarations: Vec::new(),
        literals: None,
    }
}

/// `__x` is `_A__x` at run time: the name is no member of the class under its written name.
pub(super) fn mangled(name: &str) -> bool {
    name.starts_with("__") && !name.ends_with("__")
}

/// The value of an enum literal, so that `R = 1; S = 1` is seen as an alias. Only a string and an
/// integer have a key: `1`, `1.0` and `True` are one value, so a float, a bool, bytes, `None` and
/// a tuple leave the enum open.
fn value_key(value: &Expr) -> Option<String> {
    match value {
        Expr::StringLiteral(node) => Some(format!("s:{}", node.value.to_str())),
        Expr::NumberLiteral(node) => int_key(&node.value, ""),
        Expr::UnaryOp(node) => match (&node.op, &*node.operand) {
            (UnaryOp::USub, Expr::NumberLiteral(inner)) => int_key(&inner.value, "-"),
            _ => None,
        },
        _ => None,
    }
}

fn int_key(number: &Number, sign: &str) -> Option<String> {
    match number {
        Number::Int(value) if value.to_string() == "0" => Some("i:0".to_owned()),
        Number::Int(value) => Some(format!("i:{sign}{value}")),
        _ => None,
    }
}

fn plain_name(target: &Expr) -> Option<&str> {
    match target {
        Expr::Name(name) => Some(name.id.as_str()),
        _ => None,
    }
}

/// A statement of an enum body that binds no member and no other name.
fn inert(statement: &Stmt) -> bool {
    match statement {
        Stmt::Pass(_) => true,
        Stmt::Expr(node) => matches!(&*node.value, Expr::StringLiteral(_)),
        Stmt::FunctionDef(node) => node.decorator_list.is_empty(),
        _ => false,
    }
}

/// `NAME = constant`: a member (not a descriptor, not a private or special name).
fn enum_literal(assign: &ruff_python_ast::StmtAssign, names: &[&str]) -> bool {
    names.len() == 1 && !names[0].starts_with('_') && names[0] != "mro" && constant(&assign.value)
}

fn constant(value: &Expr) -> bool {
    match value {
        Expr::StringLiteral(_)
        | Expr::NumberLiteral(_)
        | Expr::BooleanLiteral(_)
        | Expr::NoneLiteral(_)
        | Expr::BytesLiteral(_) => true,
        Expr::UnaryOp(node) => {
            matches!(node.op, UnaryOp::USub | UnaryOp::UAdd)
                && matches!(&*node.operand, Expr::NumberLiteral(_))
        }
        Expr::Tuple(node) => node.elts.iter().all(constant),
        _ => false,
    }
}

/// `_class_attribute_declarations` for one name of one statement.
fn declaration(
    scan: &mut Reader<'_, '_>,
    statement: &Stmt,
    name: &str,
    annotation: Option<String>,
) -> AttributeDeclaration {
    let crate::module::Location {
        line,
        end_line,
        column,
    } = scan.module.location(statement);
    let id = stable_id(
        "ATTR",
        &[
            Part::Text(&scan.module.rel),
            Part::Number(line),
            Part::Number(end_line),
            Part::Number(column),
            Part::Text(name),
        ],
    );
    let detail = visibility(name);
    AttributeDeclaration {
        annotation,
        constant: archkeel_facts::nullable::Nullable::Absent,
        decorator_evidence_ids: None,
        decorators: None,
        definition_id: FactId::new(id),
        evidence_ids: vec![EvidenceId::new(scan.evidence(statement))],
        literal_value: None,
        name: name.to_owned(),
        is_static: matches!(statement, Stmt::Assign(_)).then_some(true),
        visibility: serde_json::from_value::<VisibilityDetail>(detail).unwrap_or_else(|_| {
            VisibilityDetail {
                basis: "convention".to_owned(),
                kind: "public".to_owned(),
                spelling: name.to_owned(),
            }
        }),
    }
}

/// The method kind that the decorators of a method give, or `None` when a decorator may replace
/// the function (rule 5). `staticmethod` and `classmethod` count only as the builtins.
pub(super) fn method_kind(node: &StmtFunctionDef, binders: &Binders) -> Option<MethodKind> {
    let [decorator] = node.decorator_list.as_slice() else {
        // `__new__` is a static method, and the two hooks are class methods, without a decorator.
        return node
            .decorator_list
            .is_empty()
            .then(|| match node.name.as_str() {
                "__new__" => MethodKind::Static,
                "__init_subclass__" | "__class_getitem__" => MethodKind::Class,
                _ => MethodKind::Instance,
            });
    };
    match &decorator.expression {
        Expr::Name(name) if binders.builtin_visible(name.id.as_str()) => match name.id.as_str() {
            "staticmethod" => Some(MethodKind::Static),
            "classmethod" => Some(MethodKind::Class),
            _ => None,
        },
        _ => None,
    }
}

/// True when the namespace of the class can hold `name` when its annotation is read (#1714): a
/// `__slots__` entry (a member of the class), or, when the annotation is read late, a store of
/// the name in a file of the scan or a non-test file of the repository (AD-802).
fn namespace_holds(scan: &Reader<'_, '_>, body: &[Stmt], name: &str) -> bool {
    let slot = slots(body).is_none_or(|names| names.contains(name));
    slot || scan
        .writes
        .is_some_and(|writes| ClassWrites::can_write(writes, name))
}

/// The `__slots__` entries of a class body (#1523): each string of a literal string, tuple, list,
/// set or dict key. `None` when the body binds `__slots__` in any other form: a slot gets a member
/// in the class namespace, so a computed list can hold any name.
pub(super) fn slots(body: &[Stmt]) -> Option<HashSet<String>> {
    let mut found = HashSet::new();
    for stmt in body {
        let parts = match stmt {
            Stmt::AugAssign(node) => Some((vec![&*node.target], None)),
            _ => assignment_parts(stmt),
        };
        let Some((targets, value)) = parts else {
            continue;
        };
        let named =
            |target: &&Expr| matches!(target, Expr::Name(name) if name.id.as_str() == "__slots__");
        if !targets.iter().any(named) {
            continue;
        }
        found.extend(slot_names(value?)?);
    }
    Some(found)
}

fn slot_names(value: &Expr) -> Option<Vec<String>> {
    let items: Vec<&Expr> = match value {
        Expr::StringLiteral(_) => vec![value],
        Expr::Tuple(node) => node.elts.iter().collect(),
        Expr::List(node) => node.elts.iter().collect(),
        Expr::Set(node) => node.elts.iter().collect(),
        Expr::Dict(node) => node
            .items
            .iter()
            .map(|item| item.key.as_ref())
            .collect::<Option<_>>()?,
        _ => return None,
    };
    items
        .into_iter()
        .map(|item| match item {
            Expr::StringLiteral(text) => Some(text.value.to_str().to_owned()),
            _ => None,
        })
        .collect()
}

/// Why a member list is never complete: a base, a metaclass, a decorator and a write after the
/// class body can add a member that the body does not show.
const PARTIAL: &str =
    "a base, a metaclass, a decorator or a write after the class body can add a member";

/// The partial member inventory of one kind of a class.
pub(super) fn inventory(
    kind: archkeel_facts::vocab::MemberKind,
    definition_ids: Vec<FactId>,
) -> archkeel_facts::nested::MemberInventory {
    archkeel_facts::nested::MemberInventory {
        definition_ids,
        kind,
        reason: Some(PARTIAL.to_owned()),
        schema_version: "1.0.0".to_owned(),
        status: archkeel_facts::vocab::InventoryStatus::Partial,
    }
}
