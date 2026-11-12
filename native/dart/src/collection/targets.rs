// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Scope selection and the precedence of call and construction resolutions.

use super::types::{BindingKind, Construction, ConstructionData, Resolution, ResolvedSite};
use super::{decl, Builder, Stop};
use crate::syntax::{Site, SiteKind};
use archkeel_facts::vocab::Status;
use std::collections::BTreeSet;

impl Builder<'_> {
    pub(super) fn scope(&self, rel: &str, site: &Site) -> Result<(String, Option<String>), Stop> {
        self.decl.work.text(rel)?;
        if let Some(name) = &site.scope {
            self.decl.work.text(name)?;
        }
        let indices = self.scopes.get(&(rel.to_owned(), site.scope.clone()));
        for stage in 0..4 {
            self.decl.work.charge(1)?;
            if stage < 2 && site.scope_span.is_none() {
                continue;
            }
            if stage == 3 && site.scope.is_none() {
                break;
            }
            let mut best: Option<&decl::Scope> = None;
            for index in indices.into_iter().flatten() {
                self.decl.work.charge(1)?;
                let candidate = self
                    .decl
                    .output
                    .scope_candidates
                    .get(*index)
                    .ok_or(Stop::Input)?;
                if !(candidate.5 <= site.span.start_byte && site.span.start_byte < candidate.6) {
                    continue;
                }
                let position = if stage < 2 {
                    site.scope_span.as_ref().ok_or(Stop::Input)?.start_byte
                } else {
                    site.span.start_byte
                };
                let matches = match stage {
                    0 | 2 => candidate.4.start_byte <= position && position <= candidate.4.end_byte,
                    1 | 3 => candidate.4.start_byte <= position,
                    _ => return Err(Stop::Input),
                };
                if matches && best.is_none_or(|old| candidate.4.start_byte > old.4.start_byte) {
                    best = Some(candidate);
                }
            }
            if let Some(best) = best {
                return Ok((best.2.clone(), Some(best.3.clone())));
            }
        }
        Ok((self.file(rel)?.module.clone(), None))
    }

    pub(super) fn site_target_state(
        &self,
        rel: &str,
        resolved: &ResolvedSite,
        call: bool,
    ) -> Result<(Vec<String>, Option<ConstructionData>, Status), Stop> {
        let site = &resolved.site;
        let mut names = BTreeSet::new();
        for binding in &resolved.bindings {
            self.decl.work.copies(binding)?;
            let key = (binding.rel_path.clone(), binding.span.start_byte);
            names.insert(
                self.decl
                    .names
                    .get(&key)
                    .cloned()
                    .unwrap_or_else(|| format!("{}.{}", binding.module, binding.name)),
            );
        }
        let mut target_names: Vec<_> = names.into_iter().collect();
        let mut constructor = false;
        let mut enum_binding = None;
        for binding in &resolved.bindings {
            self.decl.work.charge(1)?;
            if enum_binding.is_none() && binding.kind == BindingKind::EnumMember {
                enum_binding = Some(binding);
            }
            if matches!(
                binding.kind,
                BindingKind::Constructor | BindingKind::ImplicitConstructor
            ) {
                constructor = true;
            }
        }
        if !call {
            if let Some(binding) = enum_binding {
                let name = binding.name.split('.').next().unwrap_or("");
                let target = format!("{}.{name}", binding.module);
                if self.symbol_kind(&target) == Some(decl::Kind::Class) {
                    target_names = vec![target];
                }
            }
        }
        let resolution = if call && (site.kind == SiteKind::Creation || constructor) {
            let key = (
                rel.to_owned(),
                site.span.start_byte,
                site.expression.clone(),
            );
            let index = *self.construction_indices.get(&key).ok_or(Stop::Input)?;
            Some(
                &self
                    .input
                    .resolver
                    .constructions
                    .get(index)
                    .ok_or(Stop::Input)?
                    .resolution,
            )
        } else {
            None
        };
        let construction = resolution.map(construction_record);
        if let Some(binding) = resolution.and_then(|resolution| resolution.binding.as_ref()) {
            let name = binding.name.split('.').next().unwrap_or("");
            let target = format!("{}.{name}", binding.module);
            target_names = if self.symbol_kind(&target) == Some(decl::Kind::Class) {
                vec![target]
            } else {
                Vec::new()
            };
        }
        if call && construction.is_none() {
            self.decl.work.charge(target_names.len())?;
            target_names.retain(|name| {
                matches!(
                    self.symbol_kind(name),
                    Some(decl::Kind::Method | decl::Kind::Function)
                )
            });
        }
        let one = target_names.first().filter(|_| target_names.len() == 1);
        let mut status = if one.is_some_and(|target| {
            !call
                || construction.is_some()
                || matches!(
                    self.symbol_kind(target),
                    Some(decl::Kind::Method | decl::Kind::Function)
                )
        }) {
            Status::Resolved
        } else {
            Status::Unresolved
        };
        if resolved.status != Resolution::Resolved {
            status = if call && !target_names.is_empty() {
                Status::PartiallyResolved
            } else {
                Status::Unresolved
            };
        }
        if let Some(construction) = &construction {
            status = if construction.status == Status::Unresolved {
                Status::Unresolved
            } else {
                Status::Resolved
            };
        }
        Ok((target_names, construction, status))
    }
}

fn construction_record(resolution: &Construction) -> ConstructionData {
    let target = resolution.binding.as_ref().and_then(|binding| {
        let name = binding
            .name
            .split('.')
            .next()
            .filter(|name| !name.is_empty())?;
        Some(format!("{}.{name}", binding.module))
    });
    let status = match (&target, resolution.status) {
        (Some(_), Resolution::Resolved) => Status::Resolved,
        (Some(_), Resolution::Unknown | Resolution::Unresolved) => Status::PartiallyResolved,
        (None, Resolution::Resolved | Resolution::Unknown | Resolution::Unresolved) => {
            Status::Unresolved
        }
    };
    let reason = match status {
        Status::Resolved => "Analyzer resolved a local generative constructor".to_owned(),
        Status::PartiallyResolved => {
            "factory construction does not prove a local instance target".to_owned()
        }
        Status::Unresolved => resolution
            .reason
            .as_ref()
            .filter(|reason| !reason.is_empty())
            .cloned()
            .unwrap_or_else(|| "constructor target is external, dynamic, or unresolved".to_owned()),
        Status::Unknown | Status::Decided => {
            "constructor target is external, dynamic, or unresolved".to_owned()
        }
    };
    ConstructionData {
        status,
        targets: target.into_iter().collect(),
        candidates_truncated: false,
        reason,
    }
}
