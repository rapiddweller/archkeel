// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One use of a global: what publishes it, the record of the use and the facts that prove it
//! (`collect._script_dependency`, `_script_source_target`, `_script_alias_evidence`,
//! `_script_publication_evidence`).

use archkeel_facts::data::BindingData;
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{FactId, ModuleName};

use crate::script_deps::{Probe, Run};
use crate::script_project::{source_origin, stable_publication, Publisher};
use crate::script_records::{binding, global_id, import_record, Use};
use crate::script_types::{ScriptAlias, ScriptGlobal};

/// ` has no unique unconditional publication` (`GapTitle.UNPUBLISHED_GLOBAL`).
const UNPUBLISHED: &str = " has no unique unconditional publication";

/// The aliases of a use: the alias that the use calls, and the alias that it reads or initializes.
pub(crate) type Aliases<'x> = (Option<&'x ScriptAlias>, Option<&'x ScriptAlias>);

impl<'a, 'p> Run<'a, 'p> {
    /// Resolve only the new closed-source forms. The old object analysis stays separate.
    pub(crate) fn direct_dependency(&mut self, rel: &str, probe: &Probe, path: &[String]) -> bool {
        if !self.direct || probe.scope_ambiguous {
            return false;
        }
        let (name, property) = match probe.path.as_slice() {
            [name] => (name.as_str(), false),
            [host, name] if matches!(host.as_str(), "window" | "globalThis" | "self") => {
                (name.as_str(), true)
            }
            _ => return false,
        };
        if self.standard.contains(name) || path != [name] {
            return false;
        }
        let candidates: Vec<_> = self.project.files.iter().flat_map(|(source, file)| {
            file.script.script.direct.iter().flatten().filter_map(move |publication| {
                (publication.name == name).then_some((*source, publication))
            })
        }).collect();
        let [(source, publication)] = candidates.as_slice() else { return false; };
        if (property && !publication.property)
            || self.source_writes.sole(name) != Some((*source, &publication.span))
        {
            return false;
        }
        let publication = ScriptGlobal {
            name: name.to_owned(), span: publication.span.clone(), members: Vec::new(),
            stable: true, source_members: Vec::new(), source_origin: true, availability: Vec::new(),
        };
        let module = self.module(rel);
        let target = self.module(source);
        let proof = self.publication_evidence(source, &publication);
        let evidence = self.sink.cite(rel, &probe.span);
        self.sink.targets.push(Target::Local {
            import_id: FactId::new(global_id(&module, probe.kind, &probe.span)),
            module: ModuleName::new(&target), file: (*source).to_owned(),
            runtime_file: None, declaration_file: None,
        });
        self.sink.imports.push(import_record(&Use {
            module: &module, kind: probe.kind, span: &probe.span, path,
            target_module: &target, target_package: None, symbol: Some(name), known: true,
            evidence: vec![evidence], binding: None, facts: vec![proof],
        }));
        true
    }

    /// `_script_dependency`.
    pub(crate) fn dependency(
        &mut self,
        rel: &str,
        probe: &Probe,
        path: &[String],
        aliases: Aliases,
        publishers: &[Publisher<'a>],
    ) {
        let (alias_call, alias) = aliases;
        let module = self.module(rel);
        let evidence = self.sink.cite(rel, &probe.span);
        let first = path.first().map_or("", String::as_str);
        let stable = stable_publication(first, publishers, &self.writes);
        if self.external_dependency(rel, probe, path, alias_call, publishers) {
            return;
        }
        if self.namespace_dependency(rel, probe, path, alias_call, publishers) {
            return;
        }
        let declared = stable_publication(first, publishers, &self.source_writes);
        if alias.is_some_and(|alias| alias.factory && !alias.complete) {
            let reason = "Factory result uses are not statically bounded";
            self.sink
                .gap(reason, std::slice::from_ref(&evidence), &module);
        }
        let target_rel = publishers.first().map_or("", |(rel, _)| *rel);
        let publication = publishers.first().map(|(_, publication)| *publication);
        let target_module = if target_rel.is_empty() {
            first.to_owned()
        } else {
            self.module(target_rel)
        };
        let member = match path {
            [_, member] => Some(member.as_str()),
            _ => None,
        };
        let members = self.source_members(declared, publication, target_rel, member);
        let mut known = members.len() == 1 && path.len() == 2;
        let factory = alias_call.is_some_and(|alias| alias.factory);
        let entry = members.first().map(|(local, _)| local.as_str());
        let mut proof = None;
        if factory {
            proof = known
                .then(|| alias_call.zip(entry))
                .flatten()
                .and_then(|(alias, entry)| self.factory_proof(alias, target_rel, entry, probe));
            known = proof.is_some();
        }
        let evidence_ids = match alias {
            Some(alias) => {
                self.alias_evidence(rel, probe, alias, target_rel, publication, declared)
            }
            None => vec![evidence],
        };
        if let Some((sources, _)) = &proof {
            let ids: Vec<String> = sources
                .iter()
                .map(|(source_rel, span)| self.factory_source(source_rel, span))
                .collect();
            self.add_fact_ids(&module, probe, ids);
        }
        let resolved = known
            && stable
            && !factory
            && !probe.scope_ambiguous
            && publication.zip(entry).is_some_and(|(publication, entry)| {
                publication
                    .members
                    .iter()
                    .any(|(_, local, _)| local == entry)
            });
        if let (true, Some(entry)) = (resolved, entry) {
            let target = format!("{target_module}.{entry}");
            self.sink
                .facts
                .module(&module)
                .resolution
                .insert(probe.key(), vec![target]);
        }
        let target_module = self.source_target(rel, probe, path, publishers, known);
        let symbol = if known { entry } else { member };
        let record = Use {
            module: &module,
            kind: probe.kind,
            span: &probe.span,
            path,
            target_module: &target_module,
            target_package: None,
            symbol,
            known,
            evidence: evidence_ids,
            binding: alias_call.map(|alias| alias.name.as_str()),
            facts: self.sink.facts.fact_ids(&module, &probe.key()),
        };
        self.sink.imports.push(import_record(&record));
    }

    /// The members of the publication that the file declares as source: one `(local, span)` for
    /// each member of the name that the file does not rebind.
    fn source_members(
        &self,
        declared: bool,
        publication: Option<&'a ScriptGlobal>,
        target_rel: &str,
        member: Option<&str>,
    ) -> Vec<LocalMember<'a>> {
        let (true, Some(publication), Some(member)) = (declared, publication, member) else {
            return Vec::new();
        };
        let rebound = self.file(target_rel).map(|file| &file.rebound);
        publication
            .source_members
            .iter()
            .filter(|(published, local, _)| {
                published == member && !rebound.is_some_and(|names| names.contains(local))
            })
            .map(|(_, local, span)| (local.clone(), span))
            .collect()
    }

