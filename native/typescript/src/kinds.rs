// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The node kinds that `parse.py` names (`_NodeKind`), as one enum.
//!
//! `_node_kind` compares the text of a kind, so a named kind and an anonymous token of the same
//! text are one kind. A table from the id of the grammar to `K` does the same in one lookup, and a
//! kind that `_NodeKind` does not list is `K::Other`, as `_node_kind` gives `None`.

use tree_sitter::{Language, Node};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum K {
    Other,
    Asterisk,
    Abstract,
    AbstractClassDeclaration,
    AccessibilityModifier,
    AmbientDeclaration,
    Arguments,
    Array,
    ArrayPattern,
    ArrowFunction,
    As,
    AsExpression,
    AssignmentExpression,
    AssignmentPattern,
    AugmentedAssignmentExpression,
    Async,
    BinaryExpression,
    Equal,
    NotEqual,
    StrictEqual,
    StrictNotEqual,
    CallExpression,
    CatchClause,
    Class,
    ClassBody,
    ClassDeclaration,
    ClassExpression,
    ClassHeritage,
    ClassStaticBlock,
    Comment,
    ComputedPropertyName,
    Const,
    Declare,
    Default,
    Delete,
    Decorator,
    EnumAssignment,
    EnumDeclaration,
    ElseClause,
    EscapeSequence,
    ExportClause,
    ExportSpecifier,
    ExportStatement,
    ExpressionStatement,
    ExtendsClause,
    ExtendsTypeClause,
    False,
    ForInStatement,
    ForStatement,
    FormalParameters,
    FunctionDeclaration,
    FunctionExpression,
    FunctionSignature,
    GeneratorFunction,
    GeneratorFunctionDeclaration,
    Get,
    HashBangLine,
    Identifier,
    IfStatement,
    ImplementsClause,
    ImportAlias,
    ImportClause,
    ImportRequireClause,
    ImportSpecifier,
    ImportStatement,
    InterfaceBody,
    InterfaceDeclaration,
    InternalModule,
    JsxAttribute,
    JsxNamespaceName,
    LexicalDeclaration,
    MemberExpression,
    MethodDefinition,
    MethodSignature,
    Module,
    NamedImports,
    NestedIdentifier,
    NamespaceExport,
    NamespaceImport,
    NewExpression,
    NonNullExpression,
    Null,
    Number,
    Object,
    ObjectPattern,
    ObjectAssignmentPattern,
    Pair,
    PairPattern,
    OptionalParameter,
    OptionalChain,
    OptionalChainOperator,
    Override,
    ParenthesizedExpression,
    PrivatePropertyIdentifier,
    Program,
    PropertyIdentifier,
    PropertySignature,
    PublicFieldDefinition,
    Readonly,
    RequiredParameter,
    RestParameter,
    RestPattern,
    ReturnStatement,
    SatisfiesExpression,
    Set,
    ShorthandPropertyIdentifier,
    ShorthandPropertyIdentifierPattern,
    StatementBlock,
    Static,
    String,
    StringFragment,
    SwitchCase,
    SwitchBody,
    SubscriptExpression,
    TemplateString,
    TemplateSubstitution,
    This,
    True,
    Type,
    TypeAliasDeclaration,
    TypeAnnotation,
    TypeArguments,
    TypeIdentifier,
    TypeParameter,
    TypeQuery,
    Typeof,
    UnaryExpression,
    UpdateExpression,
    Var,
    VariableDeclaration,
    VariableDeclarator,
    WithStatement,
    Question,
}

