// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts and the assessments that the comparison of a UML target shares (AD-494).

use archkeel_contract::{Entity, Target, VisibilityKind};

use crate::model::Model;

/// One assessment of the target that differs from the facts: the FAIL evidence of the row.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UmlDiff {
    /// The id of the target element: an entity, a relationship or the entity of a scope.
    pub subject: String,
    /// The fact that differs: a module or an import edge `source -> target`.
    pub fact: String,
    pub cause: &'static str,
    pub evidence: Vec<String>,
}

/// One assessment.
pub(crate) enum Assessed {
    Pass,
    Fail(UmlDiff),
    Unknown(String),
}

/// The facts that the comparison reads: the modules, the imports and the symbol table.
pub(crate) struct Facts<'m> {
    pub(crate) model: &'m Model,
    pub(crate) language: &'static str,
    /// The qualified names of the module entities of the target: the modules that it reads.
    pub(crate) read: &'m [&'m str],
    /// The profile keeps a type namespace apart from a value namespace (AD-508).
    pub(crate) namespaces: bool,
}

impl<'m> Facts<'m> {
    pub(crate) fn of(model: &'m Model, read: &'m [&'m str]) -> Self {
        let observed = model.graph().observed();
        Facts {
            model,
            language: observed.language,
            read,
            namespaces: observed.namespaces,
        }
    }

    /// The symbol table of the run, or the cause that it decides nothing (AD-508).
    pub(crate) fn symbols(&self) -> Result<&'m crate::symbols::Symbols, String> {
        if !self.model.graph().observed().symbol_facts {
            return Err(format!(
                "the {} collector states no symbol facts",
                self.language
            ));
        }
        let Some(table) = self.model.graph().symbols() else {
            return Err("the run has no symbol table".to_owned());
        };
        match &table.broken {
            Some(why) => Err(format!("the symbol facts are not consistent: {why}")),
            None => Ok(table),
        }
    }

    /// The modules of the reply named `name`, when `language` is the language of the reply.
    pub(crate) fn modules(&self, name: &str, language: &str) -> Vec<&'m crate::modules::Module> {
        if language != self.language {
            return Vec::new();
        }
        let modules = self.model.graph().modules();
        modules
            .iter()
            .map(|(_, module)| module)
            .filter(|module| module.name() == name)
            .collect()
    }

    /// True when the reply has the resolved local import edge `source -> target`.
    pub(crate) fn has_edge(&self, source: &str, target: &str) -> bool {
        self.model.graph().imports().iter().any(|import| {
            import.resolved == crate::imports::Resolved::Local
                && import.source_module == source
                && import.target_module == target
        })
    }
}

/// The entity of the target with the id `id`.
pub(crate) fn entity<'t>(target: &'t Target, id: &str) -> Option<&'t Entity> {
    target
        .entities()
        .iter()
        .find(|item| item.id().as_text() == id)
}

/// True when an entity states no detail that a module fact cannot hold.
pub(crate) fn plain(entity: &Entity) -> bool {
    entity.signature().is_none()
        && *entity.visibility().kind() == VisibilityKind::Unknown
        && entity.annotation().is_none()
        && entity.modifiers().is_empty()
        && entity.initializer().is_none()
}

/// The word of a closed contract value.
pub(crate) fn word<T: serde::Serialize>(value: &T) -> String {
    serde_json::to_value(value)
        .ok()
        .and_then(|value| value.as_str().map(str::to_owned))
        .unwrap_or_default()
}
