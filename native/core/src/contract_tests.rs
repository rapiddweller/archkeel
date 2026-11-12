// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The tree of the `Contract` request against a hostile shell (AD-379): each wrong input is a
//! named state with bounded memory, and no partial tree is ever used.

use std::collections::BTreeMap;

use serde_json::{json, Value};

use super::{answer, ContractInput, ContractState, InsideFile, MAX_INSIDE_BYTES, MAX_INSIDE_FILES};

const ROOT: &str = "architecture-contract.json";

fn component(label: &str, inside: Option<&str>) -> Value {
    let mut item = json!({
        "id": format!("C-{label}"), "label": label, "role": "component",
        "packages": [format!("p.{label}")], "responsibilities": ["Own it."],
        "forbidden_responsibilities": [], "provenance": ["d.md"],
    });
    if let (Some(path), Some(map)) = (inside, item.as_object_mut()) {
        map.insert("inside".to_owned(), json!(path));
    }
    item
}

fn contract(components: Vec<Value>, rules: Vec<Value>) -> Vec<u8> {
    let value = json!({"schema_version": "3.14.0", "components": components, "rules": rules});
    serde_json::to_vec(&value).unwrap_or_default()
}

fn assignment(id: &str, source: &str) -> Value {
    json!({"id": id, "kind": "complete_assignment", "source": source,
           "rationale": "Each module has an owner.", "provenance": ["d.md"],
           "decided_by": "architect"})
}

fn file(path: &str, identity: &str, bytes: &[u8]) -> InsideFile {
    InsideFile {
        reference: path.to_owned(),
        identity: identity.to_owned(),
        bytes: bytes.to_vec(),
    }
}

fn input(root: &[u8], insides: Vec<InsideFile>) -> ContractInput {
    ContractInput {
        path: ROOT.to_owned(),
        bytes: root.to_vec(),
        insides,
    }
}

/// A shell that reads each asked path from `files`, in rounds, until the state names no path or
/// a round adds no file. It returns the last state and the number of rounds.
fn shell(root: &[u8], files: &BTreeMap<&str, Vec<u8>>) -> (ContractState, usize) {
    let mut sent: Vec<InsideFile> = Vec::new();
    for round in 1..=super::MAX_INSIDE_FILES {
        let copy = sent
            .iter()
            .map(|f| file(&f.reference, &f.identity, &f.bytes));
        let (state, _) = answer(input(root, copy.collect()));
        let ContractState::Missing(paths) = &state else {
            return (state, round);
        };
        let before = sent.len();
        for path in paths {
            if let Some(bytes) = files.get(path.as_str()) {
                sent.push(file(path, path, bytes));
            }
        }
        if sent.len() == before {
            return (state, round);
        }
    }
    (ContractState::Refused("no end".to_owned()), 0)
}

fn refused(state: &ContractState) -> String {
    match state {
        ContractState::Refused(message) => message.clone(),
        other => format!("not refused: {other:?}"),
    }
}

#[test]
fn a_nested_tree_assembles_in_rounds_and_names_each_inside_rule() {
    let root = contract(
        vec![component("a", Some("a.json"))],
        vec![assignment("R", "a")],
    );
    let middle = contract(
        vec![component("b", Some("b.json"))],
        vec![assignment("M", "b")],
    );
    let leaf = contract(vec![component("c", None)], vec![assignment("L", "c")]);
    let files = BTreeMap::from([("a.json", middle), ("b.json", leaf)]);
    let (state, rounds) = shell(&root, &files);
    assert_eq!(rounds, 3);
    let ContractState::Parsed(rules) = state else {
        assert_eq!(format!("{state:?}"), "a parsed tree");
        return;
    };
    let ids: Vec<&String> = rules.keys().collect();
    assert_eq!(ids, ["R", "a:M", "a:b:L"]);
    let sent = vec![
        file("a.json", "a.json", &files["a.json"]),
        file("b.json", "b.json", &files["b.json"]),
    ];
    let (_, usable) = answer(input(&root, sent));
    let usable = usable.expect("a usable tree");
    assert!(usable.mounted);
    assert_eq!(usable.root.rules().len(), 1);
    let inside: Vec<&str> = usable.inside.iter().map(|(id, _)| id.as_str()).collect();
    assert_eq!(inside, ["a:M", "a:b:L"]);
}

