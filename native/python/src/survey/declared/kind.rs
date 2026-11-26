// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The kind of a class that Python binds when the class statement runs (AD-518, rule 6).
//!
//! A class has a kind only when each base is proven: a builtin that no statement of the module
//! rebinds, a name of `typing` or `enum` or `abc.ABC` that its one plain import binds, a class of the same
//! module that has a record, or a class of another admitted module of the scan that its one plain
//! import (and the plain imports of the modules that re-export it) binds (#2129). A keyword
//! (`metaclass=`), a type parameter list or any other base can change what the statement gives,
//! so the class has no kind and no record.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Expr, Stmt, StmtClassDef};
use ruff_text_size::Ranged;

use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::nested::BaseDeclaration;
use archkeel_facts::vocab::{RelationshipKind, Status};

use super::reader::Unwritable;
use super::Writer;
use crate::module::Module;
use crate::survey::binders::Binders;
use crate::survey::bound::Bound;

/// The kind of a class with a record.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Kind {
    Plain,
    Protocol,
    Enum,
}

/// The builtin classes that give a class no other kind, no namespace and no metaclass (as the kind
/// reader accepts them; `escapes` reads the same set).
pub(super) const BUILTIN_BASES: [&str; 12] = [
    "object",
    "Exception",
    "BaseException",
    "ValueError",
    "TypeError",
    "RuntimeError",
    "KeyError",
    "dict",
    "list",
    "tuple",
    "str",
    "int",
];

/// The classes of `enum` whose subclass is an enum.
const ENUM_BASES: [&str; 5] = ["Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"];

/// A class of the module body with a record: its kind, and whether `A()` gives an instance of it
/// (no enum, no protocol, no `__new__` in it or in a local base).
#[derive(Clone, Copy, Debug)]
pub(super) struct Local {
    pub kind: Kind,
    pub constructible: bool,
}

/// One base of a class: its expression, the qualified name that it resolves to, and whether that
/// is a protocol class of the module (then a class that is no protocol realizes it).
pub(super) struct BaseSite<'a> {
    pub expr: &'a Expr,
    pub target: String,
    pub protocol: bool,
}

/// The proven kind and bases of a class.
pub(super) struct Class<'a> {
    pub kind: Kind,
    pub bases: Vec<BaseSite<'a>>,
    /// Each base lets `A()` give an instance of `A`.
    pub constructible: bool,
}

/// The classes with a proven kind of the admitted modules of the scan, and the plain imports that
/// bind a name to a name of another admitted module (#2129). A class that a module decorates, binds
/// twice or builds with a keyword is not in it, and neither is a module that a hazard or an escape
/// withholds. A module that is no admitted module of the scan has no entry: its name gives no kind.
pub(crate) struct Project {
    classes: HashMap<(String, String), Kind>,
    routes: HashMap<(String, String), (String, String)>,
}

/// The hops that one name follows through re-exports.
const HOPS: usize = 8;

/// The rounds of the fixpoint. A round only adds classes, so a stop before the end only loses some.
const ROUNDS: usize = 16;

impl Project {
    pub(super) fn empty() -> Project {
        Project {
            classes: HashMap::new(),
            routes: HashMap::new(),
        }
    }

    /// The module that defines `name` of `module`, and the kind of the class, when each hop is a
    /// plain import of an admitted module and the last one is a class with a proven kind.
    pub(super) fn class(&self, module: &str, name: &str) -> Option<(String, String, Kind)> {
        let (mut module, mut name) = (module.to_owned(), name.to_owned());
        for _ in 0..HOPS {
            let key = (module, name);
            if let Some(kind) = self.classes.get(&key) {
                return Some((key.0, key.1, *kind));
            }
            (module, name) = self.routes.get(&key)?.clone();
        }
        None
    }
}

/// The classes of other modules that a base can name (#2129): the plain imports of the admitted
/// modules, then the kind of each class of the module body to a fixpoint. Each class uses the
/// same reading as `of`, with the classes of this table for a base of another module.
pub(crate) fn project(
    modules: &[Module],
    binders: &[Binders],
    admitted: impl Fn(usize, &Module) -> bool,
) -> Project {
    let mut table = Project::empty();
    let names: HashSet<&str> = modules
        .iter()
        .enumerate()
        .filter(|(index, module)| admitted(*index, module))
        .map(|(_, module)| module.name.as_str())
        .filter(|name| !matches!(*name, "typing" | "typing_extensions" | "enum" | "abc"))
        .collect();
    let bounds: Vec<Option<Bound>> = modules
        .iter()
        .map(|module| {
            names
                .contains(module.name.as_str())
                .then(|| Bound::of(&module.tree.body))
        })
        .collect();
    for (module, bound) in modules
        .iter()
        .zip(&bounds)
        .filter_map(|(m, b)| Some((m, b.as_ref()?)))
    {
        table.routes.extend(plain_imports(module, bound, &names));
    }
    for _ in 0..ROUNDS {
        let mut grew = false;
        let each = modules.iter().zip(binders).zip(&bounds);
        for ((module, binders), bound) in each.filter_map(|(m, b)| Some((m, b.as_ref()?))) {
            grew |= add_classes(&mut table, (module, binders), bound);
        }
        if !grew {
            break;
        }
    }
    table
}

