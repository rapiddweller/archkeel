// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The modules of the scan whose namespace may change under a route (AD-504): one visitor of the
//! uses of a module binding, with a closed list of harmless uses.
//!
//! A route through a module is proven only for the namespace that the module's own statements
//! build. A name that an import binds to a module of the scan (or to an imported name of unknown
//! kind) *escapes* in each use but one: a direct attribute load `name.attr`, and a call
//! `name.attr(...)`, when `attr` is no namespace (`__dict__`, `__all__`, `__setattr__`,
//! `__delattr__`) and no child module. Each other use is an escape, so the visitor fails closed:
//! an attribute store, `+=`, `del`, a call that passes the name (`setattr`, `getattr`, `vars`,
//! `patch(lib)`), an assignment of the bare name, a container, a conditional, a return, a
//! comprehension target, and an import of `__dict__` or `__all__` from the module. An escaped
//! module and each module below it withhold every route through them.
//!
//! An imported name is harmless when its origin is a `def`, a `class`, a literal or a display.
//! These values are not modules, so their use cannot directly change a module namespace.
//! A write through `sys.modules`, a computed import, `globals()` of another module, a writer
//! outside the scan roots and a C extension are not seen here: the first two are survey gaps
//! (AD-450); the rest is listed in `docs/known-limits.md`.
//!
//! AD-654: `from P import k`, where `k` is a proven key of the lazy table of `P`, reads what the
//! key gives: the attribute of the target module, or the target module. A use of the name is then
//! the use of `from target import name`, or of `import target`. A module that escapes loses the
//! proof of its keys, since another module can then write a key, and the walk runs again.

use std::collections::{HashMap, HashSet};

use archkeel_facts::vocab::RouteWithheld;

use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Stmt};

use super::bound::Bound;
use super::bound_kind::Kind;
use super::lazy_cover::{view, Sources};
use super::uses_scan::{class_patch, Scan};
pub(crate) use visit::Escapes;
use visit::{Binding, Uses, NAMESPACE};

#[path = "uses_visit.rs"]
mod visit;
use crate::module::Module;

/// The escaped modules once no escaped module keeps the proof of its keys (AD-654).
pub(super) fn settled(
    modules: &[Module],
    imports: &[Record<ImportFact>],
    sources: &mut Sources,
) -> HashSet<String> {
    settled_sites(modules, imports, sources)
        .into_keys()
        .collect()
}

/// `settled`, with the use that escapes each module.
pub(super) fn settled_sites(
    modules: &[Module],
    imports: &[Record<ImportFact>],
    sources: &mut Sources,
) -> Escapes {
    loop {
        let found = escaped_with(modules, imports, sources);
        let before = sources.len();
        sources.retain(|module, _| !found.contains_key(module));
        if sources.len() == before {
            return found;
        }
    }
}

