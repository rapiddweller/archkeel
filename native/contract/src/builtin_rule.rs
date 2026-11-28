// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The built-in rule `STRING-IMPORT` (AD-1440): the rule that every run of a collector that states the
//! construct `string_import` holds. It is not in the contract bytes. It lives apart from the declaration
//! records (`string_import.rs`) so that the module graph has no cycle.

/// The id of the built-in rule that forbids a string import with a fixed name.
pub const STRING_IMPORT_RULE: &str = "STRING-IMPORT";

use crate::document::Contract;
use crate::model::{DecidedBy, ItemId, RuleHead, Selector};
use crate::model_constructs::{ConstructKind, ForbiddenConstruct};
use crate::rule::Rule;

impl Contract {
    /// This contract with the built-in rule `STRING-IMPORT` (AD-1440) for the modules of
    /// `namespace`. The rule is not in the contract bytes and its digest does not change. A
    /// contract that defines the id gets no second rule: the hygiene check refuses it.
    #[must_use]
    pub fn with_string_import_rule(&self, namespace: &str) -> Contract {
        let defined = self
            .rules()
            .iter()
            .any(|rule| crate::rule::head_of(rule).id().as_text() == STRING_IMPORT_RULE);
        if defined {
            return self.clone();
        }
        let head = RuleHead {
            id: ItemId(STRING_IMPORT_RULE.to_owned()),
            rationale: "A module that is named by a fixed string in an import call hides an edge that \
                        an import statement shows. Write the import statement, or declare the checked \
                        site in declarations.string_imports."
                .to_owned(),
            provenance: vec!["built in (AD-1440)".to_owned()],
            decided_by: DecidedBy::Architect,
        };
        let rule = ForbiddenConstruct {
            head,
            source: Selector(namespace.to_owned()),
            constructs: vec![ConstructKind::StringImport],
            allowed_sources: Vec::new(),
            exact_sources: Vec::new(),
            allowed_type_ignores: Vec::new(),
            selector: None,
        };
        let mut rules = self.rules().clone();
        rules.push(Rule::ForbiddenConstruct(rule));
        Contract {
            rules,
            ..self.clone()
        }
    }
}
