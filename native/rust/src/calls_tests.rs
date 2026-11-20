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

#[test]
fn relative_module_calls_need_one_unshadowed_binding() {
    let result = run(
        &[
            (
                "crates/Cargo.toml",
                "[package]\nname = \"app\"\nedition = \"2021\"\n",
            ),
            (
                "crates/src/lib.rs",
                r"
                mod sibling;
                use crate::sibling as alias;

                fn block_shadow() {
                    use crate::other as sibling;
                    sibling::finish();
                }

                fn same_targets() {
                    sibling::finish();
                    crate::sibling::finish();
                    alias::finish();
                }

                mod other {
                    pub(crate) fn finish() {}
                }

                mod nested {
                    mod sibling {
                        pub(super) fn finish() {}
                    }

                    fn shadowed() {
                        use crate::other as sibling;
                        sibling::finish();
                    }
                }

                #[allow(non_camel_case_types)]
                fn generic<sibling: Dispatch>() {
                    sibling::finish();
                }

                trait Dispatch {
                    fn finish();
                }

                mod conflict {
                    mod second {
                        pub(super) fn finish() {}
                    }

                    macro_rules! second { () => {} }

                    fn call() {
                        second::finish();
                    }
                }

                #[cfg(unix)]
                mod conditional {
                    pub(super) fn finish() {}
                }

                #[cfg(not(unix))]
                mod conditional {
                    pub(super) fn finish() {}
                }

                #[cfg(unix)]
                use self::conditional as maybe;
                #[cfg(not(unix))]
                use self::other as maybe;

                fn platform() {
                    conditional::finish();
                    maybe::finish();
                }
                ",
            ),
            ("crates/src/sibling.rs", "pub(crate) fn finish() {}"),
        ],
        false,
    );
    let calls: Vec<_> = result
        .calls
        .iter()
        .filter_map(|row| match &row.data {
            CallFact::Calls(call) => Some(call),
            _ => None,
        })
        .collect();
    assert_eq!(calls.len(), 9);
    let expected = calls
        .iter()
        .find(|call| call.expression == "crate::sibling::finish")
        .and_then(|call| call.target_evidence_ids.clone())
        .expect("the rooted call proves a target");
    for call in calls {
        if call.source_scope.ends_with(".same_targets") {
            assert_eq!(call.status, Status::Resolved, "{}", call.expression);
            assert_eq!(call.targets, ["ns.app.sibling.finish"]);
            assert_eq!(call.target_evidence_ids.as_ref(), Some(&expected));
        } else {
            assert_eq!(
                call.status,
                Status::Unresolved,
                "{} in {}",
                call.expression,
                call.source_scope
            );
            assert!(call.targets.is_empty());
        }
    }
}
