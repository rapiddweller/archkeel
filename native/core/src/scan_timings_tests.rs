// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The phase timings of a scan request (#659): asked for, they leave the frame as it is, and they
// are finite times that sum to no more than the time of the scan.

use std::time::Duration;

use super::*;

#[test]
fn a_scan_gives_its_phases_only_when_asked_and_the_frame_does_not_change() {
    let root = repository("timings");
    let mut asked = request(&root);
    let plain = answer(asked.to_string().as_bytes()).unwrap();
    assert!(plain.timings.is_none());
    asked["timings"] = serde_json::json!(true);
    let timed = answer(asked.to_string().as_bytes()).unwrap();
    assert_eq!(timed.frame, plain.frame);
    let phases = timed.timings.expect("the request asked for the phases");
    let parts = [
        phases.prepare,
        phases.collect,
        phases.validate,
        phases.evaluate,
        phases.render,
    ];
    assert!(parts.iter().all(|time| *time > Duration::ZERO));
    assert!(parts.iter().sum::<Duration>() <= phases.wall);
}
