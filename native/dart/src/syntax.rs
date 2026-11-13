// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The per-file syntax of a Dart source, as `analyzer/dart/syntax.py` defines it: the
//! definitions, the directives, the sites, the concerns and the first error. The field order is the order of the Python dataclasses, so that the dump of the
//! parity test is the JSON of `dataclasses.asdict`.

use serde::Serialize;

/// A closed vocabulary: the dump writes each variant in snake case, as the Python `StrEnum`.
macro_rules! vocabulary {
    ($(#[$meta:meta])* $vis:vis $name:ident { $($variant:ident),+ $(,)? }) => {
        $(#[$meta])*
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, serde::Deserialize)]
        #[serde(rename_all = "snake_case")]
        $vis enum $name {
            $($variant),+
        }
    };
}

/// A value of the syntax: the dump writes its fields in the order of the Python dataclass.
macro_rules! value {
    ($(#[$meta:meta])* $vis:vis $name:ident { $($field:ident: $kind:ty),+ $(,)? }) => {
        $(#[$meta])*
        #[derive(Clone, Debug, PartialEq, Eq, Serialize, serde::Deserialize)]
        #[serde(deny_unknown_fields)]
        $vis struct $name {
            $($vis $field: $kind),+
        }
    };
}

#[cfg(feature = "dump")]
pub(crate) use value;

value! {
    /// A source range: lines from 1, a UTF-16 column, the first 400 characters and the bytes.
    pub(crate) Span {
        line: usize,
        end_line: usize,
        column: usize,
        excerpt: String,
        start_byte: usize,
        end_byte: usize,
    }
}

vocabulary! {
    /// `Visibility.from_name`: private when the last dotted segment starts with `_`.
    pub(crate) Visibility {
        Public,
        Private,
    }
}

impl Visibility {
    pub(crate) fn of(name: &str) -> Self {
        let last = name.rsplit('.').next().unwrap_or(name);
        if last.starts_with('_') {
            Self::Private
        } else {
            Self::Public
        }
    }
}

vocabulary! {
    pub(crate) ParameterKind {
        Positional,
        Named,
    }
}

vocabulary! {
    pub(crate) MemberKind {
        Field,
        Method,
        Constructor,
        Getter,
        Setter,
        Operator,
    }
}

vocabulary! {
    pub(crate) DefinitionKind {
        Class,
        Interface,
        Mixin,
        Enum,
        Extension,
        ExtensionType,
        Typedef,
        Function,
        Getter,
        Setter,
        Variable,
    }
}

vocabulary! {
    pub(crate) DirectiveKind {
        Library,
        Import,
        Export,
        Part,
        PartOf,
    }
}

vocabulary! {
    pub(crate) Combinator {
        Show,
        Hide,
    }
}

vocabulary! {
    /// The class modifiers, in the order of the Python enum: the order of `Definition.modifiers`.
    pub(crate) Modifier {
        Abstract,
        Base,
        Final,
        Interface,
        Sealed,
        Mixin,
    }
}

impl Modifier {
    pub(crate) const ALL: [(Self, &'static str); 6] = [
        (Self::Abstract, "abstract"),
        (Self::Base, "base"),
        (Self::Final, "final"),
        (Self::Interface, "interface"),
        (Self::Sealed, "sealed"),
        (Self::Mixin, "mixin"),
    ];
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, serde::Deserialize)]
pub(crate) enum ConcernKind {
    #[serde(rename = "syntax_error")]
    SyntaxError,
    #[serde(rename = "invalid_encoding")]
    InvalidEncoding,
    #[serde(rename = "LanguageVersionError")]
    LanguageVersionError,
    #[serde(rename = "unsupported_directive")]
    UnsupportedDirective,
    #[serde(rename = "unsupported_declaration")]
    UnsupportedDeclaration,
}

impl ConcernKind {
    /// The value of the Python `StrEnum`: the concerns sort by it after the start byte.
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::SyntaxError => "syntax_error",
            Self::InvalidEncoding => "invalid_encoding",
            Self::LanguageVersionError => "LanguageVersionError",
            Self::UnsupportedDirective => "unsupported_directive",
            Self::UnsupportedDeclaration => "unsupported_declaration",
        }
    }

    /// A kind that makes the file incomplete: a candidate for `Syntax.first_error`.
    pub(crate) fn is_error(self) -> bool {
        matches!(
            self,
            Self::SyntaxError | Self::InvalidEncoding | Self::LanguageVersionError
        )
    }
}

value! {
    pub(crate) Parameter {
        name: String,
        annotation: Option<String>,
        kind: ParameterKind,
        default: Option<String>,
        default_known: bool,
        span: Span,
        field_formal: bool,
        super_formal: bool,
        optional: bool,
        required: bool,
    }
}

value! {
    pub(crate) Member {
        name: String,
        kind: MemberKind,
        span: Span,
        annotation: Option<String>,
        return_type: Option<String>,
        visibility: Visibility,
        r#static: bool,
        r#abstract: bool,
        parameters: Vec<Parameter>,
        initializer: Option<String>,
        literal: Option<String>,
        constructor_initializers: Vec<String>,
        redirect: Option<String>,
        factory: bool,
        constant: bool,
        r#final: bool,
        late: bool,
    }
}

