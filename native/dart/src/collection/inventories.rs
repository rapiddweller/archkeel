// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Duplicate names and final inventory status. A duplicate never becomes a unique binding.

use super::{decl, file_span, Builder, Stop};
use archkeel_facts::ids::EvidenceId;
use archkeel_facts::vocab::{ExceptionName, InventoryStatus};
use std::collections::{BTreeMap, BTreeSet};

impl Builder<'_> {
    pub(super) fn duplicates(&mut self) -> Result<(), Stop> {
        let mut counts: BTreeMap<String, usize> = BTreeMap::new();
        let mut evidence: BTreeMap<String, BTreeSet<EvidenceId>> = BTreeMap::new();
        for record in &self.decl.output.symbols {
            self.decl.work.copies(record)?;
            let qualified = &record.data.qualified_name;
            *counts.entry(qualified.clone()).or_default() += 1;
            evidence
                .entry(qualified.clone())
                .or_default()
                .extend(record.evidence_ids.iter().cloned());
            if let decl::Detail::Class {
                attribute_declarations,
                ..
            } = &record.data.detail
            {
                for attribute in attribute_declarations {
                    self.decl.work.copies(attribute)?;
                    let name = format!("{qualified}.{}", attribute.name);
                    *counts.entry(name.clone()).or_default() += 1;
                    evidence
                        .entry(name)
                        .or_default()
                        .extend(attribute.evidence_ids.iter().cloned());
                }
            }
        }
        for (name, count) in &counts {
            self.decl.work.text(name)?;
            if *count <= 1 {
                continue;
            }
            let ids = evidence.get(name).ok_or(Stop::Input)?;
            let first = ids.first().ok_or(Stop::Input)?;
            let rel = self
                .decl
                .evidence
                .get(first.as_str())
                .ok_or(Stop::Input)?
                .file
                .clone();
            self.gap(
                &rel,
                &file_span(),
                ExceptionName::DuplicateDeclaration,
                &format!("duplicate declaration {name}"),
                Some(ids.iter().cloned().collect()),
            )?;
        }
        for record in &mut self.decl.output.symbols {
            self.decl.work.charge(1)?;
            let qualified = &record.data.qualified_name;
            let owner_unique = counts.get(qualified) == Some(&1);
            record.data.source_binding_unique = owner_unique;
            if let decl::Detail::Class {
                attribute_declarations,
                member_inventories,
                ..
            } = &mut record.data.detail
            {
                if !owner_unique {
                    self.incomplete_ids.insert(record.id.as_str().to_owned());
                }
                let mut unique = Vec::new();
                for attribute in std::mem::take(attribute_declarations) {
                    self.decl.work.text(&attribute.name)?;
                    let name = format!("{qualified}.{}", attribute.name);
                    if counts.get(&name).is_some_and(|count| *count > 1) {
                        self.incomplete_ids.insert(record.id.as_str().to_owned());
                    }
                    if owner_unique && counts.get(&name) == Some(&1) {
                        unique.push(attribute);
                    }
                }
                self.decl.work.charge(unique.len())?;
                if let Some(first) = member_inventories
                    .as_mut()
                    .and_then(|items| items.first_mut())
                {
                    first.definition_ids = unique
                        .iter()
                        .map(|attribute| attribute.definition_id.clone())
                        .collect();
                }
                *attribute_declarations = unique;
            }
        }
        Ok(())
    }

    pub(super) fn finalize_inventories(&mut self) -> Result<(), Stop> {
        for record in &mut self.decl.output.symbols {
            self.decl.work.charge(1)?;
            if let decl::Detail::Class {
                member_inventories, ..
            } = &mut record.data.detail
            {
                if !self.sdk_supported {
                    *member_inventories = None;
                    continue;
                }
                let incomplete = self.incomplete_ids.contains(record.id.as_str())
                    || self
                        .incomplete_paths
                        .contains(&record.data.location.source_file);
                if !incomplete {
                    continue;
                }
                if let Some(inventories) = member_inventories {
                    for inventory in inventories {
                        self.decl.work.charge(1)?;
                        inventory.status = InventoryStatus::Partial;
                        inventory.reason = Some(
                            "source contains unsupported or incomplete declarations".to_owned(),
                        );
                    }
                }
            }
        }
        Ok(())
    }
}
