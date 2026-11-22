// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence of a failed rule, copied from its evaluated violation without a second verdict.

use archkeel_eval::{Cited, CycleStep, Violation};
use std::collections::BTreeMap;

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
    /// True for a possible dependency supplied by a declaration.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    possible: bool,
    /// The class fact of a placement violation: source names the class and target its module.
    #[serde(skip_serializing_if = "Option::is_none")]
    misplaced_class_fact: Option<String>,
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
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    possible: bool,
}

impl PathStep {
    fn of(step: &CycleStep) -> Self {
        Self {
            from: step.from.clone(),
            to: step.to.clone(),
            imports: Vec::len(&step.imports),
            evidence: step.evidence.first().cloned(),
            possible: step.possible,
        }
    }
}

/// One detail without a cycle: the shared shape of the arms of `ViolationDetail::of`.
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
        possible: false,
        misplaced_class_fact: None,
        members: None,
        path: None,
    }
}

impl ViolationDetail {
    pub(crate) fn source(&self) -> &str {
        &self.source
    }

    pub(crate) fn target(&self) -> Option<&str> {
        self.target.as_deref()
    }

    /// The (importer, imported) pairs of this row that rest on a declared possible import
    /// (AD-1043): the possible steps of a cycle, or the one pair of a possible dependency.
    pub(crate) fn declared_pairs(&self) -> Vec<(&str, &str)> {
        if let Some(path) = &self.path {
            let all: &[PathStep] = path;
            let steps = all.iter().filter(|step| step.possible);
            return steps
                .map(|step| (String::as_str(&step.from), String::as_str(&step.to)))
                .collect();
        }
        match (self.possible, &self.target) {
            (true, Some(target)) => vec![(String::as_str(&self.source), String::as_str(target))],
            _ => Vec::new(),
        }
    }

    /// For each rule and each row of it, the declared (importer, imported) pairs, as text.
    pub(crate) fn declared_by_rule(
        details: &BTreeMap<String, Vec<ViolationDetail>>,
    ) -> BTreeMap<String, Vec<Vec<(String, String)>>> {
        let own = |(source, target): (&str, &str)| (source.to_owned(), target.to_owned());
        let mut found = BTreeMap::new();
        for (rule, rows) in details {
            let each = rows.iter().map(|row| row.declared_pairs());
            found.insert(
                rule.clone(),
                each.map(|pairs| pairs.into_iter().map(own).collect())
                    .collect(),
            );
        }
        found
    }

    fn cited(cause: &'static str, cited: &Cited) -> Self {
        let mut row = detail(
            cited.source_module.clone(),
            Some(cited.target_module.clone()),
            cause,
            &cited.evidence,
        );
        row.possible = cited.possible;
        row
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

    fn cycle(cycle: &archkeel_eval::Cyclic) -> Self {
        Self {
            source: cycle.members.join(" -> "),
            target: cycle.members.first().cloned(),
            cause: "dependency cycle",
            evidence: cycle.evidence.clone(),
            possible: IntoIterator::into_iter(&cycle.path).any(|step| step.possible),
            misplaced_class_fact: None,
            members: Some(cycle.members.clone()),
            path: Some(
                IntoIterator::into_iter(&cycle.path)
                    .map(PathStep::of)
                    .collect(),
            ),
        }
    }

    fn outside_root(root: &str, child: &str, evidence: &String) -> Self {
        detail(
            root.to_owned(),
            Some(child.to_owned()),
            "child outside root layout",
            std::slice::from_ref(evidence),
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
            } => Self::outside_root(root, child, evidence),
            Violation::OuterLayer(layer) => detail(
                layer.source_component.clone(),
                Some(layer.target_component.clone()),
                "dependency violates layer order",
                std::slice::from_ref(&layer.evidence),
            ),
            Violation::Cycle(cycle) => Self::cycle(cycle),
            Violation::Construct(row) => detail(
                format!("{} ({})", row.owner, row.construct),
                None,
                "forbidden construct",
                &row.evidence,
            ),
            Violation::ProtocolDeclaration(row) | Violation::BoundaryType(row) => {
                let (target, cause) = match violation {
                    Violation::ProtocolDeclaration(_) => {
                        (None, "member does not name the canonical Protocol")
                    }
                    _ => (
                        Some(row.text.clone()),
                        "written type outside the boundary types",
                    ),
                };
                detail(row.subject.clone(), target, cause, &row.evidence)
            }
            // AD-670: the source is the module, the target the item in the form `module:name`.
            Violation::UnusedPublic(row) => detail(
                row.module.clone(),
                Some(format!("{}:{}", row.module, row.name)),
                "public name that no other component uses",
                &row.evidence,
            ),
            Violation::CallOwner {
                source,
                target,
                evidence,
                ..
            } => {
                let target = Some(target.clone());
                detail(source.clone(), target, "call outside its owner", evidence)
            }
            Violation::ForbiddenArgument {
                source,
                target,
                parameter,
                evidence,
                ..
            } => detail(
                source.clone(),
                Some(format!("{target}.{parameter}")),
                "written string literal passed to restricted parameter",
                evidence,
            ),
            Violation::SymbolPlacement(row) => Self {
                possible: false,
                misplaced_class_fact: Some(row.fact_id.clone()),
                ..detail(
                    row.name.clone(),
                    Some(row.module.clone()),
                    "class outside allowed modules",
                    &row.evidence,
                )
            },
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
                possible: false,
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
            possible: false,
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

    #[test]
    fn only_the_placement_row_exports_the_cited_class_fact() {
        let placement = Violation::SymbolPlacement(Box::new(archkeel_eval::PlacedClass {
            id: "VIO-1".into(),
            rule: "LAYOUT".into(),
            fact_id: "SYM-1".into(),
            name: "app.Client".into(),
            module: "app".into(),
            kind: "class".into(),
            evidence: vec!["E1".into()],
        }));
        let wire = |v: &Violation| serde_json::to_value(ViolationDetail::of(v)).unwrap();
        let row = wire(&placement);
        assert_eq!(row["misplaced_class_fact"], "SYM-1");
        assert_eq!(row["source"], "app.Client");
        assert_eq!(row["target"], "app");
        assert!(wire(&private_import(Some("Client")))
            .get("misplaced_class_fact")
            .is_none());
    }
}
