// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proof that a factory function gives a member (`collect._script_factory_proof`,
//! `_script_factory_member`, `_script_factory_source`).

use archkeel_facts::identity::{stable_id, Part};

use crate::script_deps::{is_root, Probe, Run};
use crate::script_project::stable_publication;
use crate::script_records::{binding, proof_data};
use crate::script_types::ScriptAlias;
use crate::sites::SiteKind;
use crate::source::Span;

/// The places that prove a factory member, and whether the member is a function.
pub type Proof = (Vec<(String, Span)>, bool);

/// What following one forwarding alias gives: a proof, a stop of the whole search, or the next alias.
enum Step {
    Found(Proof),
    Stop,
    Next,
}

/// A factory member that is being followed: the file, the factory and the member.
type Seen = (String, String, String);

impl<'a, 'p> Run<'a, 'p> {
    /// `_script_factory_proof`.
    pub fn factory_proof(
        &self,
        alias: &ScriptAlias,
        rel: &str,
        entry: &str,
        probe: &Probe,
    ) -> Option<Proof> {
        let paths = &self.project.paths;
        let written = alias.escapes.iter().any(|prefix| paths.has_prefix(prefix));
        if written {
            return None;
        }
        let member = probe.path.last()?;
        let proof = self.factory_member(rel, entry, member, &[])?;
        (probe.kind != SiteKind::Call || proof.1).then_some(proof)
    }

    /// `_script_factory_member`.
    fn factory_member(&self, rel: &str, name: &str, member: &str, seen: &[Seen]) -> Option<Proof> {
        let identity: Seen = (rel.to_owned(), name.to_owned(), member.to_owned());
        if seen.contains(&identity) {
            return None;
        }
        let file = self.file(rel)?;
        let mut factories = file
            .script
            .script
            .factories
            .iter()
            .filter(|f| f.name == name);
        let factory = factories.next().filter(|_| factories.next().is_none())?;
        let mut members = factory.members.iter().filter(|item| item.name == member);
        let item = members.next().filter(|_| members.next().is_none())?;
        let mut proof = vec![
            (rel.to_owned(), factory.span.clone()),
            (rel.to_owned(), item.span.clone()),
        ];
        if let (Some(_), Some(target)) = (&item.target, &item.target_span) {
            proof.push((rel.to_owned(), target.clone()));
            return Some((proof, item.callable));
        }
        let forwarded = item.forwarded_span.as_ref()?;
        for alias in &file.script.script.aliases {
            if !alias.factory || !alias.reads.contains(forwarded) {
                continue;
            }
            let next = (identity.clone(), forwarded, alias);
            match self.forwarded(rel, proof.clone(), seen, next) {
                Step::Found(found) => return Some(found),
                Step::Stop => return None,
                Step::Next => {}
            }
        }
        None
    }

    /// The factory member that an alias forwards from another file, followed one step.
    fn forwarded(
        &self,
        rel: &str,
        proof: Vec<(String, Span)>,
        seen: &[Seen],
        next: (Seen, &Span, &ScriptAlias),
    ) -> Step {
        let (identity, forwarded, alias) = next;
        let skip = usize::from(alias.path.first().is_some_and(|first| is_root(first)));
        let path = alias.path.get(skip..).unwrap_or(&[]);
        let publishers = self.publishers(path.first());
        let ([_, published], Some(first)) = (path, path.first()) else {
            return Step::Stop;
        };
        let Some((source_rel, publication)) = publishers.first().copied() else {
            return Step::Stop;
        };
        if !stable_publication(first, publishers, &self.source_writes) {
            return Step::Stop;
        }
        let mut entries = publication
            .source_members
            .iter()
            .filter(|(p, _, _)| p == published);
        let Some(entry) = entries.next().filter(|_| entries.next().is_none()) else {
            return Step::Stop;
        };
        let Some(file) = self.file(rel) else {
            return Step::Stop;
        };
        let mut sites = file
            .sites
            .sites
            .iter()
            .filter(|site| site.span == *forwarded);
        let Some(site) = sites.next().filter(|_| sites.next().is_none()) else {
            return Step::Stop;
        };
        let names = site
            .path
            .map(|at| file.sites.paths.names(at, file.text.as_bytes()));
        let Some(last) = names.as_ref().and_then(|names| names.last()) else {
            return Step::Stop;
        };
        let mut chain = seen.to_vec();
        chain.push(identity);
        let Some(result) = self.factory_member(source_rel, &entry.1, last, &chain) else {
            return Step::Next;
        };
        let mut all = proof;
        all.push((rel.to_owned(), alias.span.clone()));
        all.push((source_rel.to_owned(), publication.span.clone()));
        all.extend(result.0);
        Step::Found((all, result.1))
    }

    /// `_script_factory_source`: the binding of a declaration that proves a factory member.
    pub fn factory_source(&mut self, rel: &str, span: &Span) -> String {
        let module = self.module(rel);
        let parts = [
            Part::Text(&module),
            Part::Number(span.line),
            Part::Number(span.column),
        ];
        let identity = stable_id("SCRIPT_FACTORY_SOURCE", &parts);
        let evidence = vec![self.sink.cite(rel, span)];
        let data = proof_data(&[
            ("module", &module),
            ("source_module", &module),
            ("source_scope", &module),
        ]);
        let title = "Factory source declaration".to_owned();
        self.sink
            .facts
            .publish(binding(identity.clone(), title, &module, evidence, data));
        identity
    }
}
