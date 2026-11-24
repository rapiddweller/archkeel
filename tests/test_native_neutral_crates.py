# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-668: a neutral crate names no language, and no violation of that is accepted.

The native contract forbids each neutral crate (`store`, `model`, `eval`, `report`, `core`) to name
`Profile`, the vocabulary of the languages, and `store` to use its language modules. This test is an
independent oracle of those rules: a token scan of the production source of each neutral crate.

- No module of a neutral crate names `Profile` in code. The self-contract has no violation (AD-1064
  keeps no list of accepted ones), so a module that names it is a place that the rule must find.
  This oracle needs no result, so a wrong PASS of the rule cannot hide it.
- Each module of a neutral crate that is named after a language (the variants of `Profile`) must be
  the target of a rule of the contract, so a new language module cannot land without a visible FAIL.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
NATIVE = ROOT / "native"
CONTRACT = NATIVE / "architecture-contract.json"
VOCABULARY = NATIVE / "facts/src/envelope_vocab.rs"
SYMBOL = "Profile"
CRATE_NAME = re.compile(r'^name\s*=\s*"([^"]+)"', re.MULTILINE)
TEST_MODULE = re.compile(
    r"^#\[cfg\(test\)\]\s*\n(?:#\[[^\n]*\]\s*\n)*\s*mod\s+\w+\s*\{", re.MULTILINE
)
TEXT = re.compile(
    r'r#*"(?:.|\n)*?"#*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])\'|//[^\n]*|/\*(?:.|\n)*?\*/'
)


def language_words() -> set[str]:
    """The lower-case names of the variants of `Profile`: the languages that the core knows."""
    text = VOCABULARY.read_text(encoding="utf-8")
    body = text.split("pub enum Profile {", 1)[1].split("}", 1)[0]
    return {word.lower() for word in re.findall(r"^\s*([A-Z]\w*),", body, re.MULTILINE)}


def code_of(text: str) -> str:
    """The code of a production file: no comment, no string, no inline test module."""
    match = TEST_MODULE.search(text)
    return TEXT.sub(" ", text[: match.start()] if match else text)


def module_of(namespace: str, crate: Path, path: Path) -> str:
    """The module name that the Rust collector gives a file of `crate/src`."""
    package = CRATE_NAME.search((crate / "Cargo.toml").read_text(encoding="utf-8"))
    assert package, crate
    parts = list(path.relative_to(crate / "src").with_suffix("").parts)
    if parts[-1] in {"lib", "mod"}:
        parts.pop()
    return ".".join([namespace, package.group(1).replace("-", "_"), *parts])


def production_files(crate: Path) -> list[Path]:
    """The Rust files of `crate/src` without test files and without the binary root."""
    return sorted(
        path
        for path in (crate / "src").rglob("*.rs")
        if not path.name.endswith("_tests.rs") and path.name not in {"tests.rs", "main.rs"}
    )


def naming_modules(crate: Path, symbol: str, namespace: str = "native") -> set[str]:
    """Each module of `crate` whose code names `symbol` as a whole word."""
    word = re.compile(rf"\b{re.escape(symbol)}\b")
    return {
        module_of(namespace, crate, path)
        for path in production_files(crate)
        if word.search(code_of(path.read_text(encoding="utf-8")))
    }


def symbol_rules(contract: dict) -> dict[str, str]:
    """Each rule that forbids `Profile`, with the crate that it guards."""
    return {
        rule["id"]: rule["source"]
        for rule in contract["rules"]
        if rule["kind"] == "forbidden_dependency" and rule.get("target_symbol") == SYMBOL
    }


def crate_dir(selector: str) -> Path:
    """The directory of the crate that a `native.archkeel_<name>` selector names."""
    name = selector.removeprefix("native.archkeel_")
    return NATIVE / name.replace("_", "-")


def test_no_module_of_a_neutral_crate_names_the_vocabulary() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rules = symbol_rules(contract)
    assert set(rules.values()) >= {
        f"native.archkeel_{name}" for name in ("store", "model", "eval", "report", "core")
    }
    problems = [
        f"{rule}: {module} names {SYMBOL}"
        for rule, source in sorted(rules.items())
        for module in sorted(naming_modules(crate_dir(source), SYMBOL))
    ]
    assert problems == [], "\n".join(problems)


def test_each_language_module_of_a_neutral_crate_is_the_target_of_a_rule() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    sources = set(symbol_rules(contract).values())
    targets = {
        rule["target"] for rule in contract["rules"] if rule["kind"] == "forbidden_dependency"
    }
    words = language_words()
    assert words == {"python", "dart", "typescript", "rust"}, words
    found = sorted(
        module
        for source in sources
        for path in production_files(crate_dir(source))
        if (module := module_of("native", crate_dir(source), path)).rsplit(".", 1)[-1] in words
    )
    unguarded = [module for module in found if module not in targets]
    assert unguarded == [], (
        f"each language module of a neutral crate needs a rule (AD-668): {unguarded}"
    )


def _crate(tmp_path: Path, files: dict[str, str]) -> Path:
    crate = tmp_path / "plant"
    (crate / "src").mkdir(parents=True)
    (crate / "Cargo.toml").write_text('[package]\nname = "archkeel-plant"\n')
    for name, text in files.items():
        (crate / "src" / name).write_text(text)
    return crate


def test_a_planted_variant_use_is_found_and_a_comment_string_or_test_is_not(tmp_path: Path) -> None:
    crate = _crate(
        tmp_path,
        {
            "lib.rs": "mod used;\nmod quiet;\n",
            "used.rs": "use x::Profile;\npub fn f(p: Profile) -> bool { p == Profile::Dart }\n",
            "quiet.rs": '//! Profile in a doc.\npub fn g() -> &\'static str { "Profile" }\n'
            "#[cfg(test)]\nmod tests {\n    fn t() { let _ = Profile::Dart; }\n}\n",
            "quiet_tests.rs": "fn t() { let _ = Profile::Dart; }\n",
        },
    )
    assert naming_modules(crate, SYMBOL) == {"native.archkeel_plant.used"}
