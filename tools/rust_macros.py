# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Expand the `macro_rules!` calls of one crate on tokens, for the API list of `rust_api.py`.

The list counts the public items that a macro builds, once for each call. A definition is read
from its tokens, a call is matched against its rules by example, and the transcribed tokens
replace the call. Only the matchers that the crates of `native/` need are read: the fragments
`ident`, `vis`, `meta`, `ty`, `tt`, `path`, `literal`, `lifetime`, `block`, `expr` and `item`, and
the repetitions `*`, `+` and `?` with a separator. Nothing here guesses:

- A call that no rule matches, a fragment that is not read, a repetition that does not line up, a
  call that nests deeper than `DEPTH`, and a name that two different definitions share are each
  a gap. The caller writes a gap as a line of the list; it does not shrink the count.
- A `#[macro_export]` definition expands in other crates, so it is a gap too.
- A macro of another crate or of the standard library is not expanded (see `docs/known-limits.md`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from rust_source import Token, group_end

DEPTH = 128
OPEN = {"(": ")", "[": "]", "{": "}"}
FRAGMENTS = frozenset("ident vis meta ty tt path literal lifetime block expr item".split())
TYPE_END = frozenset({",", ";", "=", "|", "{"})


@dataclass(frozen=True, slots=True)
class Gap:
    name: str
    reason: str


class Unreadable(Exception):
    """A matcher, a transcriber or a call that this reader does not read."""


@dataclass(slots=True)
class Var:
    name: str
    fragment: str


@dataclass(slots=True)
class Repeat:
    body: list[Element]
    separator: Token | None
    operator: str


@dataclass(slots=True)
class Delimited:
    open: Token
    body: list[Element]
    close: Token


Element = Token | Var | Repeat | Delimited


@dataclass(slots=True)
class Rule:
    matcher: list[Element]
    body: list[Element]


@dataclass(slots=True)
class Macro:
    name: str
    rules: list[Rule]
    exported: bool
    text: tuple[str, ...]


@dataclass(slots=True)
class Bound:
    """A bound fragment: tokens, or one `Bound` for each pass of a repetition."""

    tokens: list[Token] = field(default_factory=list)
    passes: list[Bound] | None = None


def _text(token: Token) -> str:
    return token.text


def _parse(tokens: Sequence[Token], matcher: bool) -> list[Element]:
    """Read tokens as matcher (`$x:frag`) or as transcriber (`$x`) elements."""
    out: list[Element] = []
    at = 0
    while at < len(tokens):
        token = tokens[at]
        if token.text == "$" and at + 1 < len(tokens):
            nxt = tokens[at + 1]
            if nxt.text == "(":
                end = group_end(tokens, at + 1)
                body = _parse(tokens[at + 2 : end - 1], matcher)
                tail = tokens[end : end + 2]
                if tail and tail[0].text in {"*", "+", "?"}:
                    out.append(Repeat(body, None, tail[0].text))
                    at = end + 1
                elif len(tail) == 2 and tail[1].text in {"*", "+"}:
                    out.append(Repeat(body, tail[0], tail[1].text))
                    at = end + 2
                else:
                    raise Unreadable("a repetition has no operator")
                continue
            if nxt.kind == "name" and matcher:
                if tokens[at + 2 : at + 3] != [] and tokens[at + 2].text == ":":
                    fragment = tokens[at + 3].text if at + 3 < len(tokens) else ""
                    if fragment not in FRAGMENTS:
                        raise Unreadable(f"the fragment {fragment} is not read")
                    out.append(Var(nxt.text, fragment))
                    at += 4
                    continue
                raise Unreadable("a matcher variable has no fragment")
            if nxt.kind == "name":
                out.append(Var(nxt.text, ""))
                at += 2
                continue
            raise Unreadable("a `$` is not followed by a name or a group")
        if token.kind == "punct" and token.text in OPEN:
            end = group_end(tokens, at)
            body = _parse(tokens[at + 1 : end - 1], matcher)
            out.append(Delimited(token, body, tokens[end - 1]))
            at = end
            continue
        out.append(token)
        at += 1
    return out


def _rules(body: Sequence[Token]) -> list[Rule]:
    rules: list[Rule] = []
    at = 0
    while at < len(body):
        if body[at].text not in OPEN:
            raise Unreadable("a rule does not start with a group")
        end = group_end(body, at)
        arrow = body[end : end + 2]
        if [t.text for t in arrow] != ["=", ">"] or end + 2 >= len(body):
            raise Unreadable("a rule has no `=>`")
        stop = group_end(body, end + 2)
        rules.append(
            Rule(_parse(body[at + 1 : end - 1], True), _parse(body[end + 3 : stop - 1], False))
        )
        at = stop + (1 if stop < len(body) and body[stop].text == ";" else 0)
    return rules


def _exported(tokens: Sequence[Token], at: int) -> bool:
    """Whether attributes before the `macro_rules` at `at` include `macro_export`."""
    end = at
    while end >= 2 and tokens[end - 1].text == "]":
        start = end - 1
        while start > 0 and not (tokens[start].text == "[" and tokens[start - 1].text == "#"):
            start -= 1
        if "macro_export" in {t.text for t in tokens[start:end]}:
            return True
        end = start - 1
    return False


def definitions(tokens: Sequence[Token]) -> tuple[list[Macro], list[Gap]]:
    """Return the `macro_rules!` definitions of one file, and the gaps of those not readable."""
    found: list[Macro] = []
    gaps: list[Gap] = []
    for at in range(len(tokens) - 3):
        if tokens[at].text != "macro_rules" or tokens[at + 1].text != "!":
            continue
        name = tokens[at + 2].text
        end = group_end(tokens, at + 3)
        body = tokens[at + 4 : end - 1]
        text = tuple(map(_text, body))
        try:
            found.append(Macro(name, _rules(body), _exported(tokens, at), text))
        except Unreadable as error:
            gaps.append(Gap(name, str(error)))
    return found, gaps


def skip_definitions(tokens: Sequence[Token]) -> list[Token]:
    """Return the tokens without the text of each `macro_rules!` definition."""
    out: list[Token] = []
    at = 0
    while at < len(tokens):
        if (
            tokens[at].text == "macro_rules"
            and tokens[at + 1 : at + 2]
            and tokens[at + 1].text == "!"
        ):
            end = group_end(tokens, at + 3)
            at = end + (1 if end < len(tokens) and tokens[end].text == ";" else 0)
            continue
        out.append(tokens[at])
        at += 1
    return out


def _fragment(kind: str, tokens: Sequence[Token], at: int) -> int:
    """Return the end of the fragment of `kind` that starts at `at`; raise when none starts."""
    if at > len(tokens) or (at == len(tokens) and kind != "vis"):
        raise Unreadable("the call ends early")
    here = tokens[at] if at < len(tokens) else None
    if kind == "ident":
        if here is None or here.kind != "name" or here.text.startswith("'"):
            raise Unreadable("no identifier")
        raw = [t.text for t in tokens[at + 1 : at + 3]]
        return at + 3 if here.text == "r" and raw[:1] == ["#"] and len(raw) == 2 else at + 1
    if kind == "lifetime":
        if here is None or not here.text.startswith("'"):
            raise Unreadable("no lifetime")
        return at + 1
    if kind == "literal":
        if here is None or here.kind != "literal":
            raise Unreadable("no literal")
        return at + 1
    if kind == "vis":
        if here is None or here.text != "pub":
            return at
        group = tokens[at + 1 : at + 2]
        return group_end(tokens, at + 1) if group and group[0].text == "(" else at + 1
    if kind == "tt":
        return group_end(tokens, at) if here and here.text in OPEN else at + 1
    if kind == "block":
        if here is None or here.text != "{":
            raise Unreadable("no block")
        return group_end(tokens, at)
    if kind == "meta" or kind == "path":
        return _path(tokens, at, kind == "meta")
    return _extent(tokens, at, kind)


def _path(tokens: Sequence[Token], at: int, meta: bool) -> int:
    position = at
    while position < len(tokens) and tokens[position].kind == "name":
        position += 1
        if tokens[position : position + 2] and [
            t.text for t in tokens[position : position + 2]
        ] == [":", ":"]:
            position += 2
        else:
            break
    if position == at:
        raise Unreadable("no path")
    if meta and position < len(tokens):
        if tokens[position].text in OPEN:
            return group_end(tokens, position)
        if tokens[position].text == "=":
            return _extent(tokens, position + 1, "expr")
    return position


def _extent(tokens: Sequence[Token], at: int, kind: str) -> int:
    """The end of a `ty`, `expr` or `item`: up to a stop token outside every group."""
    if kind == "item":
        position = at
        while position < len(tokens):
            text = tokens[position].text
            if text == ";":
                return position + 1
            if text in OPEN:
                end = group_end(tokens, position)
                if text == "{":
                    return end
                position = end
            else:
                position += 1
        return position
    stops = TYPE_END if kind == "ty" else frozenset({",", ";"})
    angle, position = 0, at
    while position < len(tokens):
        token = tokens[position]
        if token.text in OPEN and token.kind == "punct" and (kind != "ty" or token.text != "{"):
            position = group_end(tokens, position)
            continue
        if kind == "ty" and token.text == "<":
            angle += 1
        elif kind == "ty" and token.text == ">" and tokens[position - 1].text != "-":
            angle -= 1
        elif angle <= 0 and token.text in stops:
            break
        elif (
            token.text == "="
            and tokens[position + 1 : position + 2]
            and tokens[position + 1].text == ">"
        ):
            break
        position += 1
    if position == at:
        raise Unreadable(f"no {kind}")
    return position


Bindings = dict[str, Bound]


def _match(
    elements: Sequence[Element], tokens: Sequence[Token], at: int, bound: Bindings
) -> int | None:
    """Match the elements at `at`; return the end, or `None` when they do not match."""
    for element in elements:
        if isinstance(element, Token):
            if at >= len(tokens) or tokens[at].text != element.text:
                return None
            at += 1
        elif isinstance(element, Var):
            try:
                end = _fragment(element.fragment, tokens, at)
            except Unreadable:
                return None
            bound[element.name] = Bound(list(tokens[at:end]))
            at = end
        elif isinstance(element, Delimited):
            if at >= len(tokens) or tokens[at].text != element.open.text:
                return None
            end = group_end(tokens, at)
            inner = tokens[at + 1 : end - 1]
            if _match(element.body, inner, 0, bound) != len(inner):
                return None
            at = end
        else:
            after = _repeat(element, tokens, at, bound)
            if after is None:
                return None
            at = after
    return at


def _repeat(element: Repeat, tokens: Sequence[Token], at: int, bound: Bindings) -> int | None:
    passes: list[Bindings] = []
    position = at
    while position <= len(tokens):
        start = position
        if passes and element.separator is not None:
            if position >= len(tokens) or tokens[position].text != element.separator.text:
                break
            position += 1
        one: Bindings = {}
        end = _match(element.body, tokens, position, one)
        if end is None or (end == position and not element.body):
            position = start
            break
        passes.append(one)
        position = end
        if element.operator == "?":
            break
    if element.operator == "+" and not passes:
        return None
    for name in _names(element.body):
        bound[name] = Bound(passes=[Bound(p[name].tokens, p[name].passes) for p in passes])
    return position


def _names(elements: Sequence[Element]) -> list[str]:
    names: list[str] = []
    for element in elements:
        if isinstance(element, Var):
            names.append(element.name)
        elif isinstance(element, Repeat | Delimited):
            names += _names(element.body)
    return names


def _transcribe(elements: Sequence[Element], bound: Bindings, out: list[Token]) -> None:
    for element in elements:
        if isinstance(element, Token):
            out.append(element)
        elif isinstance(element, Delimited):
            out.append(element.open)
            _transcribe(element.body, bound, out)
            out.append(element.close)
        elif isinstance(element, Var):
            if element.name == "crate":
                out += [Token("crate", 0, "name")]
            elif element.name not in bound or bound[element.name].passes is not None:
                raise Unreadable(f"the variable {element.name} is not bound here")
            else:
                out += bound[element.name].tokens
        else:
            used = [n for n in _names(element.body) if n in bound and bound[n].passes is not None]
            if not used:
                raise Unreadable("a repetition uses no repeated variable")
            counts = {len(bound[n].passes or []) for n in used}
            if len(counts) != 1:
                raise Unreadable("the repetitions of a template differ in length")
            for turn in range(counts.pop()):
                inner = dict(bound)
                for name in used:
                    inner[name] = (bound[name].passes or [])[turn]
                if turn and element.separator is not None:
                    out.append(element.separator)
                _transcribe(element.body, inner, out)


def _expand_once(macro: Macro, call: Sequence[Token]) -> list[Token]:
    for rule in macro.rules:
        bound: Bindings = {}
        if _match(rule.matcher, call, 0, bound) == len(call):
            out: list[Token] = []
            _transcribe(rule.body, bound, out)
            return out
    raise Unreadable("no rule matches the call")


def expand(
    tokens: Sequence[Token], macros: dict[str, Macro], gaps: list[Gap], depth: int = 0
) -> list[Token]:
    """Return the tokens with each call of a macro of `macros` replaced by its expansion."""
    out: list[Token] = []
    at = 0
    while at < len(tokens):
        token = tokens[at]
        call = (
            token.text in macros
            and token.kind == "name"
            and at + 2 < len(tokens)
            and tokens[at + 1].text == "!"
            and tokens[at + 2].text in OPEN
            and (
                at == 0
                or tokens[at - 1].text != ":"
                or (at >= 3 and tokens[at - 3].text in {"crate", "self", "super"})
            )
        )
        if not call:
            out.append(token)
            at += 1
            continue
        end = group_end(tokens, at + 2)
        try:
            if depth >= DEPTH:
                raise Unreadable("the call is nested too deep")
            made = _expand_once(macros[token.text], tokens[at + 3 : end - 1])
            out += expand(made, macros, gaps, depth + 1)
        except Unreadable as error:
            gaps.append(Gap(token.text, str(error)))
            out += tokens[at:end]
        at = end
    return out


def table(found: Sequence[Macro], gaps: list[Gap]) -> dict[str, Macro]:
    """Index the definitions by name. Two different definitions of a name are a gap."""
    named: dict[str, Macro] = {}
    clash: set[str] = set()
    for macro in found:
        if macro.name in named and named[macro.name].text != macro.text:
            clash.add(macro.name)
        named.setdefault(macro.name, macro)
    for name in sorted(clash):
        gaps.append(Gap(name, "two different definitions share the name"))
        del named[name]
    for macro in named.values():
        if macro.exported:
            gaps.append(Gap(macro.name, "an exported macro expands in other crates"))
    return named
