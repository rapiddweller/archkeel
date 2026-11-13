# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-condition classes of the AD-402 unproved inventory (AD-414)."""

from __future__ import annotations

from python_compile_grammar_families import seeds

PROOFS = {
    "ast-structure": (
        "Python/bltinmodule.c:builtin_compile_impl: 'is_ast = PyAST_Check(source);' and "
        "'if (is_ast)' guard 'if (mod == NULL || !_PyAST_Validate(mod))'. "
        "Parser/pegen.c:_PyPegen_run_parser calls validation only under "
        "'#if defined(Py_DEBUG) && !defined(_Py_TEST_PEGEN)'. "
        "Python/ast.c validates caller-built shapes; parser productions build nonempty suites, "
        "paired dictionary/comparison/pattern lists, expression contexts and source positions. "
        "Do not extend this proof to validate_name or recursion/resource checks."
    ),
    "type-comments-disabled": (
        "Parser/pegen.c:_PyPegen_Parser_New: "
        "'tok->type_comments = (flags & PyPARSE_TYPE_COMMENTS) > 0;'. "
        "Grammar/python.gram:invalid_double_type_comments requires "
        "'TYPE_COMMENT NEWLINE TYPE_COMMENT NEWLINE INDENT'; invalid_star_etc requires "
        "\"'*' ',' TYPE_COMMENT\". compile with flags=0 does not produce TYPE_COMMENT tokens."
    ),
    "declaration-not-call": (
        "Python/compile.c declares 'static int compiler_error(struct compiler *, ...)' "
        "with version-specific location arguments. The inventory scanner includes its declaration. "
        "A C declaration does not execute or raise an error."
    ),
    "instruction-api": (
        "Python/compile.c:instructions_to_instr_sequence: "
        "'if (!PyTuple_Check(item) || PyTuple_GET_SIZE(item) != 6)' and label range checks "
        "validate the instruction-list API. _PyCompile_OptimizeCfg checks "
        "'if (!_PyInstructionSequence_Check(seq))'. "
        "Python/flowgraph.c:_PyCompile_OptimizeCfg has the same API check. "
        "The source compiler does not call these Python-object test APIs."
    ),
    "parser-other-mode": (
        "Parser/pegen.c:_PyPegen_run_parser: 'if (p->start_rule == Py_single_input && ' "
        "'bad_single_statement(p))' guards the multiple-statement error. "
        "The incomplete-input error requires 'p->flags & PyPARSE_ALLOW_INCOMPLETE_INPUT'. "
        "The exec oracle uses Py_file_input without that flag."
    ),
    "parser-old-feature-version": (
        "Parser/pegen.c:_PyPegen_number_token: 'if (p->feature_version < 6 && ' "
        "'strchr(num_raw, '_') != NULL)' guards the Python 3.6 numeric-literal diagnostic. "
        "compile has no feature_version argument and selects the running minor (11 through 14)."
    ),
    "tokenizer-other-entry": (
        "Parser/tokenizer/file_tokenizer.c:tok_readline_raw/_PyTokenizer_FromFile read a FILE*. "
        "Parser/tokenizer/readline_tokenizer.c:_PyTokenizer_FromReadline uses a readline callable. "
        "Parser/pegen.c:_PyPegen_run_parser_from_string selects _PyTokenizer_FromString or "
        "_PyTokenizer_FromUTF8, not the FILE* or readline entry."
    ),
}


def proof_class(site: dict) -> str | None:
    file, function = site["file"], site["function"]
    expression = site["expression"]
    if file == "Python/ast.c" and "PyExc_ValueError" in expression and function != "validate_name":
        return "ast-structure"
    if file == "Grammar/python.gram" and (
        function == "invalid_double_type_comments"
        or "bare * has associated type comment" in expression
    ):
        return "type-comments-disabled"
    if file == "Python/compile.c" and expression.startswith("struct compiler *"):
        return "declaration-not-call"
    if file in {"Python/compile.c", "Python/flowgraph.c"} and (
        function == "instructions_to_instr_sequence"
        or (
            function == "_PyCompile_OptimizeCfg"
            and "expected an instruction sequence" in expression
        )
    ):
        return "instruction-api"
    if file == "Parser/pegen.c":
        if (
            "multiple statements found while compiling a single statement" in expression
            or expression == '"incomplete input"'
        ):
            return "parser-other-mode"
        if "Underscores in numeric literals are only supported" in expression:
            return "parser-old-feature-version"
    if (
        file in {"Parser/tokenizer/file_tokenizer.c", "Parser/tokenizer/readline_tokenizer.c"}
        and site["call"] != "PyErr_NoMemory"
    ):
        return "tokenizer-other-entry"
    return None


def classification(site: dict) -> tuple[str, str]:
    proof = proof_class(site)
    if proof:
        return "A", proof
    if (
        site["file"] == "Grammar/python.gram"
        and site["function"] in seeds()
        and site["function"] != "invalid_block"
    ):
        return "B", site["function"]
    return "D", condition_class(site)


def condition_class(site: dict) -> str:
    if site["call"] == "PyErr_NoMemory":
        return "resource-allocation"
    if site["file"] == "Python/ast.c":
        return "ast-validation"
    if site["file"] == "Grammar/python.gram":
        return "grammar"
    return site["file"]