/// `(text, kind)` for each kind of `_NodeKind`.
const NAMES: &[(&str, K)] = &[
    ("*", K::Asterisk),
    ("abstract", K::Abstract),
    ("abstract_class_declaration", K::AbstractClassDeclaration),
    ("accessibility_modifier", K::AccessibilityModifier),
    ("ambient_declaration", K::AmbientDeclaration),
    ("arguments", K::Arguments),
    ("array", K::Array),
    ("array_pattern", K::ArrayPattern),
    ("arrow_function", K::ArrowFunction),
    ("as", K::As),
    ("as_expression", K::AsExpression),
    ("assignment_expression", K::AssignmentExpression),
    ("assignment_pattern", K::AssignmentPattern),
    (
        "augmented_assignment_expression",
        K::AugmentedAssignmentExpression,
    ),
    ("async", K::Async),
    ("binary_expression", K::BinaryExpression),
    ("==", K::Equal),
    ("!=", K::NotEqual),
    ("===", K::StrictEqual),
    ("!==", K::StrictNotEqual),
    ("call_expression", K::CallExpression),
    ("catch_clause", K::CatchClause),
    ("class", K::Class),
    ("class_body", K::ClassBody),
    ("class_declaration", K::ClassDeclaration),
    ("class_expression", K::ClassExpression),
    ("class_heritage", K::ClassHeritage),
    ("class_static_block", K::ClassStaticBlock),
    ("comment", K::Comment),
    ("computed_property_name", K::ComputedPropertyName),
    ("const", K::Const),
    ("declare", K::Declare),
    ("default", K::Default),
    ("delete", K::Delete),
    ("decorator", K::Decorator),
    ("enum_assignment", K::EnumAssignment),
    ("enum_declaration", K::EnumDeclaration),
    ("else_clause", K::ElseClause),
    ("escape_sequence", K::EscapeSequence),
    ("export_clause", K::ExportClause),
    ("export_specifier", K::ExportSpecifier),
    ("export_statement", K::ExportStatement),
    ("expression_statement", K::ExpressionStatement),
    ("extends_clause", K::ExtendsClause),
    ("extends_type_clause", K::ExtendsTypeClause),
    ("false", K::False),
    ("for_in_statement", K::ForInStatement),
    ("for_statement", K::ForStatement),
    ("formal_parameters", K::FormalParameters),
    ("function_declaration", K::FunctionDeclaration),
    ("function_expression", K::FunctionExpression),
    ("function_signature", K::FunctionSignature),
    ("generator_function", K::GeneratorFunction),
    (
        "generator_function_declaration",
        K::GeneratorFunctionDeclaration,
    ),
    ("get", K::Get),
    ("hash_bang_line", K::HashBangLine),
    ("identifier", K::Identifier),
    ("if_statement", K::IfStatement),
    ("implements_clause", K::ImplementsClause),
    ("import_alias", K::ImportAlias),
    ("import_clause", K::ImportClause),
    ("import_require_clause", K::ImportRequireClause),
    ("import_specifier", K::ImportSpecifier),
    ("import_statement", K::ImportStatement),
    ("interface_body", K::InterfaceBody),
    ("interface_declaration", K::InterfaceDeclaration),
    ("internal_module", K::InternalModule),
    ("jsx_attribute", K::JsxAttribute),
    ("jsx_namespace_name", K::JsxNamespaceName),
    ("lexical_declaration", K::LexicalDeclaration),
    ("member_expression", K::MemberExpression),
    ("method_definition", K::MethodDefinition),
    ("method_signature", K::MethodSignature),
    ("module", K::Module),
    ("named_imports", K::NamedImports),
    ("nested_identifier", K::NestedIdentifier),
    ("namespace_export", K::NamespaceExport),
    ("namespace_import", K::NamespaceImport),
    ("new_expression", K::NewExpression),
    ("non_null_expression", K::NonNullExpression),
    ("null", K::Null),
    ("number", K::Number),
    ("object", K::Object),
    ("object_pattern", K::ObjectPattern),
    ("object_assignment_pattern", K::ObjectAssignmentPattern),
    ("pair", K::Pair),
    ("pair_pattern", K::PairPattern),
    ("optional_parameter", K::OptionalParameter),
    ("optional_chain", K::OptionalChain),
    ("?.", K::OptionalChainOperator),
    ("override", K::Override),
    ("parenthesized_expression", K::ParenthesizedExpression),
    ("private_property_identifier", K::PrivatePropertyIdentifier),
    ("program", K::Program),
    ("property_identifier", K::PropertyIdentifier),
    ("property_signature", K::PropertySignature),
    ("public_field_definition", K::PublicFieldDefinition),
    ("readonly", K::Readonly),
    ("required_parameter", K::RequiredParameter),
    ("rest_parameter", K::RestParameter),
    ("rest_pattern", K::RestPattern),
    ("return_statement", K::ReturnStatement),
    ("satisfies_expression", K::SatisfiesExpression),
    ("set", K::Set),
    (
        "shorthand_property_identifier",
        K::ShorthandPropertyIdentifier,
    ),
    (
        "shorthand_property_identifier_pattern",
        K::ShorthandPropertyIdentifierPattern,
    ),
    ("statement_block", K::StatementBlock),
    ("static", K::Static),
    ("string", K::String),
    ("string_fragment", K::StringFragment),
    ("switch_case", K::SwitchCase),
    ("switch_body", K::SwitchBody),
    ("subscript_expression", K::SubscriptExpression),
    ("template_string", K::TemplateString),
    ("template_substitution", K::TemplateSubstitution),
    ("this", K::This),
    ("true", K::True),
    ("type", K::Type),
    ("type_alias_declaration", K::TypeAliasDeclaration),
    ("type_annotation", K::TypeAnnotation),
    ("type_arguments", K::TypeArguments),
    ("type_identifier", K::TypeIdentifier),
    ("type_parameter", K::TypeParameter),
    ("type_query", K::TypeQuery),
    ("typeof", K::Typeof),
    ("unary_expression", K::UnaryExpression),
    ("update_expression", K::UpdateExpression),
    ("var", K::Var),
    ("variable_declaration", K::VariableDeclaration),
    ("variable_declarator", K::VariableDeclarator),
    ("with_statement", K::WithStatement),
    ("?", K::Question),
];

