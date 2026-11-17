// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The second UX test (AD-652): a capped list names both numbers, a group says why it is one, a
// drafted text is shown as not written yet, an empty Target says so, and NEXT names the jobs.

use super::*;

// #1349: 337 places, the list shows 100. The card and the architecture line count all of them.
#[test]
fn a_capped_list_and_the_counts_beside_it_state_both_numbers() {
    let page = document(&dependency_frame(337));
    assert!(page.contains("337 places in the code"));
    // 336 of the 337 places have a module of no component (`app.a0` is owned).
    assert!(
        page.contains("336 violations outside any component"),
        "{}",
        page.len()
    );
    assert!(page.contains("The list shows 100 of 337 violated places."));
    assert!(page.contains("The page shows 100 of 337 places."));
}

// #1352: up to twelve components the first view shows them as they are; more are split, and each
// group says why.
#[test]
fn twelve_components_are_not_grouped_and_a_group_of_more_says_why() {
    let first_level = |size: usize| -> Vec<Value> {
        let data = payload(&document(
            &json!({"status": "PASS", "topology": components(size, &[(0, 1)])}),
        ));
        data["atlas"]["components"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|c| c["parent_id"].is_null())
            .cloned()
            .collect()
    };
    let twelve = first_level(12);
    assert_eq!(twelve.len(), 12);
    assert!(twelve
        .iter()
        .all(|c| !c["id"].as_str().unwrap().starts_with("GROUP:")));
    let thirteen = first_level(13);
    assert!(
        thirteen.len() < 13
            && thirteen
                .iter()
                .all(|c| c["id"].as_str().unwrap().starts_with("GROUP:"))
    );
    for group in thirteen {
        let why = group["responsibilities"][0].as_str().unwrap();
        assert!(
            why.contains("this level has 13 boxes, more than 12"),
            "{why}"
        );
    }
}

// #1352: `init` drafts the word TODO; the page says that nobody has written the text yet.
#[test]
fn a_drafted_responsibility_reads_as_not_written_yet() {
    let mut topology = components(2, &[(0, 1)]);
    topology["components"][0]["responsibilities"] = json!(["TODO"]);
    topology["components"][1]["responsibilities"] = json!(["Reads the files."]);
    let frame = json!({"status": "UNKNOWN", "topology": topology});
    let page = document(&frame);
    let data = payload(&page);
    let said: Vec<String> = data["atlas"]["components"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| c["responsibilities"][0].as_str().unwrap().to_owned())
        .collect();
    assert_eq!(
        said,
        ["Responsibility not written yet.", "Reads the files."]
    );
    assert!(!data.to_string().contains("TODO"));
    // NEXT names the job with its count.
    let next = page
        .split("id=\"next\"")
        .nth(1)
        .unwrap()
        .split("</ol>")
        .next()
        .unwrap();
    assert!(
        next.contains("Write the responsibility of 1 component"),
        "{next}"
    );
}

// #1352: a contract with no dependency gives Target and Diff one line, with the open decisions.
#[test]
fn an_empty_target_says_what_is_missing() {
    let frame = json!({"status": "UNKNOWN", "topology": components(3, &[(0, 1)]),
        "unsupported": {"rules": {"hygiene:decision.open:r": "contract hygiene decision.open: rules 72 open dependency decisions: undecided."}}});
    let data = payload(&document(&frame));
    assert_eq!(
        data["atlas"]["declared_note"],
        json!("The contract declares no dependencies yet: 72 open dependency decisions.")
    );
    // A contract that declares a dependency has no such line.
    let mut declared = components(3, &[(0, 1)]);
    declared["requires"] = json!([{"source": "COMP-0", "target": "COMP-1", "imports": 2}]);
    let data = payload(&document(&json!({"status": "PASS", "topology": declared})));
    assert!(data["atlas"]["declared_note"].is_null());
}

// The verdict and the next steps are one block: the steps sit inside the card, no panel is empty.
#[test]
fn the_next_steps_are_inside_the_verdict_card() {
    let page = document(&json!({"status": "UNKNOWN", "rules": {"A": ["k", "UNKNOWN"]}}));
    let card = page
        .split("aria-label=\"Verdict\">")
        .nth(1)
        .unwrap()
        .split("</section></div>")
        .next()
        .unwrap();
    assert!(card.contains("class=\"rp-next\""), "{card}");
    assert!(card.contains("ak-verdict__stats"));
    assert_eq!(page.matches("class=\"rp-next\"").count(), 1);
}

// The detail fold of an Unknown card is offered only when it adds to the title.
#[test]
fn the_core_detail_is_offered_only_when_it_adds_to_the_title() {
    let same = document(
        &json!({"status": "UNKNOWN", "rules": {"D": ["k", "UNKNOWN"]},
        "explained": {"D": "short reason"}}),
    );
    assert!(
        !same.contains("What the core says"),
        "the text equals the title"
    );
    let long = "a long reason that goes on and on about nothing of use to anybody ".repeat(6);
    let more = document(
        &json!({"status": "UNKNOWN", "rules": {"D": ["k", "UNKNOWN"]},
        "explained": {"D": long}}),
    );
    assert!(
        more.contains("What the core says"),
        "the title is cut: the fold has the rest"
    );
}

// The architecture line says what it counts in plain words: a violation, an open gap, and a
// violation outside any component with the reason (the module has no owner in the contract).
#[test]
fn the_architecture_line_is_plain() {
    let page = document(&dependency_frame(5));
    assert!(page.contains("with a violation, "), "{page}");
    assert!(page.contains("with an open gap."));
    assert!(page.contains("outside any component (the module has no owner in the contract)"));
    assert!(!page.contains("with a violated place"));
    assert!(!page.contains("in no component: assign"));
}
