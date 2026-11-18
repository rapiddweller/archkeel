// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The timings line of the phases of a scan (#659, AD-878).

use std::time::Duration;

use serde_json::Value;

use super::Phases;

fn each(seconds: u64) -> Phases {
    let time = Duration::from_secs(seconds);
    Phases {
        prepare: time,
        collect: time,
        validate: time,
        evaluate: time,
        render: time,
        join: time,
        wall: time * 7,
    }
}

#[test]
fn evaluation_and_render_use_their_own_boundaries() {
    let phases = Phases::evaluation(
        Some(Duration::from_secs(2)),
        Some(Duration::from_secs(5)),
        Some(Duration::from_secs(9)),
    );
    assert_eq!(phases.evaluate, Duration::from_secs(3));
    assert_eq!(phases.render, Duration::from_secs(4));
    let untimed = Phases::evaluation(None, None, None);
    assert_eq!(untimed.evaluate, Duration::ZERO);
    assert_eq!(untimed.render, Duration::ZERO);
}

#[test]
fn the_timings_line_is_one_json_document_with_the_phases_in_the_order_of_the_run() {
    let line = Phases::line(&each(2));
    let document: Value = serde_json::from_str(&line).unwrap();
    assert_eq!(document["protocol"], "archkeel-core-timings-1");
    assert_eq!(document["clock"], "monotonic");
    assert_eq!(document["unit"], "seconds");
    assert_eq!(document["core_seconds"], 14.0);
    let names: Vec<&str> = document["phases"]
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(
        names,
        ["prepare", "collect", "validate", "evaluate", "render", "join"]
    );
    assert!(line.find("prepare") < line.find("render"));
}

#[test]
fn the_phases_of_the_parts_of_a_system_run_are_summed() {
    let sum = Phases::plus(each(1), each(2));
    assert_eq!(sum.collect, Duration::from_secs(3));
    assert_eq!(sum.join, Duration::from_secs(3));
    assert_eq!(sum.wall, Duration::from_secs(21));
}
