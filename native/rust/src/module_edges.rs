// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of the edges between the modules of one crate: one `import` or `reexport` record
//! for each distinct path or proven dot call, and one gap for each path that the scan
//! cannot resolve. The resolution is in `modules.rs`.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::data::ImportData;
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{FactId, ModuleName, PackageName};
use archkeel_facts::{ImportFact, Record};

use crate::builder::{import_record, Builder};
use crate::crates::Workspace;
use crate::definitions::MethodCall;
use crate::derive_imports::Local;
use crate::modules::{Edge, Index, Outcome};
use crate::names::{self, published, with_name};
use crate::resolve::{classify, Found, Named};
use crate::scan::{MacroCall, MacroDef, Reference, Site, Via};
use crate::tokens::NAME_FROM_CALL;
use crate::tree::Module;

/// The `macro_rules!` definitions of each crate, by name: the module, and the definition.
type Defs<'a> = BTreeMap<(usize, &'a str), Vec<(&'a Module, &'a MacroDef)>>;

/// The one portable exported definition that a call of another crate names (AD-614): by its path
/// `dep::m!`, or by its plain name through the one `use` leaf of the file that binds it. A
/// `#[macro_export]` macro is an item of the root of its crate.
fn exported<'a>(
    index: &Index<'_>,
    defs: &Defs<'a>,
    module: &Module,
    call: &MacroCall,
) -> Option<(&'a Module, &'a MacroDef)> {
    let frame = index.frame(&module.module)?;
    let path = match call.path.as_slice() {
        [_] => match frame.bound(&call.name) {
            [leaf] if module.scan.counts.get(&call.name) == Some(&1) => leaf.names.clone(),
            _ => return None,
        },
        path => path.to_vec(),
    };
    let [first, last] = path.as_slice() else {
        return None;
    };
    let krate = index.workspace().crates.get(module.crate_index)?;
    let Some(Found::Edge(Named::Package(package))) =
        classify(first, krate, &module.scan.shadows, false)
    else {
        return None;
    };
    let root = &index.workspace().primary_of(&package)?.module;
    let owner = index.frame(root)?.module;
    let found = defs.get(&(owner.crate_index, last.as_str()))?;
    match found.as_slice() {
        [(at, def)] if def.portable && at.module == *root && last == &call.name => {
            Some((*at, *def))
        }
        _ => None,
    }
}

/// The definitions of `name` that a call sees: each crate-wide one, and each one of a block that
/// holds the call after the definition.
fn visible<'a>(
    defs: &Defs<'a>,
    module: &Module,
    call: &MacroCall,
    name: &str,
) -> Vec<(&'a Module, &'a MacroDef)> {
    let all = defs.get(&(module.crate_index, name)).into_iter().flatten();
    all.filter(|(owner, def)| {
        def.local
            .is_none_or(|local| owner.module == module.module && local.sees(&call.site))
    })
    .copied()
    .collect()
}

impl Builder {
    pub(crate) fn module_edge(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        reference: &Reference,
    ) {
        let Some(frame) = index.frame(&module.module) else {
            return;
        };
        // A glob names a module, also by one name (`use child::*;`): an empty last name lets the
        // path end at that module, as `through_glob` does (AD-608).
        let mut glob = None;
        if matches!(reference.via, Via::Glob { .. }) {
            let mut names = reference.names.clone();
            names.push(String::new());
            glob = Some(Reference {
                names,
                ..reference.clone()
            });
        }
        match index.resolve(frame, glob.as_ref().unwrap_or(reference)) {
            // A body path from the crate name (`::app::b`) needs `extern crate self as app`.
            Outcome::None if reference.absolute && reference.in_macro.is_some() => {
                let reason = "A macro_rules! body holds a path from the name of its own crate";
                self.unreadable(module, reference, reason.to_owned());
            }
            // A path inside one crate that no module edge names: a local outcome.
            Outcome::None => self.ended += 1,
            Outcome::Unknown(reason) => self.unreadable(module, reference, reason),
            Outcome::Edge(edge) if glob.is_none() && index.module_or_item(&edge).is_some() => {
                let reason = index.module_or_item(&edge).unwrap_or_default();
                self.unreadable(module, reference, reason);
            }
            Outcome::Edge(edge) => match &reference.in_macro {
                None => self.module_import(index, module, reference, &edge),
                Some(_) => self.macro_use(index, module, reference, edge),
            },
        }
    }

