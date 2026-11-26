// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `merge`. The records of a selected call (`sel`) hold two numbers that are no ids (AD-1136).

use super::{load, merge};

/// One raw file: a string table of `size` names and the records.
fn raw(size: usize, records: &[&str]) -> String {
    let names: Vec<String> = (0..size).map(|n| format!("\"m{n}\"")).collect();
    let mut lines = vec![
        "{\"k\":\"build\"}".to_owned(),
        format!("{{\"k\":\"str\",\"v\":[{}]}}", names.join(",")),
    ];
    lines.extend(records.iter().map(|r| (*r).to_owned()));
    format!(
        "{}\n{{\"k\":\"end\",\"lines\":{}}}\n",
        lines.join("\n"),
        lines.len()
    )
}

const LIB_SITE: &str =
    "{\"k\":\"sel\",\"from\":0,\"to\":1,\"impl\":2,\"file\":3,\"line\":7,\"col\":28}";
const TEST_SITE: &str =
    "{\"k\":\"sel\",\"from\":0,\"to\":1,\"impl\":2,\"file\":3,\"line\":90,\"col\":4}";

#[test]
fn a_selected_call_keeps_its_line_and_its_column_through_the_merge() {
    // The column is larger than the string table: an id recode would turn it into null.
    let lib = raw(4, &[LIB_SITE]);
    let (_, records) = load(&merge(&lib, &[]).unwrap()).unwrap();
    let [record] = records.as_slice() else {
        return assert_eq!(records.len(), 1);
    };
    assert!(record.contains("\"col\":28"), "{record}");
    assert!(record.contains("\"line\":7"), "{record}");
    // The merge writes ids again: the reader of the worker takes the same site.
    let again = load(&merge(&lib, &[&lib]).unwrap()).unwrap().1;
    assert_eq!(again, records);
}

#[test]
fn a_selected_call_of_a_test_unit_is_not_merged_into_the_library() {
    let lib = raw(4, &[LIB_SITE]);
    let test = raw(4, &[LIB_SITE, TEST_SITE]);
    let (_, records) = load(&merge(&lib, &[&test]).unwrap()).unwrap();
    assert_eq!(records.len(), 1, "{records:?}");
    assert!(
        records.iter().all(|r| r.contains("\"line\":7")),
        "{records:?}"
    );
}
