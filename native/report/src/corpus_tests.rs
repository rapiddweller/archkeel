// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The payloads of the Python oracle producer (#1040): each decodes, passes the check, encodes
//! to the same bytes, and the status rule gives its stated status.

use std::path::PathBuf;

use crate::head::Status;
use crate::payload::Payload;
use crate::report::Report;
use crate::status::status_of;

pub(crate) fn bytes(name: &str) -> Vec<u8> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("testdata")
        .join(format!("{name}.report-v2.json"));
    std::fs::read(&path).unwrap()
}

/// The test payloads that state PASS and FAIL; the others state UNKNOWN.
const PASS: [&str; 3] = ["F-architecture-tests", "H-uml-dart", "python-stdlib-demo"];
const FAIL: [&str; 7] = [
    "python-newer-syntax-demo",
    "variant-complete-assignment",
    "variant-decision-conflict",
    "variant-forbidden-dependency-pair",
    "variant-no-component-cycles-module",
    "variant-package-cycle-backed",
    "variant-package-cycle-rollup-only",
];
const UNKNOWN: [&str; 8] = [
    "E-runtime",
    "F-typescript-story",
    "G-dart",
    "H-typescript",
    "L-nest-realworld",
    "explore-N-explore",
    "golden-synthetic-excluded-tests",
    "planned-component",
];

/// Each test payload and the status that it states.
pub(crate) fn corpus() -> Vec<(&'static str, Status)> {
    let pass = PASS.iter().map(|name| (*name, Status::Pass));
    let fail = FAIL.iter().map(|name| (*name, Status::Fail));
    let unknown = UNKNOWN.iter().map(|name| (*name, Status::Unknown));
    pass.chain(fail).chain(unknown).collect()
}

#[test]
fn each_oracle_payload_round_trips_byte_for_byte() {
    for (name, _) in corpus() {
        let original = bytes(name);
        let payload = Payload::decode(&original)
            .map_err(|e| format!("{name}: {e}"))
            .unwrap();
        assert_eq!(payload.encode().unwrap(), original, "{name}");
    }
}

#[test]
fn each_oracle_payload_passes_the_check_and_its_status_follows_the_rule() {
    for (name, stated) in corpus() {
        let report = Report::read(&bytes(name))
            .map_err(|e| format!("{name}: {e}"))
            .unwrap();
        assert_eq!(report.payload().summary.status, stated, "{name}");
        assert_eq!(status_of(report.payload()), stated, "{name}");
        assert_eq!(report.encode().unwrap(), bytes(name), "{name}");
    }
}

#[test]
fn the_corpus_holds_each_kind_of_run() {
    let payloads: Vec<Payload> = corpus()
        .iter()
        .map(|(name, _)| Payload::decode(&bytes(name)).unwrap())
        .collect();
    let any = |test: &dyn Fn(&Payload) -> bool| payloads.iter().any(test);
    assert!(any(&|p| !p.run.target));
    assert!(any(&|p| p.run.observation != Status::Pass));
    assert!(any(&|p| p.summary.counts.cycles > 0));
    assert!(any(&|p| p.run.not_ranked.iter().any(|n| n.count > 0)));
    assert!(any(&|p| p.summary.counts.violations > 1));
    assert!(any(&|p| p.summary.counts.undecided > 0));
    assert!(any(&|p| !p.permissions.status.is_empty()));
    assert!(any(
        &|p| p.summary.status == Status::Pass && !p.unknowns.source.is_empty()
    ));
}