    /// A path in a `macro_rules!` body that starts at `crate` names the same module wherever the
    /// macro expands, so each call of the macro gets the edge (`macro_calls`). The definition keeps
    /// its own edge as `macro_body`, which no cycle or layer rule reads. Any other path in a body
    /// is relative to the place of the call: the scan does not know it, and each call is UNKNOWN.
    fn macro_use(&mut self, index: &Index<'_>, module: &Module, reference: &Reference, edge: Edge) {
        if reference.names.first().map(String::as_str) == Some("crate") {
            self.module_import(index, module, reference, &edge);
            let key = (module.module.clone(), reference.macro_id);
            self.macro_uses
                .entry(key)
                .or_default()
                .push((edge, reference.clone()));
            return;
        }
        let reason =
            "A macro_rules! body holds a module path that is relative to the place of the call";
        self.unreadable(module, reference, reason.to_owned());
    }

    /// A path that the scan cannot read is UNKNOWN here. In a macro body, each call is UNKNOWN too.
    fn unreadable(&mut self, module: &Module, reference: &Reference, reason: String) {
        let evidence = self.cite(&module.rel, &reference.site);
        self.gap(&reason, Some(&evidence), &module.module);
        self.unread_macro(module, reference, reason);
        self.ended += 1;
    }

    /// The body of a macro holds a path that the scan cannot read: each call of it is UNKNOWN.
    fn unread_macro(&mut self, module: &Module, reference: &Reference, reason: String) {
        if reference.in_macro.is_some() {
            let key = (module.module.clone(), reference.macro_id);
            self.macro_unknowns.entry(key).or_default().push(reason);
        }
    }

    /// Each call of a macro of this crate is an edge to the module that defines it and to each
    /// module that its body names, also through the macros that its body calls. A name that two
    /// modules define, a call that the scan cannot place, and a body that it cannot read are
    /// UNKNOWN in the module of the call.
    pub(crate) fn macro_calls(
        &mut self,
        workspace: &Workspace,
        index: &Index<'_>,
        modules: &[Module],
    ) {
        let mut defs = Defs::new();
        for module in modules {
            for def in &module.scan.macro_defs {
                let key = (module.crate_index, def.name.as_str());
                defs.entry(key).or_default().push((module, def));
            }
        }
        for module in modules {
            let local = Local::of(module);
            for call in &module.scan.macro_calls {
                self.expand((workspace, index, modules), &defs, &local, call);
                *self.ended_calls.entry(module.rel.clone()).or_default() += 1;
            }
        }
    }