    /// Add facts to the proofs of a site, once each (`dict.fromkeys`).
    pub(crate) fn add_fact_ids(&mut self, module: &str, probe: &Probe, ids: Vec<String>) {
        let key = probe.key();
        let mut all = self.sink.facts.fact_ids(module, &key);
        for id in ids {
            if !all.contains(&id) {
                all.push(id);
            }
        }
        self.sink.facts.module(module).fact_ids.insert(key, all);
    }

    /// `_script_source_target`.
    fn source_target(
        &mut self,
        rel: &str,
        probe: &Probe,
        path: &[String],
        publishers: &[Publisher<'a>],
        known: bool,
    ) -> String {
        let module = self.module(rel);
        let identity = global_id(&module, probe.kind, &probe.span);
        let evidence = self.sink.cite(rel, &probe.span);
        let first = path.first().map_or("", String::as_str);
        let origin = source_origin(first, publishers, &self.source_writes);
        if let (true, Some((target_rel, publication))) = (origin, publishers.first()) {
            let target = self.module(target_rel);
            let proof = self.publication_evidence(target_rel, publication);
            self.add_fact_ids(&module, probe, vec![proof]);
            self.sink.targets.push(Target::Local {
                import_id: FactId::new(identity),
                module: ModuleName::new(target.clone()),
                file: (*target_rel).to_owned(),
                runtime_file: None,
                declaration_file: None,
            });
            if let (Some(member), false) = (path.get(1), known) {
                let reason =
                    format!("Script global member {first}.{member} is not statically published");
                self.sink.gap(&reason, &[evidence], &module);
            }
            return target;
        }
        let reason = format!("Script global {first}{UNPUBLISHED}");
        self.sink.targets.push(Target::Unresolved {
            import_id: FactId::new(identity),
            specifier: first.to_owned(),
            reason: reason.clone(),
        });
        self.sink.gap(&reason, &[evidence], &module);
        first.to_owned()
    }

    /// `_script_alias_evidence`: the evidence and the facts that an alias gives a use.
    pub(crate) fn alias_evidence(
        &mut self,
        rel: &str,
        probe: &Probe,
        alias: &ScriptAlias,
        target_rel: &str,
        publication: Option<&ScriptGlobal>,
        stable: bool,
    ) -> Vec<String> {
        let module = self.module(rel);
        let evidence = vec![
            self.sink.cite(rel, &probe.span),
            self.sink.cite(rel, &alias.span),
        ];
        let parts = [
            Part::Text(&module),
            Part::Number(alias.span.line),
            Part::Number(alias.span.column),
            Part::Text(&alias.name),
        ];
        let mut proofs = vec![stable_id("SCRIPTALIAS", &parts)];
        if let (true, Some(publication)) = (stable, publication) {
            proofs.push(self.publication_evidence(target_rel, publication));
        }
        let entry = self.sink.facts.module(&module);
        entry.evidence.insert(probe.key(), evidence.clone());
        entry.fact_ids.insert(probe.key(), proofs);
        evidence
    }

    /// `_script_publication_evidence`: the binding that says a file publishes a global.
    pub(crate) fn publication_evidence(&mut self, rel: &str, publication: &ScriptGlobal) -> String {
        let module = self.module(rel);
        let parts = [
            Part::Text(&module),
            Part::Number(publication.span.line),
            Part::Number(publication.span.column),
            Part::Text(&publication.name),
        ];
        let identity = stable_id("SCRIPTPUBLICATION", &parts);
        let mut evidence = vec![self.sink.cite(rel, &publication.span)];
        for (_, _, span) in &publication.source_members {
            let member = self.sink.cite(rel, span);
            if !evidence.contains(&member) {
                evidence.push(member);
            }
        }
        let data = BindingData {
            binding: Some(publication.name.clone()),
            script_global: Some(publication.name.clone()),
            ..BindingData::in_module(&module)
        };
        let title = format!("{module} publishes script global {}", publication.name);
        let record = binding(identity.clone(), title, &module, evidence, data);
        self.sink.facts.publish(record);
        identity
    }
}

/// A member that the file declares: its local name and where.
pub(crate) type LocalMember<'a> = (String, &'a crate::source::Span);
