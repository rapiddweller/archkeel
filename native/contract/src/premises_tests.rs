// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `declarations.premises` (contract 3.17.0, AD-764), the opt-in premises of a contract.

use super::{assumption_words, PremiseName};
use crate::contract::parse_file;
use crate::document::Contract;

fn contract(version: &str, premises: &str) -> String {
    format!(
        r#"{{"schema_version": "{version}", "components": [], "rules": [],
        "declarations": {{"premises": [{premises}]}}}}"#
    )
}

const STDLIB: &str = r#"{"id": "P-1", "name": "standard_library_unchanged",
    "rationale": "No code of the project patches the standard library.", "provenance": ["d.md"]}"#;

fn read(text: &str) -> Result<Contract, String> {
    parse_file(text.as_bytes()).map_err(|error| error.message)
}

#[test]
fn a_declared_premise_parses_with_its_name_and_reason() -> Result<(), String> {
    let parsed = read(&contract("3.17.0", STDLIB))?;
    let declarations = parsed.declarations().as_ref().ok_or("declarations")?;
    let [premise] = declarations.premises().as_slice() else {
        return Err("one premise".to_owned());
    };
    assert_eq!(*premise.name(), PremiseName::StandardLibraryUnchanged);
    assert_eq!(premise.id().as_text(), "P-1");
    assert!(premise.rationale().contains("patches"));
    assert_eq!(
        assumption_words(*premise.name()),
        "the premise that outside code leaves the standard library unchanged"
    );
    Ok(())
}

#[test]
fn an_unknown_name_an_old_version_and_a_repeated_name_refuse_the_contract() {
    let unknown = STDLIB.replace("standard_library_unchanged", "network_is_up");
    let twice = format!("{STDLIB}, {}", STDLIB.replace("P-1", "P-2"));
    for (text, word) in [
        (
            contract("3.17.0", &unknown),
            "names no premise that the core knows",
        ),
        (contract("3.16.0", STDLIB), "3.17.0"),
        (contract("3.17.0", &twice), "repeats a name"),
        (
            contract(
                "3.17.0",
                r#"{"id": "P-1", "name": "standard_library_unchanged"}"#,
            ),
            "premises[0] fields mismatch",
        ),
    ] {
        let found = read(&text).err().unwrap_or_default();
        assert!(found.contains(word), "{word}: {found}");
    }
}
