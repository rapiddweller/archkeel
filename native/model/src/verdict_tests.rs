// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A PASS has no reason, so an unsupported reason cannot ride on a PASS, and an UNKNOWN always
//! has a reason with a text (review M6, M9 of #1090). The ruling of the report checks both again.

use super::{Decision, Verdict};
use crate::reason::{Input, Reason, Unsupported};

#[test]
fn a_pass_has_no_reason_and_an_unknown_has_a_reason_with_a_text() {
    let pass = Decision::passed("R".to_owned(), 1);
    assert!(matches!(pass.verdict(), Verdict::Pass(_)));
    assert_eq!(pass.reason(), None);
    assert_eq!(Decision::fail().reason(), None);
    for reason in [
        Reason::Unsupported(Unsupported::Baseline),
        Reason::MissingInput(Input::Reply),
        Reason::NoSubjects,
        Reason::UncitedChild("a".to_owned()),
        Reason::TooManyRows("modules"),
    ] {
        let unknown = Decision::unknown(reason.clone());
        assert_eq!(unknown.reason(), Some(&reason));
        assert!(!reason.to_string().is_empty(), "{reason:?}");
    }
}
