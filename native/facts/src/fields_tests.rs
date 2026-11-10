// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the store. Before AD-346 moved to typed access, it read these fields from the wire
// JSON of each record. Each field here must equal the wire value of the same key.

use serde_json::Value;

use super::*;
use crate::ids::FactId;
use crate::ids::PackageName;
use crate::record::{FactData, Record};
use crate::sections::GapFact;

fn wire(gap: &GapFact) -> Value {
    let record = Record::unknown(FactId::new("UNKNOWN-1"), "why", None, "", gap.clone());
    serde_json::to_value(&record).unwrap()["data"].clone()
}

#[test]
fn a_gap_gives_the_module_the_dimension_and_nothing_else() {
    let gap = GapFact::resolution("why", "ns.mod");
    let fields = gap.fields();
    let value = wire(&gap);
    assert_eq!(fields.module, Some(value["module"].as_str()));
    assert_eq!(
        fields.resolution_dimension,
        value["resolution_dimension"].as_str()
    );
    assert_eq!(fields.source_module, None);
    assert_eq!(fields.file, None);
    let mut data = GapData::at("why", "ns.mod");
    data.source_module = Some(ModuleName::new("other"));
    let other = GapFact::SourceResolutionGap(data);
    assert_eq!(other.fields().source_module, Some(Some("other")));
}

#[test]
fn an_import_gives_its_four_names() {
    let mut data = ImportData::statement();
    data.source_module = ModuleName::new("a");
    data.target_package = PackageName::new("p");
    let fields = data.fields();
    let value = serde_json::to_value(&data).unwrap();
    assert_eq!(fields.source_module, Some(value["source_module"].as_str()));
    assert_eq!(fields.source_package, value["source_package"].as_str());
    assert_eq!(fields.target_module, value["target_module"].as_str());
    assert_eq!(fields.target_package, value["target_package"].as_str());
    assert_eq!(fields.owner, None);
}