/// The fields of a node that the syntax walk reads. Their ids are looked up once for a grammar:
/// a lookup by name compares strings.
#[derive(Clone, Copy)]
pub enum F {
    Alias,
    Argument,
    Arguments,
    Body,
    Constructor,
    Declaration,
    Function,
    Index,
    Key,
    Kind,
    Left,
    Name,
    Object,
    Operator,
    Parameter,
    Parameters,
    Pattern,
    Property,
    ReturnType,
    Right,
    Source,
    Type,
    Value,
}

const FIELD_NAMES: &[(F, &str)] = &[
    (F::Alias, "alias"),
    (F::Argument, "argument"),
    (F::Arguments, "arguments"),
    (F::Body, "body"),
    (F::Constructor, "constructor"),
    (F::Declaration, "declaration"),
    (F::Function, "function"),
    (F::Index, "index"),
    (F::Key, "key"),
    (F::Kind, "kind"),
    (F::Left, "left"),
    (F::Name, "name"),
    (F::Object, "object"),
    (F::Operator, "operator"),
    (F::Parameter, "parameter"),
    (F::Parameters, "parameters"),
    (F::Pattern, "pattern"),
    (F::Property, "property"),
    (F::ReturnType, "return_type"),
    (F::Right, "right"),
    (F::Source, "source"),
    (F::Type, "type"),
    (F::Value, "value"),
];

/// The id of the node kind that the parser gives to a repaired region (`ts_builtin_sym_error`).
const ERROR_ID: u16 = u16::MAX;

/// What the walk needs to know about a node id: its kind and whether the grammar names it.
#[derive(Clone, Copy)]
pub struct Info {
    pub kind: K,
    pub named: bool,
    pub error: bool,
}

/// The kind of each node id of one grammar.
pub struct KindMap {
    table: Vec<(K, bool)>,
    fields: Vec<u16>,
}

impl KindMap {
    pub fn new(language: &Language) -> Self {
        let table = (0..language.node_kind_count() as u16)
            .map(|id| {
                let text = language.node_kind_for_id(id).unwrap_or("");
                let kind = NAMES
                    .iter()
                    .find(|(name, _)| *name == text)
                    .map_or(K::Other, |(_, kind)| *kind);
                (kind, language.node_kind_is_named(id))
            })
            .collect();
        let fields = FIELD_NAMES
            .iter()
            .map(|(_, name)| {
                language
                    .field_id_for_name(name)
                    .map_or(0, std::num::NonZeroU16::get)
            })
            .collect();
        Self { table, fields }
    }

    /// The kind, the name flag and the repair flag of a node, from one read of its id.
    pub fn info(&self, node: Node) -> Info {
        let id = node.kind_id();
        let (kind, named) = self
            .table
            .get(usize::from(id))
            .copied()
            .unwrap_or((K::Other, id == ERROR_ID));
        Info {
            kind,
            named,
            error: id == ERROR_ID,
        }
    }

    /// `node.child_by_field_name`, by the id of the field.
    pub fn field<'t>(&self, node: Node<'t>, field: F) -> Option<Node<'t>> {
        match self.fields.get(field as usize) {
            Some(id) if *id != 0 => node.child_by_field_id(*id),
            _ => None,
        }
    }

    pub fn of(&self, node: Node) -> K {
        self.info(node).kind
    }
}

#[cfg(test)]
#[path = "kinds_tests.rs"]
mod tests;
