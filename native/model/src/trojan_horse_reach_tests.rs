// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The words of the trojan horse reach rows (AD-664). The matching itself is planted end to end in
// `eval/src/trojan_horse_reach_tests.rs` and in the CLI plants.

use archkeel_facts::data::{GapEffect, TrojanHorseForm};

use super::{Applied, TrojanHorseProblem};

#[test]
fn each_problem_has_its_code_and_says_that_it_is_not_applied() {
    let problems = [
        (
            TrojanHorseProblem::Unmatched,
            "trojan_horse_reach.unmatched",
        ),
        (
            TrojanHorseProblem::Ambiguous(2),
            "trojan_horse_reach.ambiguous",
        ),
        (
            TrojanHorseProblem::Repeated(vec!["D-2".to_owned()]),
            "trojan_horse_reach.repeated",
        ),
        (TrojanHorseProblem::Form, "trojan_horse_reach.invalid"),
        (
            TrojanHorseProblem::ChangesOutside("os".to_owned()),
            "trojan_horse_reach.invalid",
        ),
        (
            TrojanHorseProblem::LoadsNothing("p.x".to_owned()),
            "trojan_horse_reach.invalid",
        ),
        (
            TrojanHorseProblem::Exported(vec!["p.b".to_owned()]),
            "trojan_horse_reach.invalid",
        ),
        (
            TrojanHorseProblem::Unresolved(3),
            "trojan_horse_reach.invalid",
        ),
    ];
    for (problem, code) in problems {
        assert_eq!(problem.code(), code, "{problem:?}");
        assert!(problem.text().contains("not applied"), "{problem:?}");
    }
    assert!(TrojanHorseProblem::Form
        .text()
        .contains("eval, exec, compile"));
}

#[test]
fn an_applied_declaration_names_its_site() {
    let applied = Applied {
        id: "D-1".to_owned(),
        rationale: "The text is a formula of numbers.".to_owned(),
        gap: "UNKNOWN-1".to_owned(),
        module: "p.a".to_owned(),
        form: Some(TrojanHorseForm::Loader),
        label: "loader".to_owned(),
        line: 12,
        loads: Vec::new(),
        constant: None,
        edges: Vec::new(),
        changes: Vec::new(),
        covered: Vec::new(),
        effect: None,
        stated: GapEffect::EveryModule,
    };
    assert_eq!(applied.site(), "D-1 (p.a:12 loader)");
}
