// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::data::ImportData;
use archkeel_facts::ids::ModuleName;
use archkeel_facts::{GapFact, ImportFact, Record};

use super::*;

fn proofs(causes: &[bool], erased: bool) -> (Option<ResolutionDimension>, bool) {
    let mut builder = Builder::default();
    builder.gap("unread caller", None, "src");
    let mut pending = PendingPool::new();
    for &execution in causes {
        pending.push(
            &mut builder,
            ("src", "dst"),
            ("src.rs", &Site::default()),
            &format!("candidate {execution}"),
            (erased && execution, execution, execution),
        );
    }
    let root = archkeel_snapshot::test_tree::Tree::new(&[]);
    let mut source = archkeel_snapshot::Snapshot::new(&root.path());
    let workspace = crate::crates::discover(&mut source, &[], "ns");
    let index = crate::modules::index(&workspace, &[]);
    let homes = LazyHomes {
        trait_homes: Vec::new(),
        drop_homes: Vec::new(),
        crate_deps: Vec::new(),
    };
    settle(&mut builder, pending, (&index, &[]), &homes);
    let gaps = builder.materialize_test_gaps();
    let pair = gaps
        .iter()
        .find(|gap| gap.data.data().source_module.is_some());
    let data = pair.expect("the pair is reachable").data.data();
    (data.resolution_dimension, data.no_name_route)
}

#[test]
fn a_named_cause_stays_open_before_or_after_an_execution_cause() {
    assert_eq!(
        proofs(&[true], false),
        (Some(ResolutionDimension::RuntimeEffects), true)
    );
    assert_eq!(
        proofs(&[true, true], false),
        (Some(ResolutionDimension::RuntimeEffects), true)
    );
    assert_eq!(proofs(&[true, false], false), (None, false));
    assert_eq!(proofs(&[false, true], false), (None, false));
    assert_eq!(proofs(&[true, false, true], false), (None, false));
}

#[test]
fn an_erased_destructor_is_execution_unless_the_pair_has_a_named_cause() {
    assert_eq!(
        proofs(&[true], true),
        (Some(ResolutionDimension::RuntimeEffects), true)
    );
    assert_eq!(proofs(&[true, false], true), (None, false));
    assert_eq!(proofs(&[false, true], true), (None, false));
}

#[test]
fn compact_named_sites_stream_in_unknown_id_order_and_merge_no_name_route() {
    let mut builder = Builder::default();
    let site_a = Site {
        line: 3,
        end_line: 3,
        column: 1,
        excerpt: "a.f()".to_owned(),
    };
    let site_b = Site {
        line: 7,
        end_line: 7,
        column: 1,
        excerpt: "b.g()".to_owned(),
    };
    builder.named_site(("src", "dst"), ("src.rs", &site_a), "reason a", true);
    builder.named_site(("src", "dst"), ("src.rs", &site_a), "reason a", false);
    builder.named_site(("src", "dst"), ("src.rs", &site_b), "reason b", true);
    let (_, holder) = builder.take_gaps_and_named_sites();
    let mut emitted = Vec::new();
    holder.stream_named_sites(&mut |record| emitted.push(record.clone()));
    assert_eq!(emitted.len(), 2);
    assert!(emitted[0].id < emitted[1].id);
    let merged = emitted
        .iter()
        .find(|record| record.title == "reason a")
        .expect("merged site");
    assert!(!merged.data.data().no_name_route);
}

// --- Differential refinement oracle (naive cartesian String BFS vs lazy u32 BitSet settle) ---

#[derive(Clone)]
struct RefPending {
    source: String,
    rel: String,
    site: Site,
    target: String,
    reason: String,
    erased: bool,
    execution: bool,
    no_name_route: bool,
}

#[derive(Clone)]
struct RefHome {
    target: String,
    crate_index: usize,
    rel: String,
    site: Site,
    reason: String,
}

struct Scenario {
    modules: Vec<Module>,
    imports: Vec<(&'static str, &'static str)>,
    open_gaps: Vec<(&'static str, &'static str)>,
    opaque_values: Vec<&'static str>,
    pending: Vec<RefPending>,
    trait_homes: Vec<RefHome>,
    drop_homes: Vec<RefHome>,
    crate_deps: Vec<Vec<bool>>,
}

fn fake_module(name: &str, crate_index: usize, has_static: bool) -> Module {
    let scan = crate::scan::Scan {
        has_static,
        ..Default::default()
    };
    Module {
        crate_index,
        rel: format!("{name}.rs"),
        module: name.to_owned(),
        target: name.split('.').next().unwrap_or(name).to_owned(),
        has_children: false,
        first_line: String::new(),
        blank: false,
        scan,
        gated: false,
        gates: None,
    }
}

