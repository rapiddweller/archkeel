// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed vocabulary `ExceptionName`, written as a plain enum (its `impl` blocks are plain items).

/// The protocol 9 kind of an analyzer failure (`Kind::ExceptionGap`). Python writes the class
/// name of the exception that stopped a file: `OSError` and the subclasses that a file read can
/// raise, `UnicodeDecodeError`, `SyntaxError` and its subclasses, `ValueError` and
/// `TooDeepError` (`analyzer/python/source.py`). Dart writes the names of its problem kinds
/// (`analyzer/dart/collect.py`, `resolve.py`, `snapshot.py`, `syntax.py`).
#[derive(
    Clone,
    Copy,
    Debug,
    PartialEq,
    Eq,
    PartialOrd,
    Ord,
    Hash,
    serde::Serialize,
    serde::Deserialize,
    schemars::JsonSchema,
)]
pub enum ExceptionName {
    #[serde(rename = "SyntaxError")]
    SyntaxError,
    #[serde(rename = "IndentationError")]
    IndentationError,
    #[serde(rename = "TabError")]
    TabError,
    #[serde(rename = "UnicodeDecodeError")]
    UnicodeDecodeError,
    #[serde(rename = "ValueError")]
    ValueError,
    #[serde(rename = "TooDeepError")]
    TooDeepError,
    #[serde(rename = "OSError")]
    OsError,
    #[serde(rename = "FileNotFoundError")]
    FileNotFoundError,
    #[serde(rename = "PermissionError")]
    PermissionError,
    #[serde(rename = "IsADirectoryError")]
    IsADirectoryError,
    #[serde(rename = "NotADirectoryError")]
    NotADirectoryError,
    #[serde(rename = "TimeoutError")]
    TimeoutError,
    #[serde(rename = "InterruptedError")]
    InterruptedError,
    #[serde(rename = "DirectiveError")]
    DirectiveError,
    #[serde(rename = "UnsupportedDeclaration")]
    UnsupportedDeclaration,
    #[serde(rename = "UnsupportedMember")]
    UnsupportedMember,
    #[serde(rename = "UnsupportedParameter")]
    UnsupportedParameter,
    #[serde(rename = "LanguageVersionError")]
    LanguageVersionError,
    #[serde(rename = "SdkConstraintError")]
    SdkConstraintError,
    #[serde(rename = "DuplicateDeclaration")]
    DuplicateDeclaration,
    #[serde(rename = "PartError")]
    PartError,
    #[serde(rename = "PartOwnershipConflict")]
    PartOwnershipConflict,
    #[serde(rename = "DartSourceLink")]
    DartSourceLink,
    #[serde(rename = "SnapshotError")]
    SnapshotError,
    #[serde(rename = "DartModuleError")]
    DartModuleError,
    #[serde(rename = "DartModuleCollision")]
    DartModuleCollision,
    #[serde(rename = "SelectedRootError")]
    SelectedRootError,
    #[serde(rename = "ContainmentError")]
    ContainmentError,
    #[serde(rename = "ExcludedTreeError")]
    ExcludedTreeError,
    #[serde(rename = "PubspecMissing")]
    PubspecMissing,
    #[serde(rename = "syntax_error")]
    DartSyntaxError,
    #[serde(rename = "invalid_encoding")]
    InvalidEncoding,
    /// Protocol 10.0.0 only (AD-367): the published 9.0.0 schema does not list it.
    #[serde(rename = "ShadowedModule")]
    ShadowedModule,
}