/// The modules that a use of a module binding in `modules` can change.
fn escaped_with(modules: &[Module], imports: &[Record<ImportFact>], sources: &Sources) -> Escapes {
    let binders: Vec<_> = modules
        .iter()
        .map(|module| super::binders::Binders::of(&module.tree))
        .collect();
    let (_, sites) = super::hazards_split::split(modules, &binders, (None, false), false);
    let mut scan = Scan {
        modules: modules.iter().map(|module| module.name.as_str()).collect(),
        hazardous: sites
            .iter()
            .filter(|(_, site)| namespace_hazard(&site.detail))
            .map(|(index, _)| modules[*index].name.as_str())
            .collect(),
        typing_values: HashSet::new(),
        class_patch: false,
        copy_hook: false,
        bounds: modules
            .iter()
            .map(|module| (module.name.as_str(), Bound::of(&module.tree.body)))
            .collect(),
        imports: HashMap::new(),
    };
    let mut bindings: HashMap<&str, HashMap<&str, Vec<Binding>>> = HashMap::new();
    let mut found = Escapes::new();
    for record in imports {
        let data = record.data.data();
        let source = data.source_module.as_str();
        let Some(binding) = data.binding.as_deref().filter(|name| *name != "*") else {
            continue;
        };
        let (target, symbol) = view(sources, data.target_module.as_str(), data.symbol.as_deref());
        scan.imports
            .entry((source, binding))
            .or_default()
            .push((target, symbol));
        if symbol.is_some_and(|name| NAMESPACE.contains(&name)) {
            let rel = (modules.iter()).find(|module| module.name == source);
            let place = rel.map_or(source, |module| module.rel.as_str());
            let name = symbol.unwrap_or_default();
            let at = format!("{target} <- {place} (import of {name})");
            let use_of = (RouteWithheld::EscapedNamespace, at);
            for module in scan.below(target) {
                found.entry(module).or_insert_with(|| use_of.clone());
            }
        }
        let kind = match symbol {
            None if binding == target.split('.').next().unwrap_or(target) => {
                Binding::Module(binding.to_owned())
            }
            None => Binding::Module(target.to_owned()),
            Some(name) => Binding::Attribute(target.to_owned(), name.to_owned()),
        };
        bindings
            .entry(source)
            .or_default()
            .entry(binding)
            .or_default()
            .push(kind);
    }
    scan.class_patch = class_patch(&scan, modules);
    scan.copy_hook = scan.bounds.values().any(|bound| bound.copy_hook)
        || ["copy", "copyreg"]
            .iter()
            .any(|name| scan.modules.contains(name));
    scan.typing_values = typing_values(modules, imports, &scan);
    for module in modules {
        let mut walk = Uses {
            module,
            scan: &scan,
            names: bindings.get(module.name.as_str()),
            found: &mut found,
        };
        walk.visit_body(&module.tree.body);
    }
    found
}

fn namespace_hazard(detail: &str) -> bool {
    matches!(
        detail,
        "globals"
            | "locals"
            | "vars"
            | "exec"
            | "eval"
            | "compile"
            | "__globals__"
            | "__builtins__"
            | "sys.__dict__"
    ) || detail == "builtins"
        || detail.starts_with("builtins.")
        || detail == "sys.modules"
        || detail.starts_with("sys.modules.")
}

/// A typing factory that is referenced only as a factory cannot be patched by a scanned use.
type Factory = (String, String);

fn typing_factory(scan: &Scan<'_>, module: &str, name: &str, depth: usize) -> Option<Factory> {
    let bound = scan.bounds.get(module)?;
    if depth >= 8
        || bound.getattr
        || bound.attribute_write
        || scan.hazardous.contains(module)
        || scan.modules.contains(format!("{module}.{name}").as_str())
        || bound.kind(name) != Some(Kind::Import)
    {
        return None;
    }
    let [(target, Some(symbol))] = scan.imports.get(&(module, name))?.as_slice() else {
        return None;
    };
    if matches!(*target, "typing" | "typing_extensions") && factory_form(symbol).is_some() {
        return Some(((*target).to_owned(), (*symbol).to_owned()));
    }
    typing_factory(scan, target, symbol, depth + 1)
}

/// The factories whose subscript gives an alias object whatever its arguments are: `Annotated`
/// always, `Optional[X]` is `Union[X, None]` and `Literal[...]` keeps its values. `Union[X]` is
/// `X` and `Union[X, X]` is `X`, so `Union` needs literal arguments.
fn any_argument(name: &str) -> bool {
    matches!(name, "Annotated" | "Optional" | "Literal")
}

fn factory_form(name: &str) -> Option<bool> {
    match name {
        "Annotated" | "Union" | "Optional" | "Literal" => Some(true),
        "TypeVar" | "NewType" => Some(false),
        _ => None,
    }
}

