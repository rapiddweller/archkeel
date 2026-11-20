// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Direct lexical calls to module functions within one crate target.

use std::collections::BTreeMap;

use archkeel_facts::data::CallData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName};
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::{Area, EvidenceClass, Status};
use archkeel_facts::{CallFact, Record, SymbolFact};

use crate::builder::Builder;
use crate::definitions::{Call, Definition, Form, Owner};
use crate::scan::Via;
use crate::symbols::{id, item_name};
use crate::tree::Module;

struct Function<'a> {
    module: &'a Module,
    definition: &'a Definition,
    name: String,
}

type Functions<'a> = BTreeMap<(usize, &'a str, String), Function<'a>>;
type Uses<'a> = BTreeMap<(&'a [String], &'a str), Option<&'a [String]>>;

impl Builder {
    pub(crate) fn calls(&mut self, modules: &[Module]) {
        let unique = self
            .symbols
            .iter()
            .filter_map(|symbol| match &symbol.data {
                SymbolFact::Function(data) if data.source_binding_unique == Some(true) => {
                    Some(FactId::as_str(&symbol.id))
                }
                _ => None,
            })
            .collect::<std::collections::BTreeSet<_>>();
        let functions: Functions<'_> = modules
            .iter()
            .filter(|module| !module.gated)
            .flat_map(|module| functions_in(module, &unique))
            .collect();
        for module in modules {
            let uses = direct_uses(module);
            for call in &module.scan.calls.sites {
                self.call(module, call, &functions, &uses);
            }
        }
        self.calls.sort_by(|a, b| a.id.cmp(&b.id));
    }

    fn call(&mut self, module: &Module, call: &Call, functions: &Functions<'_>, uses: &Uses<'_>) {
        let scope = qualified(&module.module, &call.scope);
        let owner = call.owner.as_ref().map(|name| format!("{scope}.{name}"));
        let source = owner
            .as_ref()
            .and_then(|name| functions.get(&key(module, name.clone())));
        let target = target(module, call, (&scope, source), (functions, uses));
        let (status, targets, reason) = match target {
            Ok(found) => (Status::Resolved, vec![found.name.clone()], None),
            Err(reason) => (Status::Unresolved, Vec::new(), Some(reason.to_owned())),
        };
        let mut data = CallData::new(
            call.expression.clone(),
            (ModuleName::new(&module.module), owner.unwrap_or(scope)),
            status,
            targets,
        );
        data.reason = reason;
        data.source_file = Some(module.rel.clone());
        if let Some(source) = source {
            data.source_definition_id = Nullable::Value(FactId::new(id(
                &module.module,
                &source.name,
                source.definition,
            )));
        }
        if let Ok(target) = target {
            let evidence = self.cite(&target.module.rel, &target.definition.site);
            data.target_evidence_ids = Some(vec![EvidenceId::new(evidence)]);
        }
        let site = &call.site;
        let identity = stable_id(
            "RSCALL",
            &[
                Part::Text(&module.module),
                Part::Text(&module.rel),
                Part::Number(site.line),
                Part::Number(site.column),
                Part::Number(site.end_line),
                Part::Number(call.end_column),
            ],
        );
        let evidence = self.cite(&module.rel, site);
        self.calls.push(Record {
            id: FactId::new(identity),
            evidence_class: EvidenceClass::Fact,
            area: Area::Source,
            title: format!("Call to {}", call.expression),
            subjects: vec![module.module.clone()],
            evidence_ids: vec![EvidenceId::new(evidence)],
            fact_ids: Vec::new(),
            data: CallFact::Calls(data),
        });
    }
}

fn functions_in<'m, 'a>(
    module: &'m Module,
    unique: &'a std::collections::BTreeSet<&str>,
) -> impl Iterator<Item = ((usize, &'m str, String), Function<'m>)> + 'a
where
    'm: 'a,
{
    module
        .scan
        .definitions
        .iter()
        .filter_map(move |definition| {
            if definition.form != Form::Function
                || definition.owner != Owner::Module
                || !module
                    .scan
                    .calls
                    .functions
                    .contains(&(definition.scope.clone(), definition.name.clone()))
            {
                return None;
            }
            let name = item_name(&module.module, definition);
            unique
                .contains(id(&module.module, &name, definition).as_str())
                .then(|| {
                    (
                        key(module, name.clone()),
                        Function {
                            module,
                            definition,
                            name,
                        },
                    )
                })
        })
}

fn key(module: &Module, name: String) -> (usize, &str, String) {
    (module.crate_index, &module.target, name)
}

fn qualified(base: &str, names: &[String]) -> String {
    names
        .iter()
        .fold(base.to_owned(), |base, name| format!("{base}.{name}"))
}

fn rooted(module: &Module, scope: &str, path: &[String]) -> Option<String> {
    let (first, rest) = path.split_first()?;
    if rest.is_empty() {
        return None;
    }
    match first.as_str() {
        "crate" => Some(qualified(&module.target, rest)),
        "self" => Some(qualified(scope, rest)),
        "super" => {
            let mut rest = path;
            let mut parent = scope;
            while let [name, remaining @ ..] = rest {
                if name != "super" {
                    return Some(qualified(parent, rest));
                }
                if parent == module.target {
                    return None;
                }
                parent = parent.rsplit_once('.')?.0;
                rest = remaining;
            }
            None
        }
        _ => None,
    }
}

fn target<'a, 'm>(
    module: &'m Module,
    call: &Call,
    (scope, source): (&str, Option<&Function<'_>>),
    (functions, uses): (&'a Functions<'m>, &Uses<'_>),
) -> Result<&'a Function<'m>, &'static str> {
    if let Some(reason) = call.reason {
        return Err(reason);
    }
    if source.is_none() {
        return Err("The enclosing function has no unique unconditional definition");
    }
    let missing = "The path does not name one unconditional function in this crate target";
    if let [name] = &call.path[..] {
        if let Some(function) = functions.get(&key(module, format!("{scope}.{name}"))) {
            return Ok(function);
        }
        let alias = uses
            .get(&(Vec::as_slice(&call.scope), name.as_str()))
            .and_then(|path| rooted(module, scope, (*path)?))
            .ok_or(missing)?;
        return functions.get(&key(module, alias)).ok_or(missing);
    }
    let path = rooted(module, scope, &call.path).ok_or(missing)?;
    functions.get(&key(module, path)).ok_or(missing)
}

fn direct_uses(module: &Module) -> Uses<'_> {
    let scan = &module.scan;
    let mut uses = Uses::new();
    for reference in &scan.references {
        let Via::Use {
            binding: Some(binding),
            block: false,
            ..
        } = &reference.via
        else {
            continue;
        };
        if reference.absolute
            || reference.in_macro.is_some()
            || scan.conditional_bindings.contains(binding)
        {
            continue;
        }
        uses.entry((Vec::as_slice(&reference.scope), String::as_str(binding)))
            .and_modify(|path| *path = None)
            .or_insert(Some(Vec::as_slice(&reference.names)));
    }
    uses
}

#[cfg(test)]
#[path = "calls_tests.rs"]
mod tests;
