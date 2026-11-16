# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The coverage tables of the scaling tests: which shape holds which construct class (AD-323).

`COVERAGE` names, for each construct class, the shapes that hold it. `KIND_CLASSES` puts each
kind of `kinds.rs` into one class. `FIELD_COVERAGE` names the shapes for each fact of the dump and
each field of a definition. `test_collector_native_scaling.py` checks that every kind, every field
and every shape appears, so a new kind or a new fact without a shape fails there.
"""

from __future__ import annotations

# Construct class -> shapes that hold it.
COVERAGE: dict[str, tuple[str, ...]] = {
    "classes": (
        "class-methods",
        "class-implements",
        "class-expressions",
        "abstract-classes",
        "class-static-accessors",
        "nested-classes",
    ),
    "class members and modifiers": (
        "abstract-classes",
        "declare-top-level",
        "class-fields",
        "class-private-static",
        "class-decorated-members",
        "class-static-accessors",
        "generators-async",
        "object-members",
        "class-string-names",
    ),
    "comment and decorator runs in a body": (
        "class-comment-run",
        "class-decorator-run",
        "class-decorator-comment-mix",
        "enum-comment-run",
        "interface-comment-run",
    ),
    "parameters": (
        "parameters",
        "parameters-defaults-rest",
        "optional-rest-parameters",
        "class-constructor-properties",
    ),
    "patterns": (
        "parameters-object-pattern",
        "parameters-array-pattern",
        "variable-patterns",
        "pattern-nest",
        "shorthand-and-assignment-patterns",
    ),
    "interfaces, enums and types": (
        "interface-members",
        "interfaces-flat",
        "enum-members",
        "type-union",
        "generics-and-type-queries",
        "overloads",
    ),
    "functions": (
        "functions-flat",
        "function-expressions",
        "generators-async",
        "arrows-flat",
        "nested-arrows",
        "nested-functions",
    ),
    "scopes and blocks": (
        "nested-blocks-var",
        "nested-blocks-let",
        "catch-frames",
        "for-in-frames",
        "switch-frames",
        "for-while-with",
        "statements-flat",
        "var-hoisting",
    ),
    "variables": ("constants-arrays", "var-hoisting", "variable-patterns"),
    "writes at depth": (
        "writes-at-depth",
        "writes-distinct-names",
        "writes-flat",
        "rebound-names",
        "statements-flat",
        "expressions-flat",
        "writes-imports-all-at-bottom",
        "writes-import-at-own-depth",
        "writes-same-import-at-depth",
        "writes-imports-in-siblings",
    ),
    "imports": (
        "imports-default",
        "imports-named",
        "imports-one-statement",
        "imports-namespace-require",
        "import-alias-export-star",
    ),
    "exports and re-exports": (
        "exports-declarations",
        "exports-clause",
        "reexports",
        "reexports-local-names",
        "export-default-class",
        "import-alias-export-star",
    ),
    "ambient declarations and namespaces": (
        "declare-global",
        "declare-top-level",
        "declare-modules",
        "nested-namespaces",
    ),
    "expressions": (
        "expressions-flat",
        "member-chain",
        "binary-chain",
        "object-members",
        "nested-arrays",
        "statements-flat",
    ),
    "literals": (
        "class-string-names",
        "templates-flat",
        "template-one",
        "expressions-flat",
        "long-string-line",
        "shorthand-and-assignment-patterns",
    ),
    "jsx": ("jsx-attributes",),
    "nests of jsx and the references of PR 4.2": ("nested-jsx", "require-calls"),
    "comments and the start of a file": ("class-comment-run", "hashbang", "triple-slash"),
    "type-only imports": ("imports-named",),
    "call sites at depth": (
        "sites-calls-at-depth",
        "sites-calls-in-arrow-nest",
        "sites-nested-calls",
        "sites-with-nest",
    ),
    "member chains": (
        "sites-member-chain-call",
        "sites-chained-calls",
        "sites-calls-with-chains",
        "sites-new-expressions",
        "sites-publication-chain",
    ),
    "computed access": ("sites-computed-access", "sites-computed-calls", "sites-subscript-flat"),
    "free names": (
        "sites-many-free-names",
        "sites-many-bound-names",
        "sites-free-names-in-frames",
        "sites-args-wide",
        "sites-escapes",
    ),
    "shadowed names": (
        "sites-many-shadowed-names",
        "sites-shadow-nest-arrows",
        "sites-calls-in-arrow-nest",
    ),
    "string comparisons in long chains": (
        "sites-comparisons-or-chain",
        "sites-comparisons-flat",
        "sites-comparison-wrappers",
        "sites-switch-cases",
        "sites-templates-comparisons",
    ),
    "sites in comment and decorator runs": (
        "sites-in-decorator-run",
        "sites-in-decorator-comment-mix",
        "sites-after-comment-run",
    ),
    "sites of a script": (
        "sites-script-wrappers",
        "sites-script-wrapper-nest",
        "sites-script-publications",
        "sites-iife-many-args",
        "sites-shorthand-properties",
    ),
    "sites in types and jsx": ("sites-type-positions", "sites-jsx-names"),
    "line shapes": (
        "one-line-functions",
        "one-line-imports",
        "one-line-astral",
        "one-line-non-ascii",
        "one-line-then-ascii-lines",
        "alternating-long-lines",
        "crlf-lines",
        "lone-cr-lines",
        "unicode-line-separators",
        "one-character-lines",
        "empty-lines",
        "tabs-and-marks",
        "long-comment-line",
    ),
}

# Each kind of `kinds.rs` (except `Other`) belongs to one construct class.
KIND_CLASSES: dict[str, tuple[str, ...]] = {
    "classes": (
        "ClassDeclaration Class ClassExpression ClassBody ClassHeritage ExtendsClause "
        "ImplementsClause AbstractClassDeclaration ClassStaticBlock"
    ).split(),
    "class members and modifiers": (
        "PublicFieldDefinition MethodDefinition Static Abstract Override Readonly Declare "
        "AccessibilityModifier PrivatePropertyIdentifier Get Set Async Asterisk Decorator "
        "ComputedPropertyName"
    ).split(),
    "parameters": (
        "FormalParameters RequiredParameter OptionalParameter RestParameter RestPattern Question"
    ).split(),
    "patterns": (
        "ArrayPattern ObjectPattern ObjectAssignmentPattern PairPattern AssignmentPattern "
        "ShorthandPropertyIdentifierPattern"
    ).split(),
    "interfaces, enums and types": (
        "InterfaceDeclaration InterfaceBody MethodSignature PropertySignature ExtendsTypeClause "
        "EnumDeclaration EnumAssignment TypeAliasDeclaration TypeAnnotation TypeArguments "
        "TypeParameter TypeQuery TypeIdentifier FunctionSignature"
    ).split(),
    "functions": (
        "FunctionDeclaration FunctionExpression GeneratorFunction GeneratorFunctionDeclaration "
        "ArrowFunction"
    ).split(),
    "scopes and blocks": (
        "StatementBlock CatchClause ForInStatement ForStatement SwitchBody SwitchCase "
        "WithStatement IfStatement ElseClause ReturnStatement"
    ).split(),
    "variables": "LexicalDeclaration VariableDeclaration VariableDeclarator Const Var".split(),
    "writes at depth": (
        "AssignmentExpression AugmentedAssignmentExpression UpdateExpression Delete "
        "ParenthesizedExpression"
    ).split(),
    "imports": (
        "ImportStatement ImportClause ImportSpecifier NamedImports NamespaceImport "
        "ImportRequireClause ImportAlias"
    ).split(),
    "exports and re-exports": (
        "ExportStatement ExportClause ExportSpecifier NamespaceExport Default"
    ).split(),
    "ambient declarations and namespaces": (
        "AmbientDeclaration InternalModule Module NestedIdentifier"
    ).split(),
    "expressions": (
        "CallExpression NewExpression MemberExpression SubscriptExpression Arguments "
        "BinaryExpression Equal NotEqual StrictEqual StrictNotEqual UnaryExpression Typeof "
        "AsExpression As SatisfiesExpression NonNullExpression OptionalChain "
        "OptionalChainOperator This Object Array Pair ExpressionStatement Program"
    ).split(),
    "literals": (
        "Identifier PropertyIdentifier ShorthandPropertyIdentifier Number String StringFragment "
        "EscapeSequence TemplateString TemplateSubstitution True False Null"
    ).split(),
    "jsx": "JsxAttribute JsxNamespaceName".split(),
    "comments and the start of a file": "Comment HashBangLine".split(),
    "type-only imports": ["Type"],
}

# Each fact of the dump and each field of a definition -> shapes that produce it.
FIELD_COVERAGE: dict[str, tuple[str, ...]] = {
    "definitions": ("class-methods", "functions-flat", "enum-members", "interfaces-flat"),
    "import_bindings": ("imports-named", "imports-default", "imports-namespace-require"),
    "module_exports": ("exports-declarations", "exports-clause", "reexports-local-names"),
    "rebound_names": ("rebound-names", "writes-flat"),
    "ambient_globals": ("declare-global",),
    "ambient_top_level": ("declare-top-level",),
    "module_file": ("exports-declarations", "imports-default"),
    "declaration_file": ("declare-top-level",),
    "script_mode": ("writes-at-depth", "rebound-names"),
    "script_bindings": ("variable-patterns", "var-hoisting", "nested-blocks-var"),
    "sites": ("sites-calls-at-depth", "sites-member-chain-call", "sites-computed-access"),
    "string_comparisons": ("sites-comparisons-or-chain", "sites-switch-cases"),
    "name": ("functions-flat",),
    "kind": ("class-methods", "enum-members", "type-union", "constants-arrays"),
    "span": ("one-line-astral", "tabs-and-marks", "crlf-lines", "long-comment-line"),
    "parent": ("nested-classes", "nested-functions", "class-methods"),
    "visibility": ("class-private-static", "exports-declarations"),
    "static": ("class-private-static",),
    "exported": ("exports-declarations", "exports-clause"),
    "annotation": ("class-fields", "interface-members", "constants-arrays"),
    "parameters": ("parameters", "parameters-defaults-rest", "optional-rest-parameters"),
    "returns": ("class-methods", "interface-members"),
    "bases": ("class-implements", "interfaces-flat"),
    "members": ("class-methods", "enum-members", "interface-members", "class-fields"),
    "decorators": ("class-decorated-members", "class-decorator-run"),
    "abstract": ("abstract-classes",),
    "members_complete": ("class-methods", "class-string-names"),
    "overload_signature": ("overloads",),
    "top_level": ("functions-flat", "nested-functions"),
    "signature_complete": ("parameters", "optional-rest-parameters"),
    "parent_line": ("nested-classes", "nested-functions"),
    "parent_column": ("nested-classes", "one-line-then-ascii-lines"),
    "is_async": ("generators-async",),
    "decorator_sources": ("class-decorated-members", "class-decorator-comment-mix"),
}

# Kinds of `_NodeKind` that the grammar never produces: `kinds_tests.rs` lists them too. No shape
# can hold them, so they are covered by name only.
NAME_ONLY = frozenset({"ClassExpression", "RestParameter"})
