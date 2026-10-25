# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""JSX attribute names name props, never bindings; a same-named variable is still a reference."""

import pytest

from archkeel.analyzer.typescript.parse import parse


@pytest.mark.parametrize(
    "source",
    [
        'export const App = () => <button className="x" title="t" onClick={() => 1} />;',
        'export const App = () => <svg aria:label="a" data-x="1" />;',
        'export const App = () => <Box title={"t"}>{"child"}</Box>;',
    ],
)
def test_jsx_attribute_names_create_no_site(source):
    expressions = {site.expression for site in parse("src/App.tsx", source.encode()).sites}
    assert not {"className", "title", "onClick", "aria", "label", "data-x"} & expressions


def test_same_named_variable_is_still_a_reference_beside_a_jsx_attribute():
    source = (
        b'const title = 1;\nexport const App = () => { title; return <button title="t" />; };\n'
    )
    sites = [site for site in parse("src/App.tsx", source).sites if site.expression == "title"]
    assert [site.span.line for site in sites] == [2]