impl ExceptionName {
    /// Each value, in the order of the declaration.
    pub const ALL: &'static [Self] = &[
        Self::SyntaxError,
        Self::IndentationError,
        Self::TabError,
        Self::UnicodeDecodeError,
        Self::ValueError,
        Self::TooDeepError,
        Self::OsError,
        Self::FileNotFoundError,
        Self::PermissionError,
        Self::IsADirectoryError,
        Self::NotADirectoryError,
        Self::TimeoutError,
        Self::InterruptedError,
        Self::DirectiveError,
        Self::UnsupportedDeclaration,
        Self::UnsupportedMember,
        Self::UnsupportedParameter,
        Self::LanguageVersionError,
        Self::SdkConstraintError,
        Self::DuplicateDeclaration,
        Self::PartError,
        Self::PartOwnershipConflict,
        Self::DartSourceLink,
        Self::SnapshotError,
        Self::DartModuleError,
        Self::DartModuleCollision,
        Self::SelectedRootError,
        Self::ContainmentError,
        Self::ExcludedTreeError,
        Self::PubspecMissing,
        Self::DartSyntaxError,
        Self::InvalidEncoding,
        Self::ShadowedModule,
    ];

    /// The JSON text of the value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::SyntaxError => "SyntaxError",
            Self::IndentationError => "IndentationError",
            Self::TabError => "TabError",
            Self::UnicodeDecodeError => "UnicodeDecodeError",
            Self::ValueError => "ValueError",
            Self::TooDeepError => "TooDeepError",
            Self::OsError => "OSError",
            Self::FileNotFoundError => "FileNotFoundError",
            Self::PermissionError => "PermissionError",
            Self::IsADirectoryError => "IsADirectoryError",
            Self::NotADirectoryError => "NotADirectoryError",
            Self::TimeoutError => "TimeoutError",
            Self::InterruptedError => "InterruptedError",
            Self::DirectiveError => "DirectiveError",
            Self::UnsupportedDeclaration => "UnsupportedDeclaration",
            Self::UnsupportedMember => "UnsupportedMember",
            Self::UnsupportedParameter => "UnsupportedParameter",
            Self::LanguageVersionError => "LanguageVersionError",
            Self::SdkConstraintError => "SdkConstraintError",
            Self::DuplicateDeclaration => "DuplicateDeclaration",
            Self::PartError => "PartError",
            Self::PartOwnershipConflict => "PartOwnershipConflict",
            Self::DartSourceLink => "DartSourceLink",
            Self::SnapshotError => "SnapshotError",
            Self::DartModuleError => "DartModuleError",
            Self::DartModuleCollision => "DartModuleCollision",
            Self::SelectedRootError => "SelectedRootError",
            Self::ContainmentError => "ContainmentError",
            Self::ExcludedTreeError => "ExcludedTreeError",
            Self::PubspecMissing => "PubspecMissing",
            Self::DartSyntaxError => "syntax_error",
            Self::InvalidEncoding => "invalid_encoding",
            Self::ShadowedModule => "ShadowedModule",
        }
    }

    /// The value of a JSON text, or `None` when the vocabulary does not hold it.
    pub fn parse(text: &str) -> Option<Self> {
        match text {
            "SyntaxError" => Some(Self::SyntaxError),
            "IndentationError" => Some(Self::IndentationError),
            "TabError" => Some(Self::TabError),
            "UnicodeDecodeError" => Some(Self::UnicodeDecodeError),
            "ValueError" => Some(Self::ValueError),
            "TooDeepError" => Some(Self::TooDeepError),
            "OSError" => Some(Self::OsError),
            "FileNotFoundError" => Some(Self::FileNotFoundError),
            "PermissionError" => Some(Self::PermissionError),
            "IsADirectoryError" => Some(Self::IsADirectoryError),
            "NotADirectoryError" => Some(Self::NotADirectoryError),
            "TimeoutError" => Some(Self::TimeoutError),
            "InterruptedError" => Some(Self::InterruptedError),
            "DirectiveError" => Some(Self::DirectiveError),
            "UnsupportedDeclaration" => Some(Self::UnsupportedDeclaration),
            "UnsupportedMember" => Some(Self::UnsupportedMember),
            "UnsupportedParameter" => Some(Self::UnsupportedParameter),
            "LanguageVersionError" => Some(Self::LanguageVersionError),
            "SdkConstraintError" => Some(Self::SdkConstraintError),
            "DuplicateDeclaration" => Some(Self::DuplicateDeclaration),
            "PartError" => Some(Self::PartError),
            "PartOwnershipConflict" => Some(Self::PartOwnershipConflict),
            "DartSourceLink" => Some(Self::DartSourceLink),
            "SnapshotError" => Some(Self::SnapshotError),
            "DartModuleError" => Some(Self::DartModuleError),
            "DartModuleCollision" => Some(Self::DartModuleCollision),
            "SelectedRootError" => Some(Self::SelectedRootError),
            "ContainmentError" => Some(Self::ContainmentError),
            "ExcludedTreeError" => Some(Self::ExcludedTreeError),
            "PubspecMissing" => Some(Self::PubspecMissing),
            "syntax_error" => Some(Self::DartSyntaxError),
            "invalid_encoding" => Some(Self::InvalidEncoding),
            "ShadowedModule" => Some(Self::ShadowedModule),
            _ => None,
        }
    }
}

impl ExceptionName {
    /// Whether the published 9.0.0 schema lists the name.
    pub(crate) fn in_v9(self) -> bool {
        self != Self::ShadowedModule
    }
}
