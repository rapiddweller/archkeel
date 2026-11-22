// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The words of the door reach rows (AD-664). The matching itself is planted end to end in
// `eval/src/door_reach_tests.rs` and in the CLI plants.

use archkeel_facts::data::{DoorForm, GapEffect};

use super::{Applied, DoorProblem};

#[test]
fn each_problem_has_its_code_and_says_that_it_is_not_applied() {
    let problems = [
        (DoorProblem::Unmatched, "door_reach.unmatched"),
        (DoorProblem::Ambiguous(2), "door_reach.ambiguous"),
        (
            DoorProblem::Repeated(vec!["D-2".to_owned()]),
            "door_reach.repeated",
        ),
        (DoorProblem::Form, "door_reach.invalid"),
        (
            DoorProblem::ChangesOutside("os".to_owned()),
            "door_reach.invalid",
        ),
        (
            DoorProblem::LoadsNothing("p.x".to_owned()),
            "door_reach.invalid",
        ),
        (
            DoorProblem::Exported(vec!["p.b".to_owned()]),
            "door_reach.invalid",
        ),
        (DoorProblem::Unresolved(3), "door_reach.invalid"),
    ];
    for (problem, code) in problems {
        assert_eq!(problem.code(), code, "{problem:?}");
        assert!(problem.text().contains("not applied"), "{problem:?}");
    }
    assert!(DoorProblem::Form.text().contains("eval, exec, compile"));
}

#[test]
fn an_applied_declaration_names_its_site() {
    let applied = Applied {
        id: "D-1".to_owned(),
        rationale: "The text is a formula of numbers.".to_owned(),
        gap: "UNKNOWN-1".to_owned(),
        module: "p.a".to_owned(),
        form: DoorForm::Loader,
        line: 12,
        loads: Vec::new(),
        constant: None,
        possible_loads: Vec::new(),
        changes: Vec::new(),
        effect: None,
        stated: GapEffect::EveryModule,
    };
    assert_eq!(applied.site(), "D-1 (p.a:12 loader)");
}
