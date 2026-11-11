// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The model of one run: what the contract and the reply give, derived once.

use archkeel_contract::{Component, Contract};
use archkeel_store::Ingested;

use crate::ids::{ComponentId, Table};
use crate::reason::{Reason, Unsupported};
use crate::section::Section;

/// The rows of one derived section. It has one variant per ported section, and no variant until
/// slice S1 ports `modules` and `packages`: a section that is not ported has no empty form.
#[derive(Debug)]
pub enum Rows {}

/// The model of one run.
#[derive(Debug)]
pub struct Model {
    components: Table<ComponentId, Component>,
    files: usize,
}

impl Model {
    /// Derive the model of a contract and a validated reply.
    pub fn derive(contract: &Contract, reply: &Ingested) -> Result<Model, Reason> {
        let components = Table::of_rows(contract.components().to_vec())
            .ok_or(Reason::TooManyRows("components"))?;
        Ok(Model {
            components,
            files: reply.reply().facts.files.len(),
        })
    }

    /// The components of the contract, in contract order.
    pub fn components(&self) -> &Table<ComponentId, Component> {
        &self.components
    }

    /// The component of a label.
    pub fn component(&self, label: &str) -> Option<ComponentId> {
        self.components
            .iter()
            .find(|(_, component)| component.label().as_text() == label)
            .map(|(id, _)| id)
    }

    /// The number of source files of the reply.
    pub fn files(&self) -> usize {
        self.files
    }

    /// The rows of one section. No section is ported yet: each answers its slice by name.
    pub fn rows(&self, section: Section) -> Result<Rows, Reason> {
        Err(Reason::Unsupported(Unsupported::Section(section)))
    }
}

#[cfg(test)]
#[path = "model_tests.rs"]
mod tests;
