// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reading of one module for its declarations (AD-518): the evidence of a node, and the text
//! of an annotation or a default.
//!
//! The text is written for a name, a dotted name, a call of one without arguments, `None`, `True`
//! and `False` only. That is what
//! `ast.unparse` writes for them in every Python of the request. Any other expression (a
//! subscript, a string, a number, a call) gives `Unwritable`, and the declaration that holds it
//! gets no record: the survey never guesses a text.

use crate::module::builtin_roles::{self, Role};
use ruff_python_ast::Expr;
use ruff_text_size::Ranged;

use archkeel_facts::data::Declared;
use archkeel_facts::ids::{FactId, ModuleName, PackageName};
use archkeel_facts::nested::VisibilityDetail;

use crate::declare::visibility;
use crate::module::{EvidenceMap, Module};
use crate::survey::binders::Binders;

/// An expression whose text this reader does not write.
#[derive(Debug, PartialEq, Eq)]
pub(super) struct Unwritable;

pub(super) struct Reader<'m, 'e> {
    pub module: &'m Module,
    pub evidence_map: &'e mut EvidenceMap,
    /// The builtin type names that the module binds somewhere: their text names something else.
    pub shadowed: Vec<&'static str>,
}

impl Reader<'_, '_> {
    /// The builtin names that `binders` shows bound in the module.
    pub(super) fn shadowed(binders: &Binders) -> Vec<&'static str> {
        let hidden = |name: &&'static str| !binders.builtin_visible(name);
        builtin_roles::named(Role::ANNOTATION)
            .filter(hidden)
            .collect()
    }
}

impl Reader<'_, '_> {
    /// The text of an optional expression.
    pub(super) fn text(&self, expr: Option<&Expr>) -> Result<Option<String>, Unwritable> {
        expr.map(|expr| plain(expr, &self.shadowed)).transpose()
    }

    /// `add_evidence`.
    pub(super) fn evidence(&mut self, node: &impl Ranged) -> String {
        self.module.evidence(self.evidence_map, node)
    }
}

fn plain(expr: &Expr, shadowed: &[&str]) -> Result<String, Unwritable> {
    match expr {
        Expr::Name(node) if shadowed.contains(&node.id.as_str()) => Err(Unwritable),
        Expr::Name(node) => Ok(node.id.to_string()),
        Expr::Attribute(node) => Ok(format!(
            "{}.{}",
            plain(&node.value, shadowed)?,
            node.attr.as_str()
        )),
        Expr::Call(node)
            if node.arguments.args.is_empty() && node.arguments.keywords.is_empty() =>
        {
            Ok(format!("{}()", plain(&node.func, shadowed)?))
        }
        Expr::NoneLiteral(_) => Ok("None".to_owned()),
        Expr::BooleanLiteral(node) => Ok(if node.value { "True" } else { "False" }.to_owned()),
        _ => Err(Unwritable),
    }
}

/// The header of a declaration of `module`: `(name, holder)` give its qualified name, and the
/// visibility is what the name reads (AD-518).
pub(super) fn header(
    module: &Module,
    (name, holder): (&str, &str),
    parent: Option<(&str, &str)>,
) -> Declared {
    let detail =
        serde_json::from_value::<VisibilityDetail>(visibility(name)).unwrap_or(VisibilityDetail {
            basis: "convention".to_owned(),
            kind: "public".to_owned(),
            spelling: name.to_owned(),
        });
    Declared {
        module: ModuleName::new(&module.name),
        package: PackageName::new(&module.package),
        name: name.to_owned(),
        qualified_name: format!("{holder}.{name}"),
        parent: parent.map(|(qualname, _)| qualname.to_owned()),
        lexical_parent_id: parent.map(|(_, id)| FactId::new(id)),
        unique: true,
        visibility: detail,
    }
}