#[test]
fn a_root_without_mounts_is_used_as_it_is_and_files_that_it_does_not_mount_are_refused() {
    let root = contract(vec![component("a", None)], vec![]);
    let (state, usable) = answer(input(&root, vec![]));
    assert!(matches!(state, ContractState::Parsed(_)));
    assert!(usable.is_some_and(|usable| !usable.mounted));
    let extra = vec![file("x.json", "x.json", &root)];
    let (state, usable) = answer(input(&root, extra));
    assert!(refused(&state).contains("Unmounted"), "{state:?}");
    assert!(usable.is_none());
}

#[test]
fn a_file_that_the_tree_does_not_ask_for_is_refused() {
    let root = contract(vec![component("a", Some("a.json"))], vec![]);
    let leaf = contract(vec![], vec![]);
    let sent = vec![
        file("a.json", "a.json", &leaf),
        file("other.json", "other.json", &leaf),
    ];
    let (state, usable) = answer(input(&root, sent));
    assert!(
        refused(&state).contains("Unmounted inputs: other.json"),
        "{state:?}"
    );
    assert!(usable.is_none());
}

#[test]
fn a_wrong_identity_or_an_unsafe_path_is_refused() {
    let root = contract(vec![component("a", Some("a.json"))], vec![]);
    let leaf = contract(vec![], vec![]);
    let linked = answer(input(&root, vec![file("a.json", "elsewhere.json", &leaf)])).0;
    assert!(
        refused(&linked).contains("link to elsewhere.json"),
        "{linked:?}"
    );
    for identity in ["", "/etc/a.json", "../a.json"] {
        let (state, usable) = answer(input(&root, vec![file("a.json", identity, &leaf)]));
        assert!(refused(&state).contains("Unsafe"), "{identity}: {state:?}");
        assert!(usable.is_none());
    }
}

#[test]
fn a_duplicate_reference_is_refused() {
    let root = contract(vec![component("a", Some("a.json"))], vec![]);
    let leaf = contract(vec![], vec![]);
    let sent = vec![
        file("a.json", "a.json", &leaf),
        file("./a.json", "a.json", &leaf),
    ];
    let state = answer(input(&root, sent)).0;
    assert!(
        refused(&state).contains("Duplicate inputs: a.json"),
        "{state:?}"
    );
}

#[test]
fn a_file_missing_after_it_was_asked_stays_missing_and_is_never_used() {
    let root = contract(
        vec![component("a", Some("a.json"))],
        vec![assignment("R", "a")],
    );
    let (state, rounds) = shell(&root, &BTreeMap::new());
    assert_eq!(rounds, 1, "{state:?}");
    assert!(
        matches!(&state, ContractState::Missing(paths) if paths == &["a.json"]),
        "{state:?}"
    );
    assert!(answer(input(&root, vec![])).1.is_none());
}

#[test]
fn changed_bytes_between_rounds_give_the_tree_of_the_last_bytes_or_a_named_error() {
    let root = contract(vec![component("a", Some("a.json"))], vec![]);
    let first = contract(vec![component("b", Some("b.json"))], vec![]);
    let leaf = contract(vec![], vec![]);
    let (state, _) = answer(input(&root, vec![file("a.json", "a.json", &first)]));
    assert!(matches!(&state, ContractState::Missing(paths) if paths == &["b.json"]));
    // Round 2: the shell changed a.json, which no longer mounts b.json.
    let sent = vec![
        file("a.json", "a.json", &leaf),
        file("b.json", "b.json", &leaf),
    ];
    let (state, usable) = answer(input(&root, sent));
    assert!(
        refused(&state).contains("Unmounted inputs: b.json"),
        "{state:?}"
    );
    assert!(usable.is_none());
}

#[test]
fn a_cycle_of_inside_references_is_refused() {
    let root = contract(vec![component("a", Some("a.json"))], vec![]);
    let back = contract(vec![component("b", Some("a.json"))], vec![]);
    let (state, _) = shell(&root, &BTreeMap::from([("a.json", back)]));
    assert!(refused(&state).contains("reference cycle"), "{state:?}");
    let to_root = contract(vec![component("b", Some(ROOT))], vec![]);
    let (state, _) = shell(&root, &BTreeMap::from([("a.json", to_root)]));
    assert!(refused(&state).contains("reference cycle"), "{state:?}");
}