    fn expand(
        &mut self,
        (workspace, index, modules): (&Workspace, &Index<'_>, &[Module]),
        defs: &Defs<'_>,
        local: &Local<'_>,
        call: &MacroCall,
    ) {
        let (module, name) = (local.module, call.name.as_str());
        if call.path.len() == 1
            && index.frame(&module.module).is_some_and(|frame| {
                frame
                    .bound(name)
                    .iter()
                    .any(|leaf| leaf.names.last().is_some_and(|original| original != name))
            })
        {
            let evidence = self.cite(&module.rel, &call.site);
            self.gap(
                "The scan cannot resolve a renamed macro binding",
                Some(&evidence),
                &module.module,
            );
            return;
        }
        let found = visible(defs, module, call, name);
        if found.is_empty() {
            // AD-614: a portable macro of another crate names the same edges in this module.
            if let Some(owner_def) = exported(index, defs, module, call) {
                self.expand_uses(index, module, call, owner_def);
            } else {
                self.unread_call((workspace, index, modules), local, call);
            }
            return;
        }
        let reason = match (found.len(), call.placed) {
            (1, true) => None,
            (1, false) => Some(format!(
                "The macro {name}! is called where the scan cannot place it"
            )),
            _ => Some(format!(
                "The macro {name}! is defined more than once in the crate"
            )),
        };
        if let Some(reason) = reason {
            let evidence = self.cite(&module.rel, &call.site);
            self.gap(&reason, Some(&evidence), &module.module);
            self.impl_home(module, call);
            return;
        }
        let mut seen = BTreeSet::new();
        let mut queue = vec![name.to_owned()];
        while let Some(next) = queue.pop() {
            if !seen.insert(next.clone()) {
                continue;
            }
            let found = visible(defs, module, call, &next);
            if let [(owner, def)] = found[..] {
                queue.extend(def.calls.iter().cloned());
                self.macro_items(module, call, def, next == name);
                self.expand_methods(module, call, def);
                self.call_edge(index, module, owner, (&next, &call.site));
                self.unknown_expansion(module, call, (owner, def));
                self.expand_uses(index, module, call, (owner, def));
            } else if found.is_empty() && next != name {
                // A plain name in a body names a macro at the place of the call (#1371).
                let inner = crate::macro_identity::inner(call, &next);
                match exported(index, defs, module, &inner) {
                    Some(owner_def) => self.expand_uses(index, module, &inner, owner_def),
                    None => self.unread_call((workspace, index, modules), local, &inner),
                }
            }
        }
    }

    /// The methods that the body of a macro calls are calls of the module of the call (#953).
    fn expand_methods(&mut self, module: &Module, call: &MacroCall, def: &MacroDef) {
        // A `fn $name` takes its name from the call tokens (#1196). A macro that defines the type
        // and its impl together adds such a name only to its own type, which no written type of
        // a receiver proof is: only a foreign impl holds back a proof by the name (AD-383).
        // A struct, enum or trait at module level that every configuration has (#1374).
        let declared =
            |name: &str| (module.scan.exact_items).contains(&(Vec::new(), name.to_owned()));
        let foreign = def.item_level.foreign_impl(&def.name, declared) || call.writes_impl;
        if def.item_level.trait_home(declared) || call.writes_impl {
            self.impl_home(module, call);
        }
        let from_call = def.members.contains(NAME_FROM_CALL) && foreign;
        let named = def.members.iter().filter(|name| *name != NAME_FROM_CALL);
        let names = named.chain(call.idents.iter().filter(|_| from_call));
        for name in names {
            let modules = self.macro_members.entry(name.clone()).or_default();
            modules.insert(module.module.clone());
            if foreign {
                let modules = self.macro_foreign_members.entry(name.clone()).or_default();
                modules.insert(module.module.clone());
            }
        }
        let calls = def.methods.iter().map(|name| MethodCall {
            bound_name: false,
            name: name.clone(),
            site: call.site.clone(),
            scope: Vec::new(),
            path: false,
            arity: None,
            on_self: None,
            owner: None,
            chain: None,
        });
        let found = self.macro_methods.entry(module.module.clone()).or_default();
        found.extend(calls);
    }

    /// The edges that the body of a macro names from the crate root, for the module of the call.
    fn expand_uses(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        call: &MacroCall,
        (owner, def): (&Module, &MacroDef),
    ) {
        let key = (owner.module.clone(), def.id);
        let uses = self.macro_uses.get(&key).cloned();
        for (edge, reference) in uses.into_iter().flatten() {
            let at = Reference {
                site: call.site.clone(),
                in_macro: None,
                ..reference
            };
            self.module_import(index, module, &at, &edge);
        }
    }

    /// The call is UNKNOWN for each reason why the scan cannot read the body of the macro.
    fn unknown_expansion(
        &mut self,
        module: &Module,
        call: &MacroCall,
        (owner, def): (&Module, &MacroDef),
    ) {
        let key = (owner.module.clone(), def.id);
        let found = self.macro_unknowns.get(&key).into_iter().flatten();
        let reasons: Vec<String> = def.unknowns.iter().chain(found).cloned().collect();
        for reason in reasons {
            let evidence = self.cite(&module.rel, &call.site);
            let reason = format!(
                "The macro {}! expands where the scan cannot read: {reason}",
                def.name
            );
            self.gap(&reason, Some(&evidence), &module.module);
        }
    }

    /// The call of `name!` depends on the module that defines the macro.
    fn call_edge(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        owner: &Module,
        (name, site): (&str, &Site),
    ) {
        let reference = Reference {
            root: name.to_owned(),
            path: format!("{name}!"),
            site: site.clone(),
            names: vec![name.to_owned()],
            ..Reference::default()
        };
        let edge = Edge {
            module: owner.module.clone(),
            lexical: owner.module.clone(),
            symbol: Some(name.to_owned()),
            level: 1,
            member_of: None,
        };
        self.module_import(index, module, &reference, &edge);
    }

    pub(crate) fn module_import(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        reference: &Reference,
        edge: &Edge,
    ) {
        let Some(target_rel) = index.rel(&edge.module) else {
            return;
        };
        if edge.module == module.module {
            self.ended += 1;
            return;
        }
        // The path of a macro body in its own definition is a template, not code (`macro_body`).
        let (template, form) = match reference.in_macro {
            Some(_) => ("template:", "macro_body"),
            None => ("", "module"),
        };
        let receiver = match reference.via {
            Via::Method => edge.member_of.clone(),
            _ => None,
        };
        let key = (
            module.module.clone(),
            format!("{template}module:{}", edge.module),
            reference.path.clone(),
            receiver,
        );
        if !self.seen.insert(key) {
            self.ended += 1;
            return;
        }
        let site = &reference.site;
        let identity = stable_id(
            "IMP",
            &[
                Part::Text(&module.module),
                Part::Number(site.line),
                Part::Number(site.column),
                Part::Text(form),
                Part::Text(&edge.module),
                Part::Text(&reference.path),
            ],
        );
        let evidence = self.cite(&module.rel, site);
        self.targets.push(Target::Local {
            import_id: FactId::new(identity.as_str()),
            module: ModuleName::new(edge.module.as_str()),
            file: target_rel.to_owned(),
            runtime_file: Some(target_rel.to_owned()),
            declaration_file: None,
        });
        let named = names::named(index, &mut self.publications, edge, &reference.via);
        let external = named.external_package();
        if let Some(package) = external.filter(|_| reference.in_macro.is_none()) {
            self.external_origin(&module.module, &evidence, package);
        }
        let mut record = with_name(
            module_record(index, module, reference, edge, &identity, evidence),
            named,
        );
        record.data.data_mut().published_as = published(index, &module.module, reference);
        // AD-622: a binary target reaches the library of its own package through the index
        // (`resolve::classify`): the path crosses crates when the target is another target.
        let target_of = |name: &str| index.frame(name).map(|frame| frame.module.target.as_str());
        let other = target_of(&edge.module).is_some_and(|at| at != module.target);
        record.data.data_mut().other_crate = other.then_some(true);
        self.imports.push(record);
        self.ended += 1;
    }
}

fn module_record(
    index: &Index<'_>,
    module: &Module,
    reference: &Reference,
    edge: &Edge,
    identity: &str,
    evidence: String,
) -> Record<ImportFact> {
    let (binding, reexport, block, glob) = match &reference.via {
        Via::Use {
            binding,
            reexport,
            block,
        } => (binding.clone(), *reexport, *block, false),
        Via::Glob { reexport, block } => (None, *reexport, *block, true),
        Via::Path | Via::Method | Via::Helper => (None, false, true, false),
    };
    let data = ImportData {
        source_module: ModuleName::new(&module.module),
        source_package: PackageName::new(module.package()),
        target_module: ModuleName::new(&edge.module),
        target_package: PackageName::new(
            index
                .frame(&edge.module)
                .map_or("", |frame| frame.module.package()),
        ),
        symbol: if glob { None } else { edge.symbol.clone() },
        inferred_receiver: matches!(reference.via, Via::Method),
        binding,
        specifier: Some(reference.path.clone()),
        relative_level: edge.level,
        reexport,
        module_level_import: !block,
        ..ImportData::statement()
    };
    let subjects = vec![module.module.clone(), edge.module.clone()];
    let at = (module.module.as_str(), reference.path.as_str());
    let fact = match (&reference.in_macro, reexport) {
        (Some(_), _) => ImportFact::MacroBody(data),
        (None, true) => ImportFact::Reexport(data),
        (None, false) => ImportFact::Import(data),
    };
    import_record((identity, evidence), at, subjects, fact)
}

#[cfg(test)]
#[path = "module_edges_tests.rs"]
mod tests;
