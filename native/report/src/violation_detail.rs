// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence of a failed rule, copied from its evaluated violation without a second verdict.

use archkeel_eval::{Cited, CycleStep, Violation};
use serde::Serialize;

/// One violation row. `source` and `target` are its identity, which the baseline reads (AD-546):
/// for a cycle the sorted members joined by ` -> ` and the first member, as before #1657. That
/// text is no path; `members` and `path` (AD-786) name the set and the closed path of a cycle.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct ViolationDetail {
    source: String,
    target: Option<String>,
    cause: &'static str,
    evidence: Vec<String>,
    /// The members of a cycle, sorted: a set without order.
    #[serde(skip_serializing_if = "Option::is_none")]
    members: Option<Vec<String>>,
    /// The closed path of a cycle in import order (AD-484): each step imports the next, and the
    /// last step ends at the first member. Empty only when the members have no closed path.
    #[serde(skip_serializing_if = "Option::is_none")]
    path: Option<Vec<PathStep>>,
}

/// One step of the closed path of a cycle: the importing member, the imported member, the number
/// of imports that make the step and the evidence of the first of them (one import site).
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct PathStep {
    from: String,
    to: String,
    imports: usize,
    evidence: Option<String>,
}

impl PathStep {
    fn of(step: &CycleStep) -> Self {
        Self {
            from: step.from.clone(),
            to: step.to.clone(),
            imports: Vec::len(&step.imports),
            evidence: step.evidence.first().cloned(),
        }
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
        Self {
            source: cited.source_module.clone(),
            target: Some(cited.target_module.clone()),
            cause,
            evidence: cited.evidence.clone(),
            ..Self::default()
        }
    }

    /// The evidence of one differing assessment of a UML target row (AD-494).
    pub(crate) fn uml(diff: &archkeel_model::UmlDiff) -> Self {
        Self {
            source: diff.subject.clone(),
            target: Some(diff.fact.clone()),
            cause: diff.cause,
            evidence: diff.evidence.clone(),
            ..Self::default()
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
                ..Self::default()
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
                ..Self::default()
            },
            Violation::OuterLayer(layer) => Self {
                source: layer.source_component.clone(),
                target: Some(layer.target_component.clone()),
                cause: "dependency violates layer order",
                evidence: vec![layer.evidence.clone()],
                ..Self::default()
            },
            Violation::Cycle(cycle) => Self {
                source: cycle.members.join(" -> "),
                target: cycle.members.first().cloned(),
                cause: "dependency cycle",
                evidence: cycle.evidence.clone(),
                members: Some(cycle.members.clone()),
                path: Some(
                    IntoIterator::into_iter(&cycle.path)
                        .map(PathStep::of)
                        .collect(),
                ),
            },
            Violation::Construct(row) => Self {
                source: format!("{} ({})", row.owner, row.construct),
                target: None,
                cause: "forbidden construct",
                evidence: row.evidence.clone(),
                ..Self::default()
            },
            Violation::BoundaryType(row) => Self {
                source: row.subject.clone(),
                target: Some(row.text.clone()),
                cause: "written type outside the boundary types",
                evidence: row.evidence.clone(),
                ..Self::default()
            },
            // AD-670: the source is the module, the target the item in the form `module:name`.
            Violation::UnusedPublic(row) => Self {
                source: row.module.clone(),
                target: Some(format!("{}:{}", row.module, row.name)),
                cause: "public name that no other component uses",
                evidence: row.evidence.clone(),
                ..Self::default()
            },
            Violation::SymbolPlacement(row) => Self {
                source: row.name.clone(),
                target: Some(row.module.clone()),
                cause: "class outside allowed modules",
                evidence: row.evidence.clone(),
                ..Self::default()
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
                ..Self::default()
            },
            // AD-608: the target is the published name in the selector form `module:name`.
            Violation::Publication(found) => Self {
                source: found.cited.source_module.clone(),
                target: Some(format!("{}:{}", found.cited.source_module, found.name)),
                cause: "publication outside the public interface",
                evidence: found.cited.evidence.clone(),
                ..Self::default()
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

    fn step(from: &str, to: &str, evidence: &[&str]) -> archkeel_eval::CycleStep {
        archkeel_eval::CycleStep {
            from: from.to_owned(),
            to: to.to_owned(),
            from_component: None,
            to_component: None,
            imports: evidence.iter().map(|e| format!("IMP-{e}")).collect(),
            evidence: evidence.iter().map(|e| (*e).to_owned()).collect(),
        }
    }

    /// #1657, the shape of pydantic-core: the sorted members are no path (no import
    /// `argument_markers -> build_tools`). The row keeps the sorted set as its baseline identity
    /// and gives the closed path in import order, with one import site for each step.
    #[test]
    fn a_cycle_names_its_closed_path_in_import_order_and_its_sorted_members() {
        let members = ["argument_markers", "build_tools", "root", "tools"].map(str::to_owned);
        let cycle = archkeel_eval::Cyclic {
            id: "VIO-C".to_owned(),
            rule: "NO-CYCLES".to_owned(),
            members: members.to_vec(),
            facts: Vec::new(),
            evidence: ["E1", "E2", "E3", "E4"].map(str::to_owned).to_vec(),
            edges: None,
            path: vec![
                step("argument_markers", "tools", &["E3"]),
                step("tools", "root", &["E4", "E2"]),
                step("root", "argument_markers", &["E1"]),
            ],
        };
        let detail = ViolationDetail::of(&Violation::Cycle(Box::new(cycle)));
        assert_eq!(
            detail.source,
            "argument_markers -> build_tools -> root -> tools"
        );
        assert_eq!(detail.target.as_deref(), Some("argument_markers"));
        assert_eq!(detail.members.as_deref(), Some(&members[..]));
        let path: Vec<(&str, &str, Option<&str>, usize)> = detail
            .path
            .iter()
            .flatten()
            .map(|s| {
                (
                    s.from.as_str(),
                    s.to.as_str(),
                    s.evidence.as_deref(),
                    s.imports,
                )
            })
            .collect();
        assert_eq!(
            path,
            [
                ("argument_markers", "tools", Some("E3"), 1),
                ("tools", "root", Some("E4"), 2),
                ("root", "argument_markers", Some("E1"), 1),
            ]
        );
        assert!(ViolationDetail::of(&private_import(None)).path.is_none());
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
