# AD-1176 A call that evaluates annotations is one dynamic-code site

**Status.** Accepted. Issues #2156 and #2157. It supersedes [AD-1173](ad-1173-a-module-that-evaluates-annotations-holds-each-value-it-cannot-name.md). It builds on [AD-1055](ad-1055-a-premised-pass-reads-pass-under-its-premises.md) and [AD-1056](ad-1056-a-declaration-names-the-modules-that-may-use-its-bound-name.md).

**Reason.** AD-1173 tracked each value that can reach an annotation. A taint analysis to prove dynamic code safe is open without end: PR #2166 took 38 commits and 44 Codex P1 findings, and each fix left a new form. The product principle of the owner (2026-11-28) is: dynamic code is UNKNOWN, and a declared site reads PASS under its premise.

**Decision.** A name that evaluates annotations is one dynamic-code site (`dynamic_import`), at each reference of the name:
1. `typing.get_type_hints`, `typing._eval_type`, `typing.evaluate_forward_ref`, `typing_extensions.get_type_hints`, `typing_extensions.evaluate_forward_ref`, `inspect.get_annotations`, `annotationlib.get_annotations` and `inspect.Signature.from_callable`. These are hazard names. The existing rules for hazard names give the import, the alias, the star import and the escape through a name.
2. `inspect.signature` is a site only in a call with an `eval_str` keyword that is not the literal `False`, or with a `**` expansion.
3. The call of a method named `_evaluate`, the private evaluation of a `ForwardRef`.

The survey does not follow the strings that reach the call. A contract declares the site (`trojan_horse_reach`, schema 3.20.0) with its premise, and the rule reads PASS under it. A string annotation is read as code when it stands in the text (AD-1095, AD-1134); that stays.

**Removed.** The taint pass of AD-1173: the class rule, the binding analysis and the held-name tracking in `hazards_annotation_class.rs` and `hazards_annotation_imports.rs`.

**Cost.** A module that evaluates annotations is UNKNOWN until its site is declared, also when all its annotations are plain types. Measured on the references (CE `23bd48d9`, EE `560d5c7ef`, FastAPI): verdicts are the same before and after. Collection gaps: CE 95 to 96, EE 159 to 165, FastAPI 11 to 11.

**Limit.** A module that gets its annotations evaluated only by another module (a library) is not gated: the survey reads only the module itself. `inspect.signature` stored under another name by an attribute assignment (`sig = inspect.signature`) is not followed: the call `sig(f, eval_str=True)` is no site. A name of `typing` that the survey cannot trace (`getattr(typing, n)(..)`) stays a site by AD-664. `from typing import *` is a site now, because `typing` exports `get_type_hints`.

**Tests.** `tests/test_collector_false_pass_python_annotation_closed.py`: the plants of #2166 (CPython 3.12 loads `app.lib` in each) must stay UNKNOWN or FAIL; each control is UNKNOWN and PASS under its declaration. Unit tests in `hazards_importers_tests.rs` pin the calls of the site list.