/// A chain of `depth` mounts as the files of one request.
fn chain(depth: usize) -> ContractState {
    let names: Vec<String> = (0..depth).map(|level| format!("d/{level}.json")).collect();
    let files = (0..depth).map(|level| {
        let next = names.get(level + 1).map(String::as_str);
        let label = format!("c{level}");
        file(
            &names[level],
            &names[level],
            &contract(vec![component(&label, next)], vec![]),
        )
    });
    let root = contract(vec![component("r", Some("d/0.json"))], vec![]);
    answer(input(&root, files.collect())).0
}

#[test]
fn a_chain_at_the_depth_bound_assembles_and_one_level_deeper_is_too_deep() {
    assert!(matches!(chain(900), ContractState::Parsed(_)));
    let state = chain(901);
    assert!(
        refused(&state).contains("deeper than 900 levels"),
        "{state:?}"
    );
}

#[test]
fn three_thousand_mounts_are_asked_and_then_refused_by_their_count() {
    let names: Vec<String> = (0..3000).map(|index| format!("m/{index}.json")).collect();
    let components = names
        .iter()
        .enumerate()
        .map(|(index, name)| component(&format!("c{index}"), Some(name)))
        .collect();
    let root = contract(components, vec![]);
    let (state, _) = answer(input(&root, vec![]));
    assert!(matches!(&state, ContractState::Missing(paths) if paths.len() == 3000));
    let leaf = contract(vec![], vec![]);
    let sent = names.iter().map(|name| file(name, name, &leaf)).collect();
    let (state, usable) = answer(input(&root, sent));
    let expected = format!("3000 inside contracts; the core reads at most {MAX_INSIDE_FILES}");
    assert!(refused(&state).contains(&expected), "{state:?}");
    assert!(usable.is_none());
}

#[test]
fn more_bytes_than_the_bound_are_refused_before_any_parse() {
    let root = contract(vec![component("a", Some("a.json"))], vec![]);
    let large = vec![b' '; MAX_INSIDE_BYTES + 1];
    let (state, usable) = answer(input(&root, vec![file("a.json", "a.json", &large)]));
    assert!(
        refused(&state).contains("the core reads at most"),
        "{state:?}"
    );
    assert!(usable.is_none());
}

#[test]
fn an_invalid_inside_contract_or_an_invalid_root_is_refused() {
    let root = contract(vec![component("a", Some("a.json"))], vec![]);
    let state = answer(input(&root, vec![file("a.json", "a.json", b"{")])).0;
    assert!(
        refused(&state).starts_with("inside-contract tree: "),
        "{state:?}"
    );
    let state = answer(input(b"{", vec![])).0;
    assert!(!refused(&state).is_empty());
}

#[test]
fn a_uml_target_in_an_inside_contract_names_the_target_of_the_tree() {
    let root = contract(vec![component("a", Some("a.json"))], vec![]);
    let inside = json!({"schema_version": "3.14.0", "components": [], "rules": [],
        "declarations": {"uml": {"schema_version": "1.1.0"}}});
    let bytes = serde_json::to_vec(&inside).unwrap_or_default();
    let (state, usable) = answer(input(&root, vec![file("a.json", "a.json", &bytes)]));
    assert!(matches!(state, ContractState::Parsed(_)), "{state:?}");
    let reason = super::uml_reason(usable.as_ref(), ROOT);
    assert!(reason.is_some_and(|(id, _)| id == "UML-TARGET-a2e40c5592b1b06a"));
    let (_, plain) = answer(input(&contract(vec![component("a", None)], vec![]), vec![]));
    assert!(super::uml_reason(plain.as_ref(), ROOT).is_none());
}

#[test]
fn the_rules_of_a_tree_name_each_inside_rule_and_give_the_root_rules_their_input() {
    use crate::engine::{Answer, Engine};
    use crate::request::Request;
    use archkeel_model::{Input, Reason, Unsupported};
    let root = contract(
        vec![component("a", Some("a.json"))],
        vec![assignment("R", "a")],
    );
    let leaf = contract(vec![component("b", None)], vec![assignment("M", "b")]);
    let mut engine = Engine::default();
    let _ = engine.answer(Request::Contract(input(
        &root,
        vec![file("a.json", "a.json", &leaf)],
    )));
    let Answer::Rules(answer) = engine.answer(Request::Rules) else {
        assert_eq!("no rules answer", "a rules answer");
        return;
    };
    let inside = Reason::Unsupported(Unsupported::InsideRule);
    assert_eq!(answer.reasons.get("a:M"), Some(&inside));
    assert_eq!(
        answer.reasons.get("R"),
        Some(&Reason::MissingInput(Input::Reply))
    );
    assert!(answer.decided.is_empty());
}
