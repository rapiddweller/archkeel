// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A door site as typed data (AD-664).
//!
//! A door is a site that can run code or load a module that the scan does not see: `eval` of a
//! text, an unpickler, a loader call with a name that the scan does not know. Its gap states
//! `every_module` (AD-564). A collector marks the gap of a door with its form, its line and the
//! scope that holds it, so a contract can name the site and declare its reach. The model reads
//! only these words; it knows no language.

/// The form of a door whose reach a contract can declare. A site of another form has no door
/// record: its gap stays as it is.
#[derive(
    Clone,
    Copy,
    Debug,
    PartialEq,
    Eq,
    Hash,
    PartialOrd,
    Ord,
    serde::Serialize,
    serde::Deserialize,
    schemars::JsonSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum DoorForm {
    /// A reference to the builtin that evaluates a text as an expression.
    Eval,
    /// A reference to the builtin that runs a text as statements.
    Exec,
    /// A reference to the builtin that compiles a text to code.
    Compile,
    /// A function that loads objects from bytes and imports the module that the bytes name.
    Unpickle,
    /// A loader function that imports the module of a name that the scan does not know.
    Loader,
    /// A reference to the builtin import function.
    DunderImport,
    /// A call through a key that the scan does not know and that can name the constructor.
    ComputedKey,
}

impl DoorForm {
    /// Each form, in the order of the declaration.
    pub const ALL: [DoorForm; 7] = [
        DoorForm::Eval,
        DoorForm::Exec,
        DoorForm::Compile,
        DoorForm::Unpickle,
        DoorForm::Loader,
        DoorForm::DunderImport,
        DoorForm::ComputedKey,
    ];

    /// The word of the form, as the wire and the contract write it.
    pub fn word(self) -> &'static str {
        match self {
            DoorForm::Eval => "eval",
            DoorForm::Exec => "exec",
            DoorForm::Compile => "compile",
            DoorForm::Unpickle => "unpickle",
            DoorForm::Loader => "loader",
            DoorForm::DunderImport => "dunder_import",
            DoorForm::ComputedKey => "computed_key",
        }
    }

    /// The form of a word, or `None` for a word that names no form.
    pub fn of_word(word: &str) -> Option<DoorForm> {
        DoorForm::ALL.into_iter().find(|form| form.word() == word)
    }
}

/// The door of a gap: its form, the line of the site and the scope that holds it.
#[derive(
    Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize, schemars::JsonSchema,
)]
#[serde(deny_unknown_fields)]
pub struct DoorSite {
    /// The form of the door.
    pub form: DoorForm,
    /// The line of the site in the file of the module, counted from 1.
    pub line: u32,
    /// The dotted names of the classes and functions that hold the site. Empty text means module
    /// level. An absent scope cannot match a scope selector.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scope: Option<String>,
    /// The name that an import statement binds to the door in its module, when the site is such
    /// a statement. Another module can import that name, so the model checks that none does.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub binding: Option<String>,
}
