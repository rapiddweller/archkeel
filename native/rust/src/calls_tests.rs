// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_facts::data::CallData;
use archkeel_facts::vocab::Status;
use archkeel_facts::CallFact;

use crate::collect::tests::run;

#[test]
fn lexical_and_conditional_calls_do_not_get_targets() {
    let result = run(
        &[
            ("crates/Cargo.toml", "[package]\nname = \"app\"\n"),
            (
                "crates/src/lib.rs",
                r"
                fn local() {}
                use crate::local as alias;
                #[cfg(unix)]
                fn conditional() {}
                #[cfg(not(unix))]
                fn conditional() {}

                fn exact() {
                    local();
                    alias();
                    crate::local();
                }

                fn shadowed(local: fn()) {
                    local();
                    self::local();
                }

                fn block_import() {
                    use crate::local as alias;
                    alias();
                }

                fn cfg_call() {
                    conditional();
                    #[cfg(unix)]
                    crate::local();
                }

                fn indirect(callback: fn() -> fn()) {
                    callback()();
                    let _ = || crate::local();
                    let _ = String::new().len();
                    stringify!(local());
                }
                ",
            ),
        ],
        false,
    );
    let calls: Vec<&CallData> = result
        .calls
        .iter()
        .filter_map(|row| match &row.data {
            CallFact::Calls(call) => Some(call),
            _ => None,
        })
        .collect();
    let resolved: Vec<_> = calls
        .iter()
        .filter(|call| call.status == Status::Resolved)
        .collect();
    assert_eq!(resolved.len(), 4, "{calls:#?}");
    for call in resolved {
        assert_eq!(call.targets, ["ns.app.local"]);
        assert!(call.target_evidence_ids.is_some());
    }
    let unresolved: Vec<_> = calls
        .iter()
        .filter(|call| call.status == Status::Unresolved)
        .collect();
    assert_eq!(unresolved.len(), 10);
    for call in unresolved {
        assert!(call.targets.is_empty());
        assert!(call.reason.is_some());
    }
    assert!(calls.iter().any(|call| call.expression == "stringify!"
        && call.reason.as_deref() == Some("Macro expansion can contain calls that are not read")));
}