fn add_import(builder: &mut Builder, source: &str, target: &str) {
    let mut data = ImportData::statement();
    data.source_module = ModuleName::new(source);
    data.target_module = ModuleName::new(target);
    let record = crate::builder::import_record(
        (&format!("IMPORT-{source}-{target}"), "EV-1".to_owned()),
        (source, target),
        vec![source.to_owned(), target.to_owned()],
        ImportFact::Import(data),
    );
    builder.imports.push(record);
}

fn insert_dot_ancestors(targets: &mut BTreeSet<String>, target: &str) {
    let mut rest = target;
    while let Some((prefix, _)) = rest.rsplit_once('.') {
        targets.insert(prefix.to_owned());
        rest = prefix;
    }
}

fn ref_reach(
    builder: &Builder,
    edges: &BTreeSet<(String, String)>,
    ingress: &BTreeSet<String>,
    source: &str,
) -> (bool, bool, BTreeSet<String>) {
    let mut next: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (s, t) in edges {
        next.entry(s.clone()).or_default().push(t.clone());
    }
    for &(s_id, t_id) in builder.gapped.keys() {
        let s = builder.interned_text(s_id).to_owned();
        let t = builder.interned_text(t_id).to_owned();
        next.entry(s).or_default().push(t);
    }
    let open_modules: Vec<String> = builder
        .gaps
        .values()
        .filter(|rec| rec.data.data().source_module.is_none())
        .map(|rec| {
            rec.data
                .data()
                .module
                .as_ref()
                .map_or(String::new(), |m| m.as_str().to_owned())
        })
        .collect();
    let anywhere = open_modules.iter().any(String::is_empty);
    let open: BTreeSet<String> = open_modules.into_iter().filter(|m| !m.is_empty()).collect();
    let mut visited = BTreeSet::new();
    let mut targets = BTreeSet::new();
    let mut incoming = false;
    let mut queue = VecDeque::from([source.to_owned()]);
    while let Some(module) = queue.pop_front() {
        if anywhere || open.contains(&module) {
            return (true, incoming, targets);
        }
        incoming |= ingress.contains(&module);
        for target in next.get(&module).into_iter().flatten() {
            if visited.insert(target.clone()) {
                targets.insert(target.clone());
                insert_dot_ancestors(&mut targets, target);
                queue.push_back(target.clone());
            }
        }
    }
    (false, incoming, targets)
}

fn ref_settle_pass(
    builder: &mut Builder,
    mut open: Vec<RefPending>,
    edges: &BTreeSet<(String, String)>,
    edge_ids: &HashSet<(u32, u32)>,
    ingress: &BTreeSet<String>,
) -> Vec<RefPending> {
    let named: BTreeSet<(String, String)> = open
        .iter()
        .filter(|p| !p.execution)
        .map(|p| (p.source.clone(), p.target.clone()))
        .collect();
    loop {
        let mut ready = Vec::new();
        let mut waiting = Vec::new();
        for p in open {
            let (any, inc, targets) = ref_reach(builder, edges, ingress, &p.source);
            let ok = if p.erased {
                any || inc
            } else {
                any || targets.contains(&p.target)
            };
            if ok {
                ready.push(p);
            } else {
                waiting.push(p);
            }
        }
        if ready.is_empty() {
            return waiting;
        }
        for p in &ready {
            if !p.execution
                && p.source != p.target
                && edges.contains(&(p.source.clone(), p.target.clone()))
            {
                builder.named_site(
                    (&p.source, &p.target),
                    (&p.rel, &p.site),
                    &p.reason,
                    p.no_name_route,
                );
                continue;
            }
            let dim = if p.execution && !named.contains(&(p.source.clone(), p.target.clone())) {
                ResolutionDimension::RuntimeEffects
            } else {
                ResolutionDimension::Imports
            };
            once_gap(
                builder,
                edge_ids,
                (&p.source, &p.target),
                (&p.rel, &p.site),
                &p.reason,
                Some(dim),
                p.no_name_route,
            );
        }
        open = waiting;
    }
}

fn push_drop_candidates(open: &mut Vec<RefPending>, homes: &[RefHome], modules: &[Module]) {
    for home in homes {
        for caller in modules.iter().filter(|m| m.module != home.target) {
            open.push(RefPending {
                source: caller.module.clone(),
                rel: home.rel.clone(),
                site: home.site.clone(),
                target: home.target.clone(),
                reason: home.reason.clone(),
                erased: true,
                execution: true,
                no_name_route: true,
            });
        }
    }
}

