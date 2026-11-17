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

// #1352, AD-794: up to one screen of components the first view shows them as they are; more are
// split by the prefix that their names share, and each group says why.
#[test]
fn one_screen_of_components_is_not_grouped_and_a_group_of_more_says_why() {
    let first_level = |size: usize| -> Vec<Value> {
        let mut topology = components(size, &[(0, 1)]);
        for (i, c) in topology["components"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .enumerate()
        {
            c["name"] = json!(format!("svc{:02}_part{}", i / 10, i % 10));
        }
        let data = payload(&document(&json!({"status": "PASS", "topology": topology})));
        data["atlas"]["components"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|c| c["parent_id"].is_null())
            .cloned()
            .collect()
    };
    let screen = first_level(30);
    assert_eq!(screen.len(), 30);
    assert!(screen
        .iter()
        .all(|c| !c["id"].as_str().unwrap().starts_with("GROUP:")));
    let more = first_level(31);
    let (groups, single): (Vec<Value>, Vec<Value>) = more
        .into_iter()
        .partition(|c| c["id"].as_str().unwrap().starts_with("GROUP:"));
    // `svc03_part0` shares its prefix with no other box: it stays a box, not a group of one.
    assert_eq!((groups.len(), single.len()), (3, 1));
    for group in groups {
        let why = group["responsibilities"][0].as_str().unwrap();
        assert!(
            why.contains("Grouped by the name prefix `svc0")
                && why.contains("this level has 31 boxes, more than one screen shows (30)"),
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

// #1764, #1765, #1767: each NEXT link has its own target and purpose, and the page can be skipped.
#[test]
fn each_next_link_goes_to_its_own_cause_and_names_its_place() {
    let frame = json!({"status": "UNKNOWN",
        "rules": {"A": ["k", "UNKNOWN"], "B": ["k", "UNKNOWN"], "C": ["k", "UNKNOWN"]},
        "explain": {"holds": {"rules": {
            "A": {"kind": "pair_gaps", "total": 7, "pairs": [{"source": "app.a", "target": "app.b"}]},
            "B": {"kind": "pair_gaps", "total": 7},
            "C": {"kind": "pair_gaps", "total": 3, "pairs": [{"source": "app.c", "target": "app.d"}]}}}}});
    let page = document(&frame);
    for (rules, total) in [("2 unknown rules", 7), ("1 unknown rule", 3)] {
        let link = format!(
            "<a href=\"#cause-pair_gaps-{total}\" aria-label=\"Causes of {rules}\">Causes</a>"
        );
        assert!(page.contains(&link), "{link}");
        assert!(page.contains(&format!(
            "<article class=\"rp-cause\" id=\"cause-pair_gaps-{total}\">"
        )));
        assert!(
            page.contains(&format!("Which pairs: {total} gap")),
            "{total}"
        );
    }
    assert!(page.contains("<a class=\"ak-skip\" href=\"#result\">Skip to the result</a>"));
    assert!(page.contains("<main class=\"rp-main report-shell\" id=\"result\" tabindex=\"-1\">"));
    let failed = document(&dependency_frame(3));
    assert!(
        failed.contains("<a href=\"#x1\" aria-label=\"Violated place 1\">1</a>"),
        "evidence"
    );
}
