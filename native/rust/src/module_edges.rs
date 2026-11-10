// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of the edges between the modules of one crate: one `import` or `reexport` record
//! for each distinct path of a module that names another module of its crate, and one gap for
//! each path that the scan cannot resolve. The resolution is in `modules.rs`.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::data::ImportData;
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{package_of, stable_id, Part};
use archkeel_facts::ids::{FactId, ModuleName, PackageName};
use archkeel_facts::{ImportFact, Record};

use crate::builder::{import_record, Builder};
use crate::crates::Root;
use crate::modules::{Edge, Index, Outcome};
use crate::scan::{MacroCall, MacroDef, Reference, Site, Via};
use crate::tree::Module;

/// The `macro_rules!` definitions of each crate, by name: the module, and the definition.
type Defs<'a> = BTreeMap<(usize, &'a str), Vec<(&'a Module, &'a MacroDef)>>;

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
        match index.resolve(frame, reference) {
            // A body path from the crate name (`::app::b`) needs `extern crate self as app`.
            Outcome::None if reference.absolute && reference.in_macro.is_some() => {
                let reason = "A macro_rules! body holds a path from the name of its own crate";
                self.unreadable(module, reference, reason.to_owned());
            }
            Outcome::None => {}
            Outcome::Unknown(reason) => self.unreadable(module, reference, reason),
            Outcome::Edge(edge) => match &reference.in_macro {
                None => self.module_import(index, module, reference, &edge),
                Some(name) => self.macro_use(index, module, reference, edge, name),
            },
        }
    }

    /// A path in a `macro_rules!` body that starts at `crate` names the same module wherever the
    /// macro expands, so each call of the macro gets the edge (`macro_calls`). The definition keeps
    /// its own edge as `macro_body`, which no cycle or layer rule reads. Any other path in a body
    /// is relative to the place of the call: the scan does not know it, and each call is UNKNOWN.
    fn macro_use(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        reference: &Reference,
        edge: Edge,
        name: &str,
    ) {
        if reference.names.first().map(String::as_str) == Some("crate") {
            self.module_import(index, module, reference, &edge);
            let key = (module.crate_index, name.to_owned());
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
    }

    /// The body of a macro holds a path that the scan cannot read: each call of it is UNKNOWN.
    fn unread_macro(&mut self, module: &Module, reference: &Reference, reason: String) {
        if let Some(name) = &reference.in_macro {
            let key = (module.crate_index, name.clone());
            self.macro_unknowns.entry(key).or_default().push(reason);
        }
    }

    /// Each call of a macro of this crate is an edge to the module that defines it and to each
    /// module that its body names, also through the macros that its body calls. A name that two
    /// modules define, a call that the scan cannot place, and a body that it cannot read are
    /// UNKNOWN in the module of the call.
    pub(crate) fn macro_calls(&mut self, index: &Index<'_>, modules: &[Module]) {
        let mut defs = Defs::new();
        for module in modules {
            for def in &module.scan.macro_defs {
                let key = (module.crate_index, def.name.as_str());
                defs.entry(key).or_default().push((module, def));
            }
        }
        for module in modules {
            for call in &module.scan.macro_calls {
                self.expand(index, &defs, module, call);
            }
        }
    }

    fn expand(&mut self, index: &Index<'_>, defs: &Defs<'_>, module: &Module, call: &MacroCall) {
        let name = call.name.as_str();
        let Some(found) = defs.get(&(module.crate_index, name)) else {
            return;
        };
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
            return;
        }
        let mut seen = BTreeSet::new();
        let mut queue = vec![name.to_owned()];
        while let Some(next) = queue.pop() {
            if !seen.insert(next.clone()) {
                continue;
            }
            let key = (module.crate_index, next);
            if let Some([(owner, def)]) = defs.get(&(key.0, key.1.as_str())).map(Vec::as_slice) {
                queue.extend(def.calls.iter().cloned());
                self.call_edge(index, module, owner, (&key.1, &call.site));
                self.unknown_expansion(module, call, def);
            }
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
    }

    /// The call is UNKNOWN for each reason why the scan cannot read the body of the macro.
    fn unknown_expansion(&mut self, module: &Module, call: &MacroCall, def: &MacroDef) {
        let key = (module.crate_index, def.name.clone());
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
        };
        self.module_import(index, module, &reference, &edge);
    }

    fn module_import(
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
            return;
        }
        // The path of a macro body in its own definition is a template, not code (`macro_body`).
        let (template, form) = match reference.in_macro {
            Some(_) => ("template:", "macro_body"),
            None => ("", "module"),
        };
        let key = (
            module.module.clone(),
            format!("{template}module:{}", edge.module),
            reference.path.clone(),
        );
        if !self.seen.insert(key) {
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
        self.imports
            .push(module_record(module, reference, edge, &identity, evidence));
    }
}

fn module_record(
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
        Via::Path => (None, false, true, false),
    };
    let data = ImportData {
        source_module: ModuleName::new(&module.module),
        source_package: PackageName::new(package_of(&module.module)),
        target_module: ModuleName::new(&edge.module),
        target_package: PackageName::new(package_of(&edge.module)),
        symbol: if glob { None } else { edge.symbol.clone() },
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

/// The target of a path into another crate of the workspace: the deepest module that the path
/// names below the root of that crate. Without an index (a declared dependency) it is the root.
pub(crate) fn local_target(
    index: Option<&Index<'_>>,
    root: &Root,
    reference: &Reference,
    import_id: FactId,
) -> (Target, String) {
    let rest = reference.names.get(1..).unwrap_or(&[]);
    let deepest = index.and_then(|index| {
        let module = index.deepest(&root.module, rest);
        index.rel(&module).map(|rel| (module, rel.to_owned()))
    });
    let (module, file) = deepest.unwrap_or_else(|| (root.module.clone(), root.rel.clone()));
    let target = Target::Local {
        import_id,
        module: ModuleName::new(module.as_str()),
        file: file.clone(),
        runtime_file: Some(file),
        declaration_file: None,
    };
    (target, module)
}

#[cfg(test)]
#[path = "module_edges_tests.rs"]
mod tests;
