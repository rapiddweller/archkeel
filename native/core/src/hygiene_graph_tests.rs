// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The marked graphs of AD-466 against the rules of the reference engine.

use std::collections::{BTreeMap, BTreeSet};

use super::{findings, text, Pair};

const COMPONENT: &str = "<!-- archkeel-component-graph -->";
const TARGET: &str = "<!-- archkeel-target-graph -->";

fn pairs(items: &[(&str, &str)]) -> BTreeSet<Pair> {
    items
        .iter()
        .map(|(a, b)| ((*a).to_owned(), (*b).to_owned()))
        .collect()
}

fn block(marker: &str, body: &str) -> String {
    format!("{marker}\n```mermaid\nflowchart LR\n{body}```\n")
}

fn codes(
    documents: &[(&str, String)],
    observed: &[(&str, &str)],
    permitted: &[(&str, &str)],
) -> Vec<String> {
    let documents: Vec<(String, String)> = documents
        .iter()
        .map(|(path, body)| ((*path).to_owned(), body.clone()))
        .collect();
    let observed = pairs(observed);
    findings(&documents, (&observed, &BTreeMap::new()), &pairs(permitted))
        .into_iter()
        .map(|(code, subject, _)| format!("{code} {subject}"))
        .collect()
}

#[test]
fn a_block_with_the_observed_edges_has_no_finding() {
    let page = block(COMPONENT, "    app --> data\n    data --> domain\n");
    assert!(codes(
        &[("d.md", page)],
        &[("app", "data"), ("data", "domain")],
        &[]
    )
    .is_empty());
}

#[test]
fn quoted_labels_and_entities_name_the_components() {
    let body = "    n_0[\"rs-flow\"]\n    n_1[\"a#35;b\"]\n    n_0 --> n_1\n";
    let page = block(COMPONENT, body);
    assert!(codes(&[("d.md", page)], &[("rs-flow", "a#b")], &[]).is_empty());
}

#[test]
fn universal_newlines_read_a_windows_page() {
    let page = block(COMPONENT, "    a --> b\n").replace('\n', "\r\n");
    let read = text(page.as_bytes()).unwrap_or_default();
    assert!(codes(&[("d.md", read)], &[("a", "b")], &[]).is_empty());
    assert_eq!(text(&[0xff, 0xfe]), None);
}

#[test]
fn the_component_block_must_exist_once_and_the_target_block_at_most_once() {
    let none = "# Page\n".to_owned();
    assert_eq!(
        codes(&[("d.md", none)], &[], &[]),
        ["graph.count architecture component graph"]
    );
    let twice = format!("{}{}", block(COMPONENT, ""), block(COMPONENT, ""));
    assert_eq!(
        codes(&[("d.md", twice)], &[], &[]),
        ["graph.count architecture component graph"]
    );
    let split = [
        ("a.md", block(COMPONENT, "")),
        ("b.md", block(COMPONENT, "")),
    ];
    assert_eq!(
        codes(&split, &[], &[]),
        ["graph.count architecture component graph"]
    );
    let targets = format!(
        "{}{}{}",
        block(COMPONENT, ""),
        block(TARGET, ""),
        block(TARGET, "")
    );
    assert_eq!(
        codes(&[("d.md", targets)], &[], &[]),
        ["graph.count architecture target graph"]
    );
}

#[test]
fn a_marker_without_a_fence_is_no_block() {
    let page = format!("{COMPONENT}\nno fence here\n");
    assert_eq!(
        codes(&[("d.md", page)], &[], &[]),
        ["graph.count architecture component graph"]
    );
}

#[test]
fn a_stale_edge_and_a_missing_edge_are_drift() {
    let page = block(COMPONENT, "    app --> data\n");
    assert_eq!(
        codes(&[("d.md", page.clone())], &[], &[]),
        ["graph.drift d.md (component graph)"]
    );
    assert_eq!(
        codes(
            &[("d.md", page)],
            &[("app", "data"), ("data", "domain")],
            &[]
        ),
        ["graph.drift d.md (component graph)"]
    );
}

#[test]
fn the_target_block_compares_the_permitted_pairs() {
    let page = format!("{}{}", block(COMPONENT, ""), block(TARGET, "    a --> b\n"));
    assert!(codes(&[("d.md", page.clone())], &[], &[("a", "b")]).is_empty());
    assert_eq!(
        codes(&[("d.md", page)], &[], &[]),
        ["graph.drift d.md (target graph)"]
    );
}

#[test]
fn a_line_that_the_block_cannot_hold_is_drift_with_equal_edges() {
    for line in [
        "    subgraph x\n",
        "    a -->|label| b\n",
        "    style a fill:#f00\n",
    ] {
        let page = block(COMPONENT, &format!("    a --> b\n{line}"));
        assert_eq!(
            codes(&[("d.md", page)], &[("a", "b")], &[]),
            ["graph.drift d.md (component graph)"],
            "{line}"
        );
    }
}

