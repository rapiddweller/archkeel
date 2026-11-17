// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the reason of a `boundary_types` gap row in the frame. A lazy class annotation names
// what the user can do (#1523).

use super::{GapCause, GapRow};

#[test]
fn a_lazy_class_namespace_row_names_the_three_remedies() {
    let row = GapRow {
        subject: "app.api.Box.f:x".to_owned(),
        cause: GapCause::LazyClassNamespace,
        text: "object".to_owned(),
    };
    let reason = row.reason();
    assert!(
        reason.starts_with("lazy_class_namespace: object ("),
        "{reason}"
    );
    for remedy in [
        "narrow the version range of the project",
        "make the annotations strings",
        "remove the namespace write",
    ] {
        assert!(reason.contains(remedy), "{reason}");
    }
    let plain = GapRow {
        cause: GapCause::UnresolvedName,
        ..row
    };
    assert_eq!(plain.reason(), "unresolved_name: object");
}
