// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The phase timings of a scan request (#659): asked for, they leave the frame as it is, and they
// are positive times that sum to no more than the time of the scan in the core.

use std::cell::Cell;
use std::time::Duration;

use super::*;

#[test]
fn a_scan_gives_its_phases_only_when_asked_and_the_frame_does_not_change() {
    let root = repository("timings");
    let mut asked = request(&root);
    let plain = answer(asked.to_string().as_bytes()).unwrap();
    assert!(!plain.timings_asked);
    asked["timings"] = serde_json::json!(true);
    let timed = answer(asked.to_string().as_bytes()).unwrap();
    assert_eq!(timed.frame, plain.frame);
    assert!(timed.timings_asked);
    let phases = timed.timings.expect("the scan was measured");
    let parts = [
        phases.prepare,
        phases.collect,
        phases.validate,
        phases.evaluate,
        phases.render,
    ];
    assert!(parts.iter().all(|time| *time > Duration::ZERO));
    assert_eq!(phases.join, Duration::ZERO);
    assert!(parts.iter().sum::<Duration>() <= phases.wall);
}

#[test]
fn a_scan_without_timings_does_not_read_the_clock() {
    let root = repository("no-clock");
    let input = request(&root).to_string();
    let calls = Cell::new(0);
    let now = || {
        calls.set(calls.get() + 1);
        Duration::from_millis(calls.get())
    };
    let answer = crate::scan::answer(input.as_bytes(), &now).unwrap();
    assert!(!answer.timings_asked);
    assert_eq!(calls.get(), 0);
}

#[test]
fn a_refused_scan_has_no_phases_but_the_request_still_asked() {
    let root = repository("timings-refused");
    let mut asked = request(&root);
    asked["config"] = serde_json::json!("missing.toml");
    asked["timings"] = serde_json::json!(true);
    let refused = answer(asked.to_string().as_bytes()).unwrap();
    assert!(refused.names_a_gap && refused.timings_asked && refused.timings.is_none());
}
