// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! An optional, bounded display of existing model rows. It makes no decision.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_contract::Lifecycle;
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::sections::Section;
use archkeel_model::{claims, Model, ModelTree, Reason, Resolved};
use archkeel_report::Ruling;
use archkeel_store::Ingested;
use serde::Serialize;

const MAX_COMPONENTS: usize = 4_096;
const MAX_MODULES: usize = 10_000;
const MAX_EDGES: usize = 20_000;
const MAX_EVIDENCE: usize = 5;

#[derive(Serialize)]
pub(crate) struct Topology {
    version: u8,
    complete: bool,
    gaps: Vec<String>,
    truncated: bool,
    budgets: Counts,
    total: Counts,
    components: Vec<Component>,
    modules: Vec<Module>,
    edges: Vec<Edge>,
    component_edges: Vec<Edge>,
}

#[derive(Serialize)]
struct Counts {
    components: usize,
    modules: usize,
    edges: usize,
    component_edges: usize,
    evidence_per_edge: usize,
}

#[derive(Serialize)]
struct Component {
    id: String,
    name: String,
    parent: Option<String>,
    packages: Vec<String>,
    exact_modules: Vec<String>,
    planned: bool,
}

#[derive(Serialize)]
struct Module {
    name: String,
    path: String,
    component: Option<String>,
    ownership: &'static str,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
struct Location {
    path: String,
    line: i64,
}

#[derive(Serialize)]
struct Edge {
    id: String,
    source: String,
    target: String,
    resolution: &'static str,
    count: usize,
    evidence: Vec<Location>,
    evidence_total: usize,
    rules: BTreeSet<String>,
}

#[derive(Default)]
struct Bucket {
    count: usize,
    evidence: BTreeSet<Location>,
    rules: BTreeSet<String>,
}

type Key = (String, String, &'static str);

pub(crate) fn project(
    models: Result<&ModelTree, Reason>,
    reply: Option<&Ingested>,
    ruling: &Ruling,
    links: &BTreeMap<String, BTreeSet<String>>,
) -> Topology {
    let mut gaps = BTreeSet::new();
    // The scope text is the one the frame carries: read it from the ruling, not decide it again.
    let scope = serde_json::to_value(ruling).ok().and_then(|value| {
        value
            .get("scope")
            .and_then(|s| s.as_str().map(str::to_owned))
    });
    match scope.as_deref() {
        Some("complete") => {}
        Some(reason) => {
            gaps.insert(reason.to_owned());
        }
        None => {
            gaps.insert("scope: not readable from the ruling".to_owned());
        }
    }
    let mut components = Vec::new();
    let mut modules = Vec::new();
    let mut edges = Vec::new();
    let mut component_edges = Vec::new();
    match (models, reply) {
        (Ok(models), Some(reply)) => {
            components = component_rows(models);
            modules = module_rows(models);
            (edges, component_edges) = edge_rows(models, reply, links, &modules);
        }
        (Err(reason), _) => {
            gaps.insert(reason.to_string());
        }
        (Ok(_), None) => {
            gaps.insert("missing input: collector reply".to_owned());
        }
    }
    let evidence_per_edge = edges
        .iter()
        .chain(&component_edges)
        .map(|edge| edge.evidence_total)
        .max()
        .unwrap_or(0);
    let total = Counts {
        components: components.len(),
        modules: modules.len(),
        edges: edges.len(),
        component_edges: component_edges.len(),
        evidence_per_edge,
    };
    let truncated = total.components > MAX_COMPONENTS
        || total.modules > MAX_MODULES
        || total.edges > MAX_EDGES
        || total.component_edges > MAX_EDGES
        || evidence_per_edge > MAX_EVIDENCE;
    components.truncate(MAX_COMPONENTS);
    modules.truncate(MAX_MODULES);
    edges.truncate(MAX_EDGES);
    component_edges.truncate(MAX_EDGES);
    Topology {
        version: 1,
        complete: gaps.is_empty() && !truncated,
        gaps: gaps.into_iter().collect(),
        truncated,
        total,
        budgets: Counts {
            components: MAX_COMPONENTS,
            modules: MAX_MODULES,
            edges: MAX_EDGES,
            component_edges: MAX_EDGES,
            evidence_per_edge: MAX_EVIDENCE,
        },
        components,
        modules,
        edges,
        component_edges,
    }
}

fn component_rows(models: &ModelTree) -> Vec<Component> {
    let mut keys = BTreeMap::new();
    let mut rows = Vec::new();
    for model in models.models() {
        let mount = model.contract().mount();
        let parent = mount.as_ref().and_then(|key| keys.get(key)).cloned();
        for (_, component) in model.components().iter() {
            let id = component.id().as_text().to_owned();
            let name = component.label().as_text().to_owned();
            let key = mount
                .as_ref()
                .map_or_else(|| name.clone(), |key| format!("{key}:{name}"));
            keys.insert(key, id.clone());
            rows.push(Component {
                id,
                name,
                parent: parent.clone(),
                packages: component
                    .packages()
                    .iter()
                    .map(|p| p.as_text().to_owned())
                    .collect(),
                exact_modules: component
                    .exact_modules()
                    .iter()
                    .map(|p| p.as_text().to_owned())
                    .collect(),
                planned: component.lifecycle() == &Some(Lifecycle::Planned),
            });
        }
    }
    rows.sort_by(|a, b| a.id.cmp(&b.id));
    rows
}

fn module_rows(models: &ModelTree) -> Vec<Module> {
    let tree: Vec<&Model> = models.models().collect();
    let mut rows: Vec<Module> = models
        .root()
        .graph()
        .modules()
        .iter()
        .map(|(id, module)| {
            let model = tree
                .iter()
                .rev()
                .find(|model| model.holds(id))
                .copied()
                .unwrap_or(models.root());
            let component = model
                .owner(id)
                .and_then(|owner| model.components().get(owner))
                .map(|component| component.id().as_text().to_owned());
            let ownership = if component.is_some() {
                "owned"
            } else if model
                .components()
                .iter()
                .any(|(_, c)| claims(c, module.name()))
            {
                "ambiguous"
            } else {
                "unowned"
            };
            Module {
                name: module.name().to_owned(),
                path: module.file().to_owned(),
                component,
                ownership,
            }
        })
        .collect();
    rows.sort_by(|a, b| (&a.path, &a.name).cmp(&(&b.path, &b.name)));
    rows
}

fn edge_rows(
    models: &ModelTree,
    reply: &Ingested,
    links: &BTreeMap<String, BTreeSet<String>>,
    modules: &[Module],
) -> (Vec<Edge>, Vec<Edge>) {
    let facts = &reply.reply().facts;
    let locations: BTreeMap<_, _> = facts
        .evidence
        .iter()
        .map(|e| {
            (
                e.id.as_str(),
                Location {
                    path: e.file.clone(),
                    line: e.line.max(0),
                },
            )
        })
        .collect();
    let targets: BTreeMap<&str, &Target> = facts
        .imports
        .iter()
        .map(|target| (target.import_id().as_str(), target))
        .collect();
    let mut buckets = BTreeMap::new();
    for import in models.root().graph().imports() {
        // The typed target decides. A profile that reads each target by its module (Python, Dart)
        // gives the rules `Resolved::Local` for a library or a platform module: it is no module
        // of the scan, so the display calls it external (AD-466).
        let outside = matches!(
            targets.get(import.id()),
            Some(Target::External { .. } | Target::Builtin { .. })
        );
        let resolution = match import.resolved() {
            Resolved::Local if !outside => "resolved",
            _ => "external",
        };
        add(
            &mut buckets,
            (import.source_module(), import.target_module(), resolution),
            import.id(),
            import.evidence().iter().map(String::as_str),
            (&locations, links),
        );
    }
    let unresolved: BTreeSet<_> = facts
        .imports
        .iter()
        .filter_map(|target| match target {
            Target::Unresolved { .. } => Some(target.import_id().as_str()),
            _ => None,
        })
        .collect();
    for section in &facts.sections {
        if let Section::Imports(records) = section {
            for record in records
                .iter()
                .filter(|r| unresolved.contains(r.id.as_str()))
            {
                let data = record.data.data();
                add(
                    &mut buckets,
                    (
                        data.source_module.as_str(),
                        data.target_module.as_str(),
                        "unresolved",
                    ),
                    record.id.as_str(),
                    record.evidence_ids.iter().map(|id| id.as_str()),
                    (&locations, links),
                );
            }
        }
    }
    let owners: BTreeMap<_, _> = modules
        .iter()
        .map(|m| {
            (
                m.name.as_str(),
                m.component.as_deref().unwrap_or(m.ownership),
            )
        })
        .collect();
    let mut aggregated: BTreeMap<Key, Bucket> = BTreeMap::new();
    for ((source, target, resolution), bucket) in &buckets {
        let source = owners.get(source.as_str()).copied().unwrap_or("unowned");
        let target = owners.get(target.as_str()).copied().unwrap_or(resolution);
        let row = aggregated
            .entry((source.to_owned(), target.to_owned(), *resolution))
            .or_default();
        row.count += bucket.count;
        row.evidence.extend(bucket.evidence.iter().cloned());
        row.rules.extend(bucket.rules.iter().cloned());
    }
    (finish(buckets, "module"), finish(aggregated, "component"))
}

fn add<'a>(
    buckets: &mut BTreeMap<Key, Bucket>,
    (source, target, resolution): (&str, &str, &'static str),
    import: &str,
    evidence: impl Iterator<Item = &'a str>,
    (locations, links): (
        &BTreeMap<&str, Location>,
        &BTreeMap<String, BTreeSet<String>>,
    ),
) {
    let bucket = buckets
        .entry((source.to_owned(), target.to_owned(), resolution))
        .or_default();
    bucket.count += 1;
    bucket
        .evidence
        .extend(evidence.filter_map(|id| locations.get(id).cloned()));
    if let Some(rules) = links.get(import) {
        bucket.rules.extend(rules.iter().cloned());
    }
}

fn finish(buckets: BTreeMap<Key, Bucket>, level: &str) -> Vec<Edge> {
    buckets
        .into_iter()
        .map(|((source, target, resolution), bucket)| Edge {
            id: stable_id(
                "EDGE",
                &[
                    Part::Text(level),
                    Part::Text(&source),
                    Part::Text(&target),
                    Part::Text(resolution),
                ],
            ),
            source,
            target,
            resolution,
            count: bucket.count,
            evidence_total: bucket.evidence.len(),
            evidence: bucket.evidence.into_iter().take(MAX_EVIDENCE).collect(),
            rules: bucket.rules,
        })
        .collect()
}

#[cfg(test)]
#[path = "topology_projection_tests.rs"]
mod tests;