/// The `from m import a` statements of the module body that bind their name once, with `m` an
/// admitted module of the scan: `(module, binding)` is `(m, a)`.
fn plain_imports(
    module: &Module,
    bound: &Bound,
    names: &HashSet<&str>,
) -> Vec<((String, String), (String, String))> {
    let mut found = Vec::new();
    for statement in &module.tree.body {
        let Stmt::ImportFrom(node) = statement else {
            continue;
        };
        let from = node.module.as_ref().filter(|_| node.level == 0);
        let Some(from) = from.filter(|from| names.contains(from.as_str())) else {
            continue;
        };
        let start = statement.range().start();
        for alias in &node.names {
            let binding = alias.asname.as_ref().unwrap_or(&alias.name).as_str();
            if alias.name.as_str() != "*" && bound.sole(binding, start) {
                found.push((
                    (module.name.clone(), binding.to_owned()),
                    (from.to_string(), alias.name.to_string()),
                ));
            }
        }
    }
    found
}

/// The classes of one module body with a kind, given the table so far. True when one is new.
fn add_classes(table: &mut Project, (module, binders): (&Module, &Binders), bound: &Bound) -> bool {
    let body = &module.tree.body;
    let mut local: HashMap<String, Local> = HashMap::new();
    let mut grew = false;
    for statement in body {
        let Stmt::ClassDef(node) = statement else {
            continue;
        };
        let name = node.name.as_str();
        let plain = node.decorator_list.is_empty() && bound.sole(name, statement.range().start());
        let reading = Reading::top((&module.name, body), bound, binders, (&local, table));
        let found = of(node, &reading).filter(|_| plain);
        let Some((kind, constructible)) = found.map(|class| (class.kind, class.constructible))
        else {
            continue;
        };
        local.insert(
            name.to_owned(),
            Local {
                kind,
                constructible,
            },
        );
        grew |= table
            .classes
            .insert((module.name.clone(), name.to_owned()), kind)
            .is_none();
    }
    grew
}

/// What a class statement reads to know its bases.
pub(super) struct Reading<'a> {
    pub module: &'a str,
    pub body: &'a [Stmt],
    pub bound: &'a Bound,
    pub binders: &'a Binders,
    /// The class body that holds this class, for a nested class: it can bind a name of a base.
    pub enclosing: Option<&'a Bound>,
    /// The classes of the module body that have a record, by name (a top-level class only).
    pub local: &'a HashMap<String, Local>,
    /// The classes of the other modules of the scan.
    pub project: &'a Project,
}

impl<'a> Reading<'a> {
    /// The reading of a class of the module body.
    pub(super) fn top(
        (module, body): (&'a str, &'a [Stmt]),
        bound: &'a Bound,
        binders: &'a Binders,
        (local, project): (&'a HashMap<String, Local>, &'a Project),
    ) -> Self {
        Reading {
            module,
            body,
            bound,
            binders,
            enclosing: None,
            local,
            project,
        }
    }

    /// The reading of a class nested in the class body with the binders `held`.
    pub(super) fn within(self, held: &'a Bound) -> Self {
        Reading {
            enclosing: Some(held),
            ..self
        }
    }
}

/// What one base is.
enum Is {
    Plain,
    Protocol,
    Enum,
}

/// What `classify` finds for one base.
struct Found {
    is: Is,
    target: String,
    protocol: bool,
    constructible: bool,
}

/// The kind and the bases of `node`, or `None` when a base or a keyword leaves them open.
pub(super) fn of<'a>(node: &'a StmtClassDef, reading: &Reading<'_>) -> Option<Class<'a>> {
    if node.type_params.is_some() {
        return None;
    }
    let arguments = node.arguments.as_deref();
    if arguments.is_some_and(|arguments| !arguments.keywords.is_empty()) {
        return None;
    }
    let (mut protocol, mut enumeration, mut constructible) = (false, false, true);
    let mut bases = Vec::new();
    for base in arguments.map_or(&[][..], |arguments| &arguments.args) {
        let found = classify(base, reading)?;
        match found.is {
            Is::Plain => {}
            Is::Protocol => protocol = true,
            Is::Enum => enumeration = true,
        }
        constructible &= found.constructible;
        bases.push(BaseSite {
            expr: base,
            target: found.target,
            protocol: found.protocol,
        });
    }
    let kind = match (protocol, enumeration) {
        (true, true) => return None,
        (true, false) => Kind::Protocol,
        (false, true) => Kind::Enum,
        (false, false) => Kind::Plain,
    };
    Some(Class {
        kind,
        bases,
        constructible,
    })
}

