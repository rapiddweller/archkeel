// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_model::{Input, Reason};

use crate::ruling::RunScope;

#[test]
fn the_scope_of_a_run_writes_the_word_complete_or_the_text_of_its_reason() {
    assert_eq!(
        serde_json::to_string(&RunScope::Complete).unwrap(),
        "\"complete\""
    );
    let reason = Reason::MissingInput(Input::Reply);
    let open = RunScope::Open(reason.clone());
    assert_eq!(
        serde_json::to_string(&open).unwrap(),
        serde_json::to_string(&reason.to_string()).unwrap()
    );
    assert_eq!(open.word(), reason.to_string());
    assert_ne!(open, RunScope::Complete);
}
