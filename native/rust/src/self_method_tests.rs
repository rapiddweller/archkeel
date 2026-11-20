// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::Status;
use archkeel_facts::{CallFact, SymbolFact};

use crate::collect::tests::run;

#[test]
fn plain_self_needs_the_exact_inherent_receiver() {
    let result = run(
        &[
            (
                "crates/Cargo.toml",
                "[package]\nname = \"app\"\nedition = \"2021\"\n",
            ),
            (
                "crates/src/lib.rs",
                r"
                struct Ticket;
                trait Shared { fn release(self) -> bool; }
                impl Shared for &Ticket { fn release(self) -> bool { false } }
                trait Mutable { fn adjusted(&mut self) -> bool; }
                impl Mutable for Ticket {
                    fn adjusted(&mut self) -> bool { self.release() }
                }
                impl Ticket {
                    fn exact(&self) -> bool { self.release() }
                    fn release(&self) -> bool { true }
                    fn adjusted(&self) -> bool { false }
                    fn opposite(&mut self) -> bool { self.adjusted() }
                    fn borrowed(&self) -> bool { (&self).release() }
                    fn late(&self) -> bool { (|| self.release())() }
                    fn aliased(&self) -> bool {
                        let other = self;
                        other.release()
                    }
                    fn shadowed(&self) -> bool {
                        fn release() -> bool { false }
                        let _ = release();
                        self.release()
                    }
                    fn configured(&self) -> bool {
                        #[cfg(unix)]
                        { return self.release(); }
                        #[cfg(not(unix))]
                        { false }
                    }
                }
                ",
            ),
        ],
        false,
    );
    let method = |name: &str| {
        result
            .symbols
            .iter()
            .find(|row| matches!(&row.data, SymbolFact::Method(data) if data.qualified_name == format!("ns.app.Ticket.{name}")))
    };
    let source = method("exact").expect("source method");
    let target = method("release").expect("target method");
    let calls: Vec<_> = result
        .calls
        .iter()
        .filter_map(|row| match &row.data {
            CallFact::Calls(call) => Some(call),
            _ => None,
        })
        .collect();
    let linked: Vec<_> = calls
        .iter()
        .filter(|call| call.status == Status::Resolved)
        .collect();
    assert_eq!(linked.len(), 1, "{calls:#?}");
    let call = linked[0];
    assert_eq!(call.targets, ["ns.app.Ticket.release"]);
    assert_eq!(
        call.source_definition_id,
        Nullable::Value(source.id.clone())
    );
    assert_eq!(
        call.target_evidence_ids.as_ref(),
        Some(&target.evidence_ids)
    );
    assert_eq!(
        calls
            .iter()
            .filter(|call| call.expression == "release")
            .count(),
        8,
        "{calls:#?}"
    );
    assert!(calls
        .iter()
        .any(|call| call.expression == "adjusted" && call.status == Status::Unresolved));
}
