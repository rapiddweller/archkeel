// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The marked graphs of AD-466 against the rules of the reference engine.

use std::collections::BTreeSet;

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
    findings(&documents, (&observed, &observed), &pairs(permitted))
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

fn with_possible(page: String, observed: &[(&str, &str)], possible: &[(&str, &str)]) -> usize {
    let documents = [("d.md".to_owned(), page)];
    let (observed, possible) = (pairs(observed), pairs(possible));
    findings(&documents, (&observed, &possible), &BTreeSet::new()).len()
}

#[test]
fn a_drawn_edge_that_the_code_may_use_is_no_drift_of_the_component_graph() {
    // #1021: the pair gap `a -> b` was dropped because the contract allows it.
    let page = block(COMPONENT, "    a --> c\n    a --> b\n");
    assert_eq!(with_possible(page.clone(), &[("a", "c")], &[("a", "c")]), 1);
    assert_eq!(
        with_possible(page, &[("a", "c")], &[("a", "c"), ("a", "b")]),
        0
    );
}

#[test]
fn an_observed_edge_that_is_not_drawn_stays_a_drift_whatever_may_be_used() {
    let page = block(COMPONENT, "    a --> b\n");
    assert_eq!(
        with_possible(page, &[("a", "b"), ("a", "c")], &[("a", "b")]),
        1
    );
}

#[test]
fn the_target_graph_does_not_excuse_an_unpermitted_edge() {
    let page = block(TARGET, "    a --> b\n");
    let documents = [("d.md".to_owned(), page)];
    let possible = pairs(&[("a", "b")]);
    let found = findings(&documents, (&BTreeSet::new(), &possible), &BTreeSet::new());
    let drift = found.iter().filter(|(code, ..)| *code == "graph.drift");
    assert_eq!(drift.count(), 1);
}