fn run_reference(scenario: &Scenario) -> (Vec<Record<GapFact>>, Vec<Record<GapFact>>) {
    let mut builder = Builder::default();
    for &(s, t) in &scenario.imports {
        add_import(&mut builder, s, t);
    }
    for &(reason, module) in &scenario.open_gaps {
        builder.gap(reason, None, module);
    }
    for &opaque in &scenario.opaque_values {
        builder.opaque_values.insert(opaque.to_owned());
    }
    let edges: BTreeSet<(String, String)> = scenario
        .imports
        .iter()
        .map(|&(s, t)| (s.to_owned(), t.to_owned()))
        .collect();
    let edge_ids = import_edges(&mut builder);
    let mut open = scenario.pending.clone();
    for home in &scenario.trait_homes {
        for caller in &scenario.modules {
            if caller.module == home.target
                || !crate_reaches(&scenario.crate_deps, caller.crate_index, home.crate_index)
            {
                continue;
            }
            open.push(RefPending {
                source: caller.module.clone(),
                rel: home.rel.clone(),
                site: home.site.clone(),
                target: home.target.clone(),
                reason: home.reason.clone(),
                erased: false,
                execution: true,
                no_name_route: true,
            });
        }
    }
    open = ref_settle_pass(&mut builder, open, &edges, &edge_ids, &BTreeSet::new());
    let mut ingress: BTreeSet<String> = builder.opaque_values.clone();
    for m in &scenario.modules {
        if m.scan.has_static {
            ingress.insert(m.module.clone());
        }
    }
    if !scenario.drop_homes.is_empty() && !ingress.is_empty() {
        push_drop_candidates(&mut open, &scenario.drop_homes, &scenario.modules);
        drop(ref_settle_pass(
            &mut builder,
            open,
            &edges,
            &edge_ids,
            &ingress,
        ));
    }
    let (gaps, holder) = builder.take_gaps_and_named_sites();
    let mut named = Vec::new();
    holder.stream_named_sites(&mut |record| named.push(record.clone()));
    (gaps, named)
}

fn run_optimized(scenario: &Scenario) -> (Vec<Record<GapFact>>, Vec<Record<GapFact>>) {
    let mut builder = Builder::default();
    for &(s, t) in &scenario.imports {
        add_import(&mut builder, s, t);
    }
    for &(reason, module) in &scenario.open_gaps {
        builder.gap(reason, None, module);
    }
    for &opaque in &scenario.opaque_values {
        builder.opaque_values.insert(opaque.to_owned());
    }
    let mut pool = PendingPool::new();
    for p in &scenario.pending {
        pool.push(
            &mut builder,
            (&p.source, &p.target),
            (&p.rel, &p.site),
            &p.reason,
            (p.erased, p.execution, p.no_name_route),
        );
    }
    let to_lazy = |list: &[RefHome], b: &mut Builder| -> Vec<LazyHome> {
        list.iter()
            .map(|h| LazyHome {
                target: b.intern_text(&h.target),
                crate_index: h.crate_index,
                rel: h.rel.clone(),
                site: h.site.clone(),
                reason: h.reason.clone(),
            })
            .collect()
    };
    let homes = LazyHomes {
        trait_homes: to_lazy(&scenario.trait_homes, &mut builder),
        drop_homes: to_lazy(&scenario.drop_homes, &mut builder),
        crate_deps: scenario.crate_deps.clone(),
    };
    let root = archkeel_snapshot::test_tree::Tree::new(&[]);
    let mut source = archkeel_snapshot::Snapshot::new(&root.path());
    let workspace = crate::crates::discover(&mut source, &[], "ns");
    let index = crate::modules::index(&workspace, &[]);
    settle(&mut builder, pool, (&index, &scenario.modules), &homes);
    let (gaps, holder) = builder.take_gaps_and_named_sites();
    let mut named = Vec::new();
    holder.stream_named_sites(&mut |record| named.push(record.clone()));
    (gaps, named)
}

fn assert_equivalent(scenario: &Scenario) {
    let (ref_gaps, ref_named) = run_reference(scenario);
    let (opt_gaps, opt_named) = run_optimized(scenario);
    assert_eq!(opt_gaps, ref_gaps, "gaps differ from reference oracle");
    assert_eq!(
        opt_named, ref_named,
        "named sites differ from reference oracle"
    );
}

