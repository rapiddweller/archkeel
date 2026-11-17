// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence of a failed rule, copied from its evaluated violation without a second verdict.

use archkeel_eval::{Cited, Violation};
use serde::Serialize;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct ViolationDetail {
    source: String,
    target: Option<String>,
    cause: &'static str,
    evidence: Vec<String>,
}

/// One detail: the shared shape of every arm of `ViolationDetail::of`.
fn detail(
    source: String,
    target: Option<String>,
    cause: &'static str,
    evidence: &[String],
) -> ViolationDetail {
    ViolationDetail {
        source,
        target,
        cause,
        evidence: evidence.to_vec(),
    }
}

impl ViolationDetail {
    pub(crate) fn source(&self) -> &str {
        &self.source
    }

    pub(crate) fn target(&self) -> Option<&str> {
        self.target.as_deref()
    }

    fn cited(cause: &'static str, cited: &Cited) -> Self {
        detail(
            cited.source_module.clone(),
            Some(cited.target_module.clone()),
            cause,
            &cited.evidence,
        )
    }

    /// The evidence of one differing assessment of a UML target row (AD-494).
    pub(crate) fn uml(diff: &archkeel_model::UmlDiff) -> Self {
        detail(
            diff.subject.clone(),
            Some(diff.fact.clone()),
            diff.cause,
            &diff.evidence,
        )
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
            Violation::Unassigned { name, evidence, .. } => detail(
                name.clone(),
                None,
                "module has no unique owner",
                std::slice::from_ref(evidence),
            ),
            Violation::NotAllowedChild {
                root,
                child,
                evidence,
                ..
            } => detail(
                root.clone(),
                Some(child.clone()),
                "child outside root layout",
                std::slice::from_ref(evidence),
            ),
            Violation::OuterLayer(layer) => detail(
                layer.source_component.clone(),
                Some(layer.target_component.clone()),
                "dependency violates layer order",
                std::slice::from_ref(&layer.evidence),
            ),
            Violation::Cycle(cycle) => detail(
                cycle.members.join(" -> "),
                cycle.members.first().cloned(),
                "dependency cycle",
                &cycle.evidence,
            ),
            Violation::Construct(row) => detail(
                format!("{} ({})", row.owner, row.construct),
                None,
                "forbidden construct",
                &row.evidence,
            ),
            Violation::BoundaryType(row) => detail(
                row.subject.clone(),
                Some(row.text.clone()),
                "written type outside the boundary types",
                &row.evidence,
            ),
            // AD-670: the source is the module, the target the item in the form `module:name`.
            Violation::UnusedPublic(row) => detail(
                row.module.clone(),
                Some(format!("{}:{}", row.module, row.name)),
                "public name that no other component uses",
                &row.evidence,
            ),
            Violation::SymbolPlacement(row) => detail(
                row.name.clone(),
                Some(row.module.clone()),
                "class outside allowed modules",
                &row.evidence,
            ),
            // AD-428: the target names the imported symbol in the selector form `module:name`.
            Violation::PrivateImport { cited, symbol, .. } => detail(
                cited.source_module.clone(),
                Some(match symbol {
                    Some(name) => format!("{}:{name}", cited.target_module),
                    None => cited.target_module.clone(),
                }),
                "import outside the public interface",
                &cited.evidence,
            ),
            // AD-608: the target is the published name in the selector form `module:name`.
            Violation::Publication(found) => detail(
                found.cited.source_module.clone(),
                Some(format!("{}:{}", found.cited.source_module, found.name)),
                "publication outside the public interface",
                &found.cited.evidence,
            ),
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
