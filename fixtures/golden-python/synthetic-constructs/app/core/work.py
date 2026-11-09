from __future__ import annotations

from typing import Any, Callable, TypeAlias, cast

from app.util.helpers import build

Handler: TypeAlias = Callable[..., Any]
LIMIT = 3
dynamic = [LIMIT]


def risky(value: Any, handler: Callable[..., Any], payload: dict[str, Any], marker: object) -> int:
    assert value is not None
    name = getattr(value, "name", None)
    if hasattr(value, "flag"):
        setattr(value, "flag", 1)
    delattr(value, "flag")
    state = vars(value)
    table = value.__dict__
    if name == "primary":
        build("a", LIMIT)
    result = cast(int, eval("1 + 1"))  # type: ignore[misc]
    exec("pass")
    try:
        handler(state, table, payload, marker)
    except Exception:
        pass
    return result + 1 * 2


def stub():
    ...


class Port:
    def method(self, unused, used):
        local = 1
        return used
