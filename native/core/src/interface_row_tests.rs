// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_eval::{Cited, Violation};
use serde_json::json;

#[test]
fn an_interface_failure_keeps_its_import_evidence_and_components() {
    let violation = Violation::PrivateImport {
        id: "VIO".into(),
        rule: "INTERFACE".into(),
        cited: Cited {
            import: "IMP".into(),
            source_module: "app.client".into(),
            target_module: "app.api".into(),
            evidence: vec!["EVIDENCE".into()],
        },
        symbol: Some("_hidden".into()),
        source_component: "client".into(),
        target_component: "service".into(),
    };
    let row = super::row(&violation);
    assert_eq!(row["area"], "api_surface");
    assert_eq!(row["kind"], "interface_boundary");
    assert_eq!(row["subjects"], json!(["app.api._hidden", "app.client"]));
    assert_eq!(row["fact_ids"], json!(["IMP"]));
    assert_eq!(row["evidence_ids"], json!(["EVIDENCE"]));
    assert_eq!(
        row["data"],
        json!({"source_module": "app.client", "target_module": "app.api",
        "symbol": "_hidden", "source_component": "client", "target_component": "service"})
    );
}
