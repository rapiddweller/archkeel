// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed `forbidden_construct` rule and the constructs and selectors that it names.

use crate::model::{RuleHead, Selector};

closed_enum!(
    /// The constructs that `forbidden_construct` names (`ForbiddenConstructKind`).
    ConstructKind {
        /// A call of `getattr`.
        Getattr,
        /// A call of `hasattr`.
        Hasattr,
        /// A call of `cast`.
        Cast,
        /// A call of `eval`.
        Eval,
        /// A call of `exec`.
        Exec,
        /// A dynamic import.
        DynamicImport,
        /// A `type: ignore` comment.
        TypeIgnore,
        /// An `Any` annotation.
        AnyAnnotation,
        /// A body that declares no implementation.
        PlaceholderBody,
        /// An `assert` statement.
        Assert,
        /// A broad exception handler.
        BroadExcept,
        /// A call of `setattr`.
        Setattr,
        /// A call of `delattr`.
        Delattr,
        /// A call of `vars`.
        Vars,
        /// A use of `__dict__`.
        DunderDict,
        /// A comparison with a string literal.
        StringLiteralCompare,
        /// An import call that names its module by a literal string (AD-1440).
        StringImport,
    }
);

record!(
    pub(crate),
    /// One allowed suppression: its scope, line, statement and exact tag.
    TypeIgnore {
        /// The qualified name of the symbol.
        qualified_name: Selector,
        /// The line of the statement.
        line: u64,
        /// The statement as written.
        statement: String,
        /// The exact tag of the comment.
        tag: String,
    }
);

closed_enum!(
    /// The role of a construct selector.
    SelectorRole {
        /// A read.
        Read,
        /// A write.
        Write,
        /// A call.
        Call,
        /// A reflection call.
        Reflect,
        /// A constructor call.
        Constructor,
        /// A type test.
        TypeProbe,
        /// An equality test.
        Equality,
        /// A membership test.
        Membership,
        /// A pattern match.
        Match,
        /// A `startswith` test.
        Startswith,
        /// An `endswith` test.
        Endswith,
    }
);

record!(
    pub(crate),
    /// One nominal receiver and member, with an optional literal operand.
    ConstructSelector {
        /// The receiver that the selector reads.
        receiver: Selector,
        /// The member that the rule reads.
        #[serde(skip_serializing_if = "Option::is_none")]
        member: Option<String>,
        /// The role that the rule reads.
        role: SelectorRole,
        /// The literal that the selector reads.
        #[serde(skip_serializing_if = "Option::is_none")]
        literal: Option<String>,
    }
);

record!(
    pub(crate),
    /// A rule that forbids a written construct.
    ForbiddenConstruct {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The constructs that the rule names.
        constructs: Vec<ConstructKind>,
        /// The sources that the rule excepts by prefix.
        allowed_sources: Vec<Selector>,
        /// The sources that the rule excepts by exact name.
        exact_sources: Vec<Selector>,
        /// The `type: ignore` comments that the rule accepts.
        #[serde(skip_serializing_if = "Vec::is_empty")]
        allowed_type_ignores: Vec<TypeIgnore>,
        /// The selector of a construct on a receiver.
        #[serde(skip_serializing_if = "Option::is_none")]
        selector: Option<ConstructSelector>,
    }
);