fn site_at(line: i64, excerpt: &str) -> Site {
    Site {
        line,
        end_line: line,
        column: 1,
        excerpt: excerpt.to_owned(),
    }
}

#[test]
fn differential_cyclic_imports_chained_traits_and_drop_ingress() {
    let scenario = Scenario {
        modules: vec![
            fake_module("c0.a", 0, false),
            fake_module("c0.b", 0, false),
            fake_module("c0.c", 0, true),
            fake_module("c1.impl_m", 1, false),
            fake_module("c1.drop_m", 1, false),
            fake_module("c2.isolated", 2, false),
        ],
        imports: vec![
            ("c0.a", "c0.b"),
            ("c0.b", "c0.c"),
            ("c0.c", "c0.a"),
            ("c0.b", "c1.impl_m"),
        ],
        open_gaps: vec![],
        opaque_values: vec!["c2.isolated"],
        pending: vec![
            RefPending {
                source: "c0.a".into(),
                rel: "c0.a.rs".into(),
                site: site_at(10, "x.m()"),
                target: "c1.impl_m".into(),
                reason: "method m on c1.impl_m".into(),
                erased: false,
                execution: false,
                no_name_route: false,
            },
            RefPending {
                source: "c0.b".into(),
                rel: "c0.b.rs".into(),
                site: site_at(12, "y.m()"),
                target: "c1.impl_m".into(),
                reason: "direct-edge named site".into(),
                erased: false,
                execution: false,
                no_name_route: true,
            },
            RefPending {
                source: "c0.b".into(),
                rel: "c0.b.rs".into(),
                site: site_at(12, "y.m()"),
                target: "c1.impl_m".into(),
                reason: "direct-edge named site".into(),
                erased: false,
                execution: false,
                no_name_route: false,
            },
        ],
        trait_homes: vec![RefHome {
            target: "c1.impl_m".into(),
            crate_index: 1,
            rel: "c1.impl_m.rs".into(),
            site: site_at(5, "impl Tr for S"),
            reason: "trait impl in c1.impl_m".into(),
        }],
        drop_homes: vec![RefHome {
            target: "c1.drop_m".into(),
            crate_index: 1,
            rel: "c1.drop_m.rs".into(),
            site: site_at(8, "impl Drop for D"),
            reason: "drop impl in c1.drop_m".into(),
        }],
        // Crate 0 depends on crate 1; crate 2 is independent of crates 0 and 1.
        crate_deps: vec![
            vec![true, true, false],
            vec![false, true, false],
            vec![false, false, true],
        ],
    };
    assert_equivalent(&scenario);
}

#[test]
fn differential_dot_prefix_ancestors_transitive_unlock_and_open_gaps() {
    let scenario = Scenario {
        modules: vec![
            fake_module("app.entry", 0, false),
            fake_module("app.mid", 0, false),
            fake_module("app.mid.leaf", 0, false),
            fake_module("app.open_caller", 0, false),
            fake_module("app.target", 0, false),
        ],
        imports: vec![("app.entry", "app.mid.leaf")],
        open_gaps: vec![("unread macro in open_caller", "app.open_caller")],
        opaque_values: vec![],
        pending: vec![
            // app.entry reaches app.mid.leaf -> ancestor app.mid unlocks this gap to app.target!
            RefPending {
                source: "app.entry".into(),
                rel: "app.entry.rs".into(),
                site: site_at(4, "v.step()"),
                target: "app.mid".into(),
                reason: "ancestor reachability to app.mid".into(),
                erased: false,
                execution: false,
                no_name_route: true,
            },
            RefPending {
                source: "app.mid".into(),
                rel: "app.mid.rs".into(),
                site: site_at(6, "w.go()"),
                target: "app.target".into(),
                reason: "second-hop pending".into(),
                erased: false,
                execution: false,
                no_name_route: false,
            },
            // app.open_caller has an open gap -> reaches every target immediately.
            RefPending {
                source: "app.open_caller".into(),
                rel: "app.open_caller.rs".into(),
                site: site_at(9, "z.run()"),
                target: "app.target".into(),
                reason: "open caller reaches target".into(),
                erased: false,
                execution: false,
                no_name_route: true,
            },
        ],
        trait_homes: vec![RefHome {
            target: "app.target".into(),
            crate_index: 0,
            rel: "app.target.rs".into(),
            site: site_at(2, "impl Display"),
            reason: "trait impl in app.target".into(),
        }],
        drop_homes: vec![],
        crate_deps: vec![vec![true]],
    };
    assert_equivalent(&scenario);
}
