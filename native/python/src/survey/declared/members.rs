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
use ruff_python_ast::{Expr, Stmt, StmtClassDef, StmtFunctionDef, UnaryOp};
use ruff_text_size::Ranged;

use super::kind::Kind;
use super::reader::{Reader, Unwritable};
use crate::declare::visibility;
use crate::survey::binders::Binders;
use crate::survey::bound::Bound;

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
    for statement in &node.body {
        let start = statement.range().start();
        let (names, annotation) = match statement {
            Stmt::AnnAssign(assign) => match &*assign.target {
                Expr::Name(name) if !enumeration => {
                    (vec![name.id.as_str()], scan.text(Some(&assign.annotation))?)
                }
                _ if enumeration => return Ok(open()),
                _ => continue,
            },
            Stmt::Assign(assign) => {
                let names: Vec<&str> = assign.targets.iter().filter_map(plain_name).collect();
                let plain = names.len() == assign.targets.len();
                if enumeration && !(plain && enum_literal(assign, &names)) {
                    return Ok(open());
                }
                if !plain {
                    continue;
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
    names.len() == 1 && !names[0].starts_with('_') && constant(&assign.value)
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
        return node
            .decorator_list
            .is_empty()
            .then_some(MethodKind::Instance);
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