fn classify(base: &Expr, reading: &Reading<'_>) -> Option<Found> {
    if let Expr::Name(name) = base {
        let name = name.id.as_str();
        if reading
            .enclosing
            .is_some_and(|held| held.names().contains(name))
        {
            return None;
        }
        if let Some(local) = reading
            .local
            .get(name)
            .filter(|_| reading.enclosing.is_none())
        {
            // A class that derives from a protocol class is no protocol itself.
            return Some(Found {
                is: match local.kind {
                    Kind::Enum => Is::Enum,
                    Kind::Plain | Kind::Protocol => Is::Plain,
                },
                target: format!("{}.{name}", reading.module),
                protocol: local.kind == Kind::Protocol,
                constructible: local.constructible,
            });
        }
        if BUILTIN_BASES.contains(&name) && reading.binders.builtin_visible(name) {
            return Some(Found {
                is: Is::Plain,
                target: format!("builtins.{name}"),
                protocol: false,
                constructible: true,
            });
        }
    }
    let (module, symbol) = imported(base, reading)?;
    if let Some((defined, class, kind)) = reading.project.class(&module, &symbol) {
        // The class of another module: no `__new__` is known for it, so no `A()` instance is claimed.
        return Some(Found {
            is: match kind {
                Kind::Enum => Is::Enum,
                Kind::Plain | Kind::Protocol => Is::Plain,
            },
            target: format!("{defined}.{class}"),
            protocol: kind == Kind::Protocol,
            constructible: false,
        });
    }
    let is = match (module.as_str(), symbol.as_str()) {
        ("typing" | "typing_extensions", "Protocol") => Is::Protocol,
        ("enum", symbol) if ENUM_BASES.contains(&symbol) => Is::Enum,
        // Its metaclass `ABCMeta` gives a class too, and no base here has another metaclass.
        ("abc", "ABC") => Is::Plain,
        _ => return None,
    };
    Some(Found {
        is,
        target: format!("{module}.{symbol}"),
        protocol: false,
        constructible: false,
    })
}

/// The module and the name that an expression reads through the one plain import of its root:
/// `from enum import Enum` (`Enum`) or `import enum` (`enum.Enum`).
pub(super) fn imported(base: &Expr, reading: &Reading<'_>) -> Option<(String, String)> {
    let (root, attribute) = match base {
        Expr::Name(name) => (name.id.as_str(), None),
        Expr::Attribute(node) => match &*node.value {
            Expr::Name(name) => (name.id.as_str(), Some(node.attr.as_str())),
            _ => return None,
        },
        _ => return None,
    };
    if reading
        .enclosing
        .is_some_and(|held| held.names().contains(root))
    {
        return None;
    }
    reading.body.iter().find_map(|statement| {
        let start = statement.range().start();
        match (statement, attribute) {
            (Stmt::ImportFrom(node), None) if node.level == 0 => {
                let module = node.module.as_ref()?;
                node.names
                    .iter()
                    .find(|alias| alias.asname.as_ref().unwrap_or(&alias.name).as_str() == root)
                    .filter(|_| reading.bound.sole(root, start))
                    .map(|alias| (module.to_string(), alias.name.to_string()))
            }
            (Stmt::Import(node), Some(attribute)) => node
                .names
                .iter()
                .find(|alias| match &alias.asname {
                    Some(name) => name.as_str() == root,
                    None => alias.name.as_str() == root,
                })
                .filter(|_| reading.bound.sole(root, start))
                .map(|alias| (alias.name.to_string(), attribute.to_owned())),
            _ => None,
        }
    })
}

impl Writer<'_, '_> {
    /// `_base_declaration`: one resolved declaration for each base of a class. The list is the
    /// class statement, so a base that it does not name is a base that the class lacks.
    pub(super) fn bases(
        &mut self,
        class: &str,
        class_kind: Kind,
        bases: &[BaseSite<'_>],
    ) -> Result<Vec<BaseDeclaration>, Unwritable> {
        let module = self.scan.module;
        let mut found = Vec::new();
        for base in bases {
            let expression = self.scan.text(Some(base.expr))?.unwrap_or_default();
            let crate::module::Location { line, column, .. } = module.location(base.expr);
            let relationship_kind = if base.protocol && class_kind != Kind::Protocol {
                RelationshipKind::Realizes
            } else {
                RelationshipKind::Inherits
            };
            let id = stable_id(
                "BASE",
                &[
                    Part::Text(class),
                    Part::Number(line),
                    Part::Number(column),
                    Part::Text(&expression),
                ],
            );
            found.push(BaseDeclaration {
                candidate_count: 1,
                candidates_truncated: None,
                evidence_ids: vec![EvidenceId::new(self.scan.evidence(base.expr))],
                expression,
                id: FactId::new(id),
                reason: Some("explicit base with a proven binding".to_owned()),
                relationship_kind,
                status: Status::Resolved,
                targets: vec![base.target.clone()],
            });
        }
        Ok(found)
    }
}

#[cfg(test)]
#[path = "kind_tests.rs"]
mod tests;