impl Member {
    /// A member with the defaults of the Python dataclass.
    pub(crate) fn new(name: String, kind: MemberKind, span: Span) -> Self {
        Self {
            visibility: Visibility::of(&name),
            name,
            kind,
            span,
            annotation: None,
            return_type: None,
            r#static: false,
            r#abstract: false,
            parameters: Vec::new(),
            initializer: None,
            literal: None,
            constructor_initializers: Vec::new(),
            redirect: None,
            factory: false,
            constant: false,
            r#final: false,
            late: false,
        }
    }
}

value! {
    pub(crate) Definition {
        name: String,
        kind: DefinitionKind,
        span: Span,
        visibility: Visibility,
        type_parameters: Vec<String>,
        extends: Vec<String>,
        with_types: Vec<String>,
        implements: Vec<String>,
        alias: Option<String>,
        enum_members: Vec<String>,
        members: Vec<Member>,
        parameters: Vec<Parameter>,
        return_type: Option<String>,
        initializer: Option<String>,
        literal: Option<String>,
        modifiers: Vec<Modifier>,
        constant: bool,
        r#final: bool,
        late: bool,
        enum_member_spans: Vec<Span>,
    }
}

impl Definition {
    /// A definition with the defaults of the Python dataclass.
    pub(crate) fn new(name: String, kind: DefinitionKind, span: Span) -> Self {
        Self {
            visibility: Visibility::of(&name),
            name,
            kind,
            span,
            type_parameters: Vec::new(),
            extends: Vec::new(),
            with_types: Vec::new(),
            implements: Vec::new(),
            alias: None,
            enum_members: Vec::new(),
            members: Vec::new(),
            parameters: Vec::new(),
            return_type: None,
            initializer: None,
            literal: None,
            modifiers: Vec::new(),
            constant: false,
            r#final: false,
            late: false,
            enum_member_spans: Vec::new(),
        }
    }
}

value! {
    pub(crate) Directive {
        kind: DirectiveKind,
        span: Span,
        target: Option<String>,
        prefix: Option<String>,
        deferred: bool,
        show: Vec<String>,
        hide: Vec<String>,
        combinators: Vec<(Combinator, Vec<String>)>,
        alternatives: Vec<(String, String)>,
    }
}

impl Directive {
    pub(crate) fn new(kind: DirectiveKind, span: Span, target: Option<String>) -> Self {
        Self {
            kind,
            span,
            target,
            prefix: None,
            deferred: false,
            show: Vec::new(),
            hide: Vec::new(),
            combinators: Vec::new(),
            alternatives: Vec::new(),
        }
    }
}

vocabulary! {
    pub(crate) SiteKind {
        Reference,
        Call,
        Creation,
        Type,
        Extends,
        Implements,
        With,
        FieldFormal,
        SuperFormal,
        Binding,
        Assignment,
    }
}

impl SiteKind {
    /// The value of the Python `StrEnum`: the sites sort by it after the start byte.
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Reference => "reference",
            Self::Call => "call",
            Self::Creation => "creation",
            Self::Type => "type",
            Self::Extends => "extends",
            Self::Implements => "implements",
            Self::With => "with",
            Self::FieldFormal => "field_formal",
            Self::SuperFormal => "super_formal",
            Self::Binding => "binding",
            Self::Assignment => "assignment",
        }
    }
}

vocabulary! {
    pub(crate) SiteUse {
        Type,
        Read,
        Write,
        ReadWrite,
        Value,
    }
}

/// The scope of a site: `(scope, scope_span, scope_depth)` of `_sites`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct Context {
    pub(crate) scope: Option<String>,
    pub(crate) span: Option<Span>,
    pub(crate) depth: usize,
}

value! {
    pub(crate) Site {
        kind: SiteKind,
        expression: String,
        span: Span,
        name: Option<String>,
        receiver: Option<String>,
        scope: Option<String>,
        scope_span: Option<Span>,
        scope_depth: usize,
        arguments: Vec<String>,
        assigned_name: Option<String>,
        assignment_annotation: Option<String>,
        initializer: Option<String>,
        r#use: SiteUse,
        computed: bool,
        shadowed_names: Vec<String>,
        closure_scope: bool,
        expression_source: Option<String>,
        initializer_source: Option<String>,
    }
}

impl Site {
    /// A site with the defaults of the Python dataclass and the scope of `context`.
    pub(crate) fn new(kind: SiteKind, expression: String, span: Span, context: &Context) -> Self {
        Self {
            kind,
            expression,
            span,
            name: None,
            receiver: None,
            scope: context.scope.clone(),
            scope_span: context.span.clone(),
            scope_depth: context.depth,
            arguments: Vec::new(),
            assigned_name: None,
            assignment_annotation: None,
            initializer: None,
            r#use: SiteUse::Value,
            computed: false,
            shadowed_names: Vec::new(),
            closure_scope: false,
            expression_source: None,
            initializer_source: None,
        }
    }
}

value! {
    pub(crate) Concern {
        kind: ConcernKind,
        message: String,
        span: Span,
    }
}

value! {
    /// The syntax of one source.
    pub(crate) Syntax {
        definitions: Vec<Definition>,
        directives: Vec<Directive>,
        sites: Vec<Site>,
        concerns: Vec<Concern>,
        first_error: Option<Span>,
        complete: bool,
        language_version: Option<String>,
    }
}
