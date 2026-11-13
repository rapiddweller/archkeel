// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Binding, call and reference records. Bindings precede all uses in a file.

use super::types::{RecordKind, ResolvedSite, ResultBinding, SiteData, Source};
use super::{decl, expression, fact, id, Builder, Stop};
use crate::syntax::{Site, SiteKind, SiteUse, Visibility};
use archkeel_facts::identity::Part;
use archkeel_facts::ids::EvidenceId;
use archkeel_facts::vocab::Status;
use std::collections::BTreeSet;

pub(super) struct Bound {
    pub(super) site: Site,
    pub(super) id: String,
    pub(super) name: String,
    pub(super) qualified: String,
    pub(super) annotation: Option<String>,
    pub(super) evidence: EvidenceId,
}

impl Builder<'_> {
    pub(super) fn sites(&mut self, source: &Source) -> Result<(), Stop> {
        let rel = &source.file.rel;
        let index = *self.site_indices.get(rel).ok_or(Stop::Input)?;
        let answer = self.input.resolver.sites.get(index).ok_or(Stop::Input)?;
        self.validate_sites(&source.file.syntax.sites, &answer.sites)?;
        self.file_sites(rel, &answer.sites)?;
        Ok(())
    }

    fn validate_sites(&self, sites: &[Site], answers: &[ResolvedSite]) -> Result<(), Stop> {
        let mut answers = answers.iter();
        for site in sites {
            self.decl.work.copies(site)?;
            let mut expected = site.clone();
            if site.kind == SiteKind::Reference && site.r#use == SiteUse::ReadWrite {
                expected.r#use = SiteUse::Read;
                answers
                    .next()
                    .filter(|answer| answer.site == expected)
                    .ok_or(Stop::Input)?;
                expected.r#use = SiteUse::Write;
            }
            answers
                .next()
                .filter(|answer| answer.site == expected)
                .ok_or(Stop::Input)?;
        }
        if answers.next().is_some() {
            return Err(Stop::Input);
        }
        Ok(())
    }

    fn file_sites(&mut self, rel: &str, sites: &[ResolvedSite]) -> Result<(), Stop> {
        let bindings = self.binding_sites(rel, sites)?;
        for resolved in sites {
            self.decl.work.copies(resolved)?;
            match resolved.site.kind {
                SiteKind::Binding
                | SiteKind::Assignment
                | SiteKind::Extends
                | SiteKind::Implements
                | SiteKind::With
                | SiteKind::FieldFormal
                | SiteKind::SuperFormal => continue,
                SiteKind::Reference | SiteKind::Call | SiteKind::Creation | SiteKind::Type => {}
            }
            self.site_record(rel, resolved, &bindings)?;
        }
        Ok(())
    }

    fn binding_sites(&mut self, rel: &str, sites: &[ResolvedSite]) -> Result<Vec<Bound>, Stop> {
        let mut calls = BTreeSet::new();
        for resolved in sites {
            self.decl.work.text(&resolved.site.expression)?;
            if matches!(resolved.site.kind, SiteKind::Call | SiteKind::Creation) {
                calls.insert(resolved.site.expression.as_str());
            }
        }
        let mut result = Vec::new();
        for resolved in sites {
            self.decl.work.copies(&resolved.site)?;
            let site = &resolved.site;
            let Some(name) = site.assigned_name.as_ref().filter(|name| !name.is_empty()) else {
                continue;
            };
            if site.kind != SiteKind::Binding {
                continue;
            }
            let (scope, scope_id) = self.scope(rel, site)?;
            let lexical = match &site.scope_span {
                Some(span) if site.closure_scope => format!("{scope}._closure_{}", span.start_byte),
                Some(_) | None => scope.clone(),
            };
            let mut qualified = format!("{lexical}.{name}");
            if self.symbol_indices.contains_key(&qualified) {
                qualified = format!("{scope}.$local{}.{name}", site.span.start_byte);
            }
            let identity = id(
                "DARTBIND",
                rel,
                site.span.start_byte,
                &[
                    Part::Text(scope_id.as_deref().unwrap_or("")),
                    Part::Text(name),
                ],
            );
            let cited = self.cite(rel, &site.span)?;
            let raw_initializer = &site.initializer;
            let initializer = site
                .initializer_source
                .as_ref()
                .filter(|text| !text.is_empty())
                .or(raw_initializer.as_ref())
                .filter(|value| !value.contains("=>"))
                .cloned();
            let index = *self.by_path.get(rel).ok_or(Stop::Input)?;
            let file = self.files.get(index).ok_or(Stop::Input)?;
            let mut data = self.decl.meta(
                file,
                name,
                &qualified,
                Some((&scope, scope_id.as_deref().unwrap_or(""))),
                decl::Category::DynamicBinding,
                Visibility::of(name),
            )?;
            data.lexical_parent_id = scope_id.as_ref().map(archkeel_facts::ids::FactId::new);
            data.detail = decl::Detail::Binding {
                annotation: site.assignment_annotation.clone(),
                initializer: if raw_initializer
                    .as_deref()
                    .is_some_and(|value| calls.contains(value))
                {
                    None
                } else {
                    initializer.clone()
                },
                definition_contexts: [],
            };
            let index = self.decl.output.symbols.len();
            self.decl.publish(
                file,
                &site.span,
                identity.clone(),
                decl::Kind::Binding,
                data,
            );
            self.decl
                .index(file, &site.span, &identity, Some(&qualified));
            self.symbol_indices.insert(qualified.clone(), index);
            result.push(Bound {
                site: site.clone(),
                id: identity,
                name: name.clone(),
                qualified,
                annotation: site.assignment_annotation.clone(),
                evidence: EvidenceId::new(cited),
            });
        }
        Ok(result)
    }

    fn site_record(
        &mut self,
        rel: &str,
        resolved: &ResolvedSite,
        bindings: &[Bound],
    ) -> Result<(), Stop> {
        let site = &resolved.site;
        let (mut scope, mut scope_id) = self.scope(rel, site)?;
        let call = matches!(site.kind, SiteKind::Call | SiteKind::Creation);
        let (target_names, construction, status) = self.site_target_state(rel, resolved, call)?;
        let use_text = if call {
            ""
        } else {
            match site.r#use {
                SiteUse::Type => "type",
                SiteUse::Read => "read",
                SiteUse::Write => "write",
                SiteUse::ReadWrite => "read_write",
                SiteUse::Value => "value",
            }
        };
        let identity = id(
            if call { "DARTCALL" } else { "DARTREF" },
            rel,
            site.span.start_byte,
            &[
                Part::Text(scope_id.as_deref().unwrap_or("")),
                Part::Text(&site.expression),
                Part::Text(use_text),
            ],
        );
        if !call
            && matches!(
                site.r#use,
                SiteUse::Read | SiteUse::ReadWrite | SiteUse::Value
            )
        {
            (scope, scope_id) = self
                .binding_scope(site, bindings)?
                .unwrap_or((scope, scope_id));
        }
        let module = self.file(rel)?.module.clone();
        let data = SiteData {
            source_scope: scope.clone(),
            source_definition_id: scope_id,
            source_module: module,
            source_file: rel.to_owned(),
            expression: expression(site),
            status,
            candidate_count: target_names.len(),
            targets: if status == Status::Unresolved {
                Vec::new()
            } else {
                target_names
            },
            candidates_truncated: false,
            reason: match status {
                Status::Resolved => "Analyzer resolved the source element",
                Status::PartiallyResolved => "multiple local source candidates remain",
                Status::Unresolved => "target is external, dynamic, or unresolved",
                Status::Unknown | Status::Decided => return Err(Stop::Input),
            },
            r#use: if call {
                None
            } else {
                Some(if site.r#use == SiteUse::Value {
                    SiteUse::Read
                } else {
                    site.r#use
                })
            },
            construction,
            result_bindings: self.result_bindings(site, bindings)?,
        };

        let cited = self.cite(rel, &site.span)?;
        let record = fact(
            identity,
            if call {
                RecordKind::Call
            } else {
                RecordKind::Reference
            },
            expression(site),
            vec![scope],
            cited,
            data,
        );
        if call {
            self.output.calls.push(record);
        } else {
            self.output.references.push(record);
        }
        Ok(())
    }

    fn binding_scope(
        &self,
        site: &Site,
        bindings: &[Bound],
    ) -> Result<Option<(String, Option<String>)>, Stop> {
        for binding in bindings.iter().rev() {
            self.decl.work.copies(&binding.site.scope_span)?;
            if binding.site.scope_span == site.scope_span
                && binding.site.span.start_byte <= site.span.start_byte
                && site.span.end_byte <= binding.site.span.end_byte
            {
                return Ok(Some((binding.qualified.clone(), Some(binding.id.clone()))));
            }
        }
        Ok(None)
    }

    fn result_bindings(&self, site: &Site, bindings: &[Bound]) -> Result<Vec<ResultBinding>, Stop> {
        let mut matching = Vec::new();
        for binding in bindings {
            self.decl.work.copies(&binding.site.initializer)?;
            if binding.site.initializer.as_deref() != Some(site.expression.as_str())
                || binding.site.span.start_byte > site.span.start_byte
                || site.span.start_byte > binding.site.span.end_byte
            {
                continue;
            }
            self.decl.work.text(&binding.name)?;
            matching.push(ResultBinding {
                id: binding.id.clone(),
                name: binding.name.clone(),
                target_kind: "name",
                annotation: binding.annotation.clone(),
                initializer: expression(site),
                evidence_ids: vec![binding.evidence.clone()],
                definition_contexts: [],
            });
        }
        Ok(matching)
    }
}
