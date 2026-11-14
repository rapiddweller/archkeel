// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence of a failed rule, copied from its evaluated violation without a second verdict.

use archkeel_eval::{Cited, Violation};
use serde::Serialize;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct ViolationDetail {
    source: String,
    target: Option<String>,
    cause: &'static str,
    evidence: Vec<String>,
}

impl ViolationDetail {
    fn cited(cause: &'static str, cited: &Cited) -> Self {
        Self {
            source: cited.source_module.clone(),
            target: Some(cited.target_module.clone()),
            cause,
            evidence: cited.evidence.clone(),
        }
    }

    pub(crate) fn of(violation: &Violation) -> Self {
        match violation {
            Violation::Forbidden { cited, .. } => Self::cited("forbidden dependency", cited),
            Violation::OutsideScope { cited, .. } => Self::cited("dependency outside scope", cited),
            Violation::Undeclared { cited, .. } => {
                Self::cited("undeclared external dependency", cited)
            }
            Violation::Peer { cited, .. } => Self::cited("sibling isolation violation", cited),
            Violation::Unrequired { cited, .. } => {
                Self::cited("undeclared component dependency", cited)
            }
            Violation::Unassigned { name, evidence, .. } => Self {
                source: name.clone(),
                target: None,
                cause: "module has no unique owner",
                evidence: vec![evidence.clone()],
            },
            Violation::NotAllowedChild {
                root,
                child,
                evidence,
                ..
            } => Self {
                source: root.clone(),
                target: Some(child.clone()),
                cause: "child outside root layout",
                evidence: vec![evidence.clone()],
            },
            Violation::OuterLayer(layer) => Self {
                source: layer.source_component.clone(),
                target: Some(layer.target_component.clone()),
                cause: "dependency violates layer order",
                evidence: vec![layer.evidence.clone()],
            },
            Violation::Cycle(cycle) => Self {
                source: cycle.members.join(" -> "),
                target: cycle.members.first().cloned(),
                cause: "dependency cycle",
                evidence: cycle.evidence.clone(),
            },
            Violation::Construct(row) => Self {
                source: format!("{} ({})", row.owner, row.construct),
                target: None,
                cause: "forbidden construct",
                evidence: row.evidence.clone(),
            },
            // AD-428: the target names the imported symbol in the selector form `module:name`.
            Violation::PrivateImport { cited, symbol, .. } => Self {
                source: cited.source_module.clone(),
                target: Some(match symbol {
                    Some(name) => format!("{}:{name}", cited.target_module),
                    None => cited.target_module.clone(),
                }),
                cause: "import outside the public interface",
                evidence: cited.evidence.clone(),
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn private_import(symbol: Option<&str>) -> Violation {
        Violation::PrivateImport {
            id: "VIO-1".to_owned(),
            rule: "INTERFACE".to_owned(),
            cited: Cited {
                import: "IMP-1".to_owned(),
                source_module: "app.client".to_owned(),
                target_module: "app.impl".to_owned(),
                evidence: vec!["EVD-1".to_owned()],
            },
            symbol: symbol.map(str::to_owned),
            source_component: "COMP-CLIENT".to_owned(),
            target_component: "COMP-SERVICE".to_owned(),
        }
    }

    #[test]
    fn a_private_import_names_its_source_target_symbol_and_evidence() {
        let named = ViolationDetail::of(&private_import(Some("Secret")));
        assert_eq!(named.source, "app.client");
        assert_eq!(named.target.as_deref(), Some("app.impl:Secret"));
        assert_eq!(named.cause, "import outside the public interface");
        assert_eq!(named.evidence, ["EVD-1"]);
        let module = ViolationDetail::of(&private_import(None));
        assert_eq!(module.target.as_deref(), Some("app.impl"));
    }
}