fn typing_values(
    modules: &[Module],
    imports: &[Record<ImportFact>],
    scan: &Scan<'_>,
) -> HashSet<(String, String)> {
    let mut aliases = HashMap::new();
    let mut blocked = HashSet::new();
    let mut blocked_modules = HashSet::new();
    let class_write = scan.bounds.values().any(|bound| bound.attribute_write)
        || super::uses_typing_guard::withheld(modules);
    for record in imports {
        let data = record.data.data();
        let target = data.target_module.as_str();
        if !matches!(target, "typing" | "typing_extensions") {
            continue;
        }
        if data.symbol.as_deref().is_none_or(|symbol| symbol == "*") {
            blocked_modules.insert(target.to_owned());
            continue;
        }
        let (Some(symbol), Some(binding)) = (data.symbol.as_deref(), data.binding.as_deref())
        else {
            continue;
        };
        if factory_form(symbol).is_some()
            && scan
                .bounds
                .get(data.source_module.as_str())
                .and_then(|b| b.kind(binding))
                != Some(Kind::Import)
        {
            blocked.insert((target.to_owned(), symbol.to_owned()));
        }
    }
    for (module, name) in scan.imports.keys() {
        if let Some(factory) = typing_factory(scan, module, name, 0) {
            aliases.insert(((*module).to_owned(), (*name).to_owned()), factory);
        }
    }
    for module in modules {
        let names = aliases
            .iter()
            .filter_map(|((owner, name), factory)| {
                (owner == &module.name).then_some((name.as_str(), factory))
            })
            .collect();
        let mut watch = TypingWatch {
            names,
            blocked: &mut blocked,
        };
        watch.visit_body(&module.tree.body);
    }
    let mut values = HashSet::new();
    for module in modules {
        let Some(bound) = scan.bounds.get(module.name.as_str()) else {
            continue;
        };
        for (name, head, form, inert) in module
            .tree
            .body
            .iter()
            .flat_map(|stmt| typing_candidates(stmt, bound))
        {
            let key = (module.name.clone(), head.to_owned());
            let Some(factory) = aliases.get(&key) else {
                continue;
            };
            if factory_form(&factory.1) == Some(form)
                && (inert || any_argument(&factory.1))
                && !blocked.iter().any(|(_, name)| name == &factory.1)
                && blocked_modules.is_empty()
                && !class_write
            {
                values.insert((module.name.clone(), name.to_owned()));
            }
        }
    }
    values
}

/// A typing alias candidate: its name, the head name, the form (subscript or call) and whether
/// each argument is a literal or an unbound builtin type.
type Candidate<'a> = (&'a str, &'a str, bool, bool);

fn typing_candidates<'a>(stmt: &'a Stmt, bound: &Bound) -> Vec<Candidate<'a>> {
    let (targets, value): (Vec<&Expr>, &Expr) = match stmt {
        Stmt::Assign(node) => (node.targets.iter().collect(), &node.value),
        Stmt::AnnAssign(node) => match &node.value {
            Some(value) => (vec![&node.target], value),
            None => return Vec::new(),
        },
        _ => return Vec::new(),
    };
    let (head, form, inert) = match value {
        Expr::Subscript(node) => (&*node.value, true, bound.inert_typing_arg(&node.slice)),
        Expr::Call(node) => {
            let inert = node.arguments.keywords.is_empty()
                && node
                    .arguments
                    .args
                    .iter()
                    .all(|arg| bound.inert_typing_arg(arg));
            if !inert {
                return Vec::new();
            }
            (&*node.func, false, true)
        }
        _ => return Vec::new(),
    };
    let Expr::Name(head) = head else {
        return Vec::new();
    };
    targets
        .into_iter()
        .filter_map(|target| match target {
            Expr::Name(name) => Some((name.id.as_str(), head.id.as_str(), form, inert)),
            _ => None,
        })
        .collect()
}

struct TypingWatch<'a> {
    names: HashMap<&'a str, &'a Factory>,
    blocked: &'a mut HashSet<Factory>,
}

impl<'a> Visitor<'a> for TypingWatch<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Subscript(node) if self.factory(&node.value, true) => {
                self.visit_expr(&node.slice);
                return;
            }
            Expr::Call(node) if self.factory(&node.func, false) => {
                self.visit_arguments(&node.arguments);
                return;
            }
            Expr::Name(name) => {
                if let Some(factory) = self.names.get(name.id.as_str()) {
                    self.blocked.insert((*factory).clone());
                }
            }
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

impl TypingWatch<'_> {
    fn factory(&self, expr: &Expr, form: bool) -> bool {
        let Expr::Name(name) = expr else { return false };
        self.names
            .get(name.id.as_str())
            .is_some_and(|factory| factory_form(&factory.1) == Some(form))
    }
}

#[cfg(test)]
#[path = "uses_tests.rs"]
mod tests;