#[test]
fn comments_declarations_and_isolated_nodes_are_held() {
    let body = "    %% a comment\n    a --> b\n    c\n    n_0[\"d\"]\n";
    let page = block(COMPONENT, body);
    assert!(codes(&[("d.md", page)], &[("a", "b")], &[]).is_empty());
}

#[test]
fn an_ambiguous_label_is_drift() {
    for body in [
        "    n_0[\"a\"]\n    n_0[\"b\"]\n    n_0 --> n_1\n",
        "    n_0[\"a\"]\n    n_1[\"a\"]\n    n_0 --> n_1\n",
        "    n_0[\"#1114112;\"]\n",
    ] {
        let page = block(COMPONENT, body);
        let found = codes(&[("d.md", page)], &[], &[]);
        assert_eq!(found, ["graph.drift d.md (component graph)"], "{body}");
    }
}

#[test]
fn a_block_without_a_closing_fence_reads_to_the_next_same_marker() {
    let open = format!("{COMPONENT}\n```mermaid\n    a --> b\n");
    assert!(codes(&[("d.md", open)], &[("a", "b")], &[]).is_empty());
    // The other marker does not end the block: its line is a line that the block cannot hold.
    let page = format!("{COMPONENT}\n```mermaid\n    a --> b\n{TARGET}\n```mermaid\n```\n");
    let found = codes(&[("d.md", page)], &[("a", "b")], &[]);
    assert_eq!(found, ["graph.drift d.md (component graph)"]);
}

#[test]
fn only_a_mermaid_fence_opens_a_block() {
    // The reference engine looks for the text "```mermaid" and a newline after the marker.
    for fence in [
        "```text\n",
        "```\n",
        "``` mermaid\n",
        "```Mermaid\n",
        "~~~mermaid\n",
    ] {
        let page = format!("{COMPONENT}\n{fence}flowchart LR\n```\n");
        assert_eq!(
            codes(&[("d.md", page)], &[], &[]),
            ["graph.count architecture component graph"],
            "{fence}"
        );
    }
    let page = format!("{COMPONENT}\n````mermaid\nflowchart LR\n````\n");
    assert!(codes(&[("d.md", page)], &[], &[]).is_empty());
}

fn held(page: String, observed: &[(&str, &str)], unconfirmed: &[(&str, &str)]) -> Vec<String> {
    let documents = [("d.md".to_owned(), page)];
    let observed = pairs(observed);
    let unconfirmed: BTreeMap<Pair, String> = unconfirmed
        .iter()
        .map(|(a, b)| (((*a).to_owned(), (*b).to_owned()), format!("ns.{a}")))
        .collect();
    let edges = (&observed, &unconfirmed);
    findings(&documents, edges, &BTreeSet::new())
        .into_iter()
        .map(|(_, _, claim)| claim)
        .collect()
}

#[test]
fn a_drawn_edge_that_only_a_dropped_gap_names_is_held_with_its_own_text() {
    // #1021: the pair gap `a -> b` was dropped because the contract allows it. The edge is neither
    // observed nor absent: the finding stays, with a text that does not say "not found".
    let page = block(COMPONENT, "    a --> c\n    a --> b\n");
    let claims = held(page.clone(), &[("a", "c")], &[("a", "b")]);
    assert_eq!(
        claims,
        [
            "Drawn edge a -> b can be neither confirmed nor refuted: the call in ns.a may or may \
          not reach b."
        ]
    );
    let claims = held(page, &[("a", "c")], &[]);
    assert!(
        claims[0].contains("drawn and not found: a->b"),
        "{claims:?}"
    );
}

#[test]
fn an_absent_edge_and_a_held_edge_are_named_apart() {
    let page = block(COMPONENT, "    a --> b\n    a --> d\n");
    let claims = held(page, &[("a", "c")], &[("a", "b")]);
    assert!(claims[0].contains("drawn and not found: a->d; found and not drawn: a->c"));
    assert_eq!(claims.len(), 1);
    assert!(claims[0].contains(". Drawn edge a -> b can be neither confirmed nor refuted"));
}

#[test]
fn an_observed_edge_that_is_not_drawn_stays_a_drift_whatever_may_be_used() {
    let page = block(COMPONENT, "    a --> b\n");
    let claims = held(page, &[("a", "b"), ("a", "c")], &[]);
    assert_eq!(claims.len(), 1);
    assert!(claims[0].contains("found and not drawn: a->c"));
}

#[test]
fn the_target_graph_holds_no_edge() {
    let page = block(TARGET, "    a --> b\n");
    let documents = [("d.md".to_owned(), page)];
    let unconfirmed = BTreeMap::from([(("a".to_owned(), "b".to_owned()), "ns.a".to_owned())]);
    let found = findings(
        &documents,
        (&BTreeSet::new(), &unconfirmed),
        &BTreeSet::new(),
    );
    let drift: Vec<_> = found
        .iter()
        .filter(|(code, ..)| *code == "graph.drift")
        .collect();
    assert_eq!(drift.len(), 1);
    assert!(drift[0].2.contains("drawn and not found: a->b"));
}
