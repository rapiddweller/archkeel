// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A trojan horse site as typed data (AD-664).
//!
//! A trojan horse is a site that can run code or load a module that the scan does not see: `eval` of a
//! text, an unpickler, a loader call with a name that the scan does not know. Its gap states
//! `every_module` (AD-564). A collector marks the gap of a trojan horse with its form, its line and the
//! scope that holds it, so a contract can name the site and declare its reach. The model reads
//! only these words; it knows no language.

/// The form of a trojan horse whose reach a contract can declare. A site of another form has no trojan horse
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
pub enum TrojanHorseForm {
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

impl TrojanHorseForm {
    /// Each form, in the order of the declaration.
    pub const ALL: [TrojanHorseForm; 7] = [
        TrojanHorseForm::Eval,
        TrojanHorseForm::Exec,
        TrojanHorseForm::Compile,
        TrojanHorseForm::Unpickle,
        TrojanHorseForm::Loader,
        TrojanHorseForm::DunderImport,
        TrojanHorseForm::ComputedKey,
    ];

    /// The word of the form, as the wire and the contract write it.
    pub fn word(self) -> &'static str {
        match self {
            TrojanHorseForm::Eval => "eval",
            TrojanHorseForm::Exec => "exec",
            TrojanHorseForm::Compile => "compile",
            TrojanHorseForm::Unpickle => "unpickle",
            TrojanHorseForm::Loader => "loader",
            TrojanHorseForm::DunderImport => "dunder_import",
            TrojanHorseForm::ComputedKey => "computed_key",
        }
    }

    /// The form of a word, or `None` for a word that names no form.
    pub fn of_word(word: &str) -> Option<TrojanHorseForm> {
        TrojanHorseForm::ALL
            .into_iter()
            .find(|form| form.word() == word)
    }
}

/// The trojan horse of a gap: its form or its name, the line of the site and the scope that holds it.
#[derive(
    Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize, schemars::JsonSchema,
)]
#[serde(deny_unknown_fields)]
pub struct TrojanHorseSite {
    /// The form of the trojan horse. A site of no form has none and a contract names it by `name`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub form: Option<TrojanHorseForm>,
    /// The qualified name that the gap of the site prints (`pickle.load`, `__self__`). A
    /// contract names a site by it (AD-1043).
    #[serde(rename = "name", default, skip_serializing_if = "Option::is_none")]
    pub site_name: Option<String>,
    /// The line of the site in the file of the module, counted from 1; 0 when the collector has
    /// no line for it.
    pub line: u32,
    /// True when the collector can identify the site by line but cannot state its scope.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub line_only: bool,
    /// The dotted names of the classes and functions that hold the site, outermost first. The
    /// module level has none.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scope: Option<String>,
    /// The name that an import statement binds to the trojan horse in its module, when the site is such
    /// a statement. Another module can import that name, so the model checks that none does.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub binding: Option<String>,
    /// The modules that can reach the bound name of the module of the site: an import of the
    /// name, a star import, or a use of an attribute or a text of that name (AD-1043).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub exposed_to: Vec<String>,
}
