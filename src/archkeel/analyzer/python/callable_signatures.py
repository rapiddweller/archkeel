# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-bound synchronous contextmanager signatures; runtime effects remain separate."""

from __future__ import annotations

import ast
import sys
from importlib.machinery import BuiltinImporter, ModuleSpec
from types import BuiltinFunctionType, ModuleType, WrapperDescriptorType

from archkeel.ir.facts import (
    CPYTHON_NATIVE_RUNTIMES,
    ContextManagerReturn,
    ContextManagerSignature,
    CPythonABCBranch,
    CPythonPartialIntrinsic,
    NativeABCModule,
    NativeImplementation,
    NativeOrigin,
    NativeSignatureKind,
    ProviderBinding,
    ProviderBindingKind,
)
from archkeel.ir.facts_codec import RawEvidence, RawRecord, contextmanager_signature_data

from .source import (
    ParsedModule,
    add_evidence,
    is_proven_decorator,
    member_binding_closure,
    own_scope,
    provider_source_eligible,
    resolve_static_name,
    stable_direct_module_bindings,
)

_EXIT_BODY = """if typ is None:
    try:
        next(self.gen)
    except StopIteration:
        return False
    else:
        try:
            raise RuntimeError("generator didn't stop")
        finally:
            self.gen.close()
else:
    if value is None:
        value = typ()
    try:
        self.gen.throw(typ, value, traceback)
    except StopIteration as exc:
        return exc is not value
    except RuntimeError as exc:
        if exc is value:
            exc.__traceback__ = traceback
            return False
        if isinstance(value, StopIteration) and exc.__cause__ is value:
            value.__traceback__ = traceback
            return False
        raise
    except BaseException as exc:
        if exc is not value:
            raise
        exc.__traceback__ = traceback
        return False
    try:
        raise RuntimeError("generator didn't stop after throw()")
    finally:
        self.gen.close()
"""


def _body(node: ast.FunctionDef | ast.ClassDef) -> list[ast.stmt]:
    nodes = node.body
    if (
        nodes
        and isinstance(nodes[0], ast.Expr)
        and isinstance(nodes[0].value, ast.Constant)
        and isinstance(nodes[0].value.value, str)
    ):
        nodes = nodes[1:]
    return nodes


def _equal(nodes: list[ast.stmt], expected: str) -> bool:
    return ast.dump(ast.Module(body=nodes, type_ignores=[])) == ast.dump(ast.parse(expected))


def _declared(
    tree: ast.Module, name: str, cls: type[ast.FunctionDef] | type[ast.ClassDef]
) -> ast.FunctionDef | ast.ClassDef | None:
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        and isinstance(node, cls)
        and node.name == name
    ]
    return matches[0] if len(matches) == 1 else None


def _stores(tree: ast.Module, name: str) -> list[ast.AST]:
    found: list[ast.AST] = []

    def walk(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                found.append(node)
            return
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and node.id == name
        ):
            found.append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == name or alias.name == "*":
                    found.append(node)
        for child in ast.iter_child_nodes(node):
            walk(child)

    for node in tree.body:
        walk(node)
    return found


def _constant_tuple(tree: ast.Module, name: str) -> tuple[str, ...] | None:
    candidates = _stores(tree, name)
    if len(candidates) != 1 or not isinstance(candidates[0], ast.Name):
        return None
    statements = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
    ]
    if len(statements) != 1:
        return None
    try:
        value = ast.literal_eval(statements[0].value)
    except (ValueError, TypeError):
        return None
    return value if type(value) is tuple and all(type(part) is str for part in value) else None


def _imported(tree: ast.Module, local: str) -> tuple[str, str] | None:
    candidates = _stores(tree, local)
    if len(candidates) != 1 or not isinstance(candidates[0], ast.ImportFrom):
        return None
    statement = candidates[0]
    if statement.level or statement.module is None:
        return None
    alias = next((a for a in statement.names if (a.asname or a.name) == local), None)
    return (statement.module, alias.name) if alias else None


def _partial_route(tree: ast.Module, local: str) -> bool:
    candidates = _stores(tree, local)
    if (
        len(candidates) != 2
        or not isinstance(candidates[0], ast.ClassDef)
        or not isinstance(candidates[1], ast.ImportFrom)
    ):
        return False
    target = candidates[1]
    # Python 3.14 imports Placeholder in the same statement; partial comes first, so it binds first.
    if (
        target.module != "_functools"
        or target.level
        or target.names[0].name != "partial"
        or target.names[0].asname is not None
    ):
        return False
    enclosing = [node for node in tree.body if isinstance(node, ast.Try) and target in node.body]
    if len(enclosing) != 1:
        return False
    attempt = enclosing[0]
    return (
        attempt.body == [target]
        and not attempt.orelse
        and not attempt.finalbody
        and len(attempt.handlers) == 1
        and isinstance(attempt.handlers[0].type, ast.Name)
        and attempt.handlers[0].type.id == "ImportError"
        and attempt.handlers[0].name is None
        and len(attempt.handlers[0].body) == 1
        and isinstance(attempt.handlers[0].body[0], ast.Pass)
    )


def _simple_args(node: ast.FunctionDef, count: int, defaults: int = 0) -> bool:
    args = node.args
    return (
        len(args.args) == count
        and len(args.defaults) == defaults
        and not (
            args.posonlyargs or args.kwonlyargs or args.kw_defaults or args.vararg or args.kwarg
        )
    )


def _updater(tree: ast.Module, node: ast.FunctionDef) -> bool:
    if node.decorator_list or len(_stores(tree, node.name)) != 1 or not _simple_args(node, 4, 2):
        return False
    wrapper, wrapped, assigned, updated = [arg.arg for arg in node.args.args]
    if not all(isinstance(default, ast.Name) for default in node.args.defaults):
        return False
    attrs, updates = [
        _constant_tuple(tree, default.id)
        for default in node.args.defaults
        if isinstance(default, ast.Name)
    ]
    if (
        attrs is None
        or updates != ("__dict__",)
        or not set(attrs)
        <= {
            "__module__",
            "__name__",
            "__qualname__",
            "__doc__",
            "__annotations__",
            # Python 3.14 copies the lazy annotation function instead of the annotations (PEP 649).
            "__annotate__",
            "__type_params__",
        }
    ):
        return False
    return _equal(
        _body(node),
        f"""for attr in {assigned}:
    try:
        value = getattr({wrapped}, attr)
    except AttributeError:
        pass
    else:
        setattr({wrapper}, attr, value)
for attr in {updated}:
    getattr({wrapper}, attr).update(getattr({wrapped}, attr, {{}}))
{wrapper}.__wrapped__ = {wrapped}
return {wrapper}
""",
    )


def _wraps(
    tree: ast.Module, node: ast.FunctionDef, intrinsic: CPythonPartialIntrinsic | None
) -> ast.FunctionDef | None:
    nodes = _body(node)
    if (
        intrinsic is None
        or node.decorator_list
        or len(_stores(tree, node.name)) != 1
        or not _simple_args(node, 3, 2)
        or len(nodes) != 1
        or not isinstance(nodes[0], ast.Return)
        or not isinstance(nodes[0].value, ast.Call)
    ):
        return None
    call = nodes[0].value
    if (
        not isinstance(call.func, ast.Name)
        or len(call.args) != 1
        or not isinstance(call.args[0], ast.Name)
    ):
        return None
    wrapped, assigned, updated = [arg.arg for arg in node.args.args]
    target = _declared(tree, call.args[0].id, ast.FunctionDef)
    proven = (
        isinstance(target, ast.FunctionDef)
        and _updater(tree, target)
        and _partial_route(tree, call.func.id)
        and _equal(
            nodes,
            f"return {call.func.id}({target.name}, wrapped={wrapped}, "
            f"assigned={assigned}, updated={updated})",
        )
        and ast.dump(ast.Tuple(elts=node.args.defaults, ctx=ast.Load()))
        == ast.dump(ast.Tuple(elts=target.args.defaults, ctx=ast.Load()))
    )

    return target if proven and isinstance(target, ast.FunctionDef) else None


def _method(node: ast.ClassDef, name: str) -> ast.FunctionDef | None:
    found = [
        child
        for child in node.body
        if isinstance(child, ast.FunctionDef) and child.name == name and not child.decorator_list
    ]
    return found[0] if len(found) == 1 else None


def _parameters(node: ast.FunctionDef, signature: str) -> bool:
    expected = ast.parse(f"def f{signature}: pass").body[0]
    return isinstance(expected, ast.FunctionDef) and ast.dump(node.args) == ast.dump(expected.args)


def _generator_storage(base: ast.ClassDef) -> bool:
    init = _method(base, "__init__")
    return (
        init is not None
        and _parameters(init, "(self, func, args, kwds)")
        and _equal(
            _body(init),
            """self.gen = func(*args, **kwds)
self.func, self.args, self.kwds = func, args, kwds
doc = getattr(func, '__doc__', None)
if doc is None:
    doc = type(self).__doc__
self.__doc__ = doc
""",
        )
    )


def _wrapper(tree: ast.Module, node: ast.ClassDef) -> bool:
    if (
        node.decorator_list
        or node.keywords
        or len(node.bases) != 3
        or not all(isinstance(base, ast.Name) for base in node.bases)
        or len(_stores(tree, node.name)) != 1
    ):
        return False
    bases = [item.id for item in node.bases if isinstance(item, ast.Name)]
    base = _declared(tree, bases[0], ast.ClassDef)
    decorator = _declared(tree, bases[2], ast.ClassDef)
    enter, exit = _method(node, "__enter__"), _method(node, "__exit__")
    if (
        not isinstance(base, ast.ClassDef)
        or not isinstance(decorator, ast.ClassDef)
        or enter is None
        or exit is None
    ):
        return False
    recreate, apply = _method(base, "_recreate_cm"), _method(decorator, "__call__")
    if not _generator_storage(base) or recreate is None or apply is None:
        return False
    if (
        not _parameters(enter, "(self)")
        or not _parameters(exit, "(self, typ, value, traceback)")
        or not _parameters(recreate, "(self)")
        or not _parameters(apply, "(self, func)")
    ):
        return False
    abstract = _declared(tree, bases[1], ast.ClassDef)
    if not isinstance(abstract, ast.ClassDef) or len(_stores(tree, abstract.name)) != 1:
        return False
    if {child.name for child in _body(node) if isinstance(child, ast.FunctionDef)} != {
        "__enter__",
        "__exit__",
    } or any(not isinstance(child, ast.FunctionDef) for child in _body(node)):
        return False
    if not _equal(_body(recreate), "return self.__class__(self.func, self.args, self.kwds)"):
        return False
    if not _equal(
        _body(enter),
        """del self.args, self.kwds, self.func
try:
    return next(self.gen)
except StopIteration:
    raise RuntimeError("generator didn't yield") from None
""",
    ):
        return False
    # Python 3.12 deprecated the three-argument generator throw, so contextlib passes only value.
    expected_exit = (
        _EXIT_BODY
        if sys.version_info[:2] == (3, 11)
        else _EXIT_BODY.replace("self.gen.throw(typ, value, traceback)", "self.gen.throw(value)")
    )
    if not _equal(_body(exit), expected_exit):
        return False
    if not _closed_class(base, {"__init__", "_recreate_cm"}, ()) or not _closed_class(
        decorator, {"_recreate_cm", "__call__"}, ("object",)
    ):
        return False
    decorator_recreate = _method(decorator, "_recreate_cm")
    if decorator_recreate is None or not _equal(_body(decorator_recreate), "return self"):
        return False
    return _equal(
        _body(apply),
        """@wraps(func)
def inner(*args, **kwds):
    with self._recreate_cm():
        return func(*args, **kwds)
return inner
""",
    )


def _closed_class(node: ast.ClassDef, members: set[str], bases: tuple[str, ...]) -> bool:
    return (
        not node.decorator_list
        and not node.keywords
        and tuple(ast.unparse(base) for base in node.bases) == bases
        and all(
            isinstance(child, ast.FunctionDef) and not child.decorator_list for child in _body(node)
        )
        and {child.name for child in _body(node) if isinstance(child, ast.FunctionDef)} == members
        and len(_body(node)) == len(members)
    )


def _builtin_module(name: str) -> ModuleType | None:
    module = sys.modules.get(name)
    if type(module) is not ModuleType or name not in sys.builtin_module_names:
        return None
    try:
        _fallback = module.__getattr__
    except AttributeError:
        pass
    else:
        return None
    try:
        spec = module.__spec__
    except AttributeError:
        return None
    if not isinstance(spec, ModuleSpec):
        return None
    return (
        module
        if spec.name == name
        and spec.origin == "built-in"
        and isinstance(spec.loader, type)
        and spec.loader is BuiltinImporter
        else None
    )


def _partial_intrinsic() -> CPythonPartialIntrinsic | None:
    if sys.implementation.name != "cpython" or sys.version_info[:2] not in CPYTHON_NATIVE_RUNTIMES:
        return None
    module = _builtin_module("_functools")
    if module is None:
        return None
    try:
        member = module.partial
    except AttributeError:
        return None
    if type(member) is not type or member.__module__ != "functools" or member.__name__ != "partial":
        return None
    new, call = member.__new__, member.__call__
    if (
        not isinstance(new, BuiltinFunctionType)
        or new.__self__ is not member
        or not isinstance(call, WrapperDescriptorType)
        or call.__objclass__ is not member
    ):
        return None
    return CPythonPartialIntrinsic(
        NativeSignatureKind.PARTIAL,
        NativeImplementation.CPYTHON,
        ".".join(map(str, sys.version_info[:3])),
        sys.implementation.cache_tag or "",
        NativeOrigin.BUILTIN,
    )


_ABC_MEMBERS = (
    "get_cache_token",
    "_abc_init",
    "_abc_register",
    "_abc_instancecheck",
    "_abc_subclasscheck",
    "_get_dump",
    "_reset_registry",
    "_reset_caches",
)


def _abc_intrinsic() -> CPythonABCBranch | None:
    module = _builtin_module("_abc")
    if module is None:
        return None
    try:
        members = (
            module.get_cache_token,
            module._abc_init,
            module._abc_register,
            module._abc_instancecheck,
            module._abc_subclasscheck,
            module._get_dump,
            module._reset_registry,
            module._reset_caches,
        )
    except AttributeError:
        return None
    for name, member in zip(_ABC_MEMBERS, members, strict=True):
        if (
            not isinstance(member, BuiltinFunctionType)
            or member.__module__ != "_abc"
            or member.__name__ != name
            or member.__self__ is not module
        ):
            return None
    return CPythonABCBranch(
        NativeSignatureKind.ABC, NativeABCModule.ABC, NativeOrigin.BUILTIN, _ABC_MEMBERS
    )


def _abc_source(module: ParsedModule) -> tuple[ast.AST, ...] | None:
    candidates = [
        node
        for node in module.tree.body
        if isinstance(node, ast.Try)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.ImportFrom)
        and node.body[0].module == "_abc"
    ]
    cls = _declared(module.tree, "ABC", ast.ClassDef)
    if (
        len(candidates) != 1
        or not isinstance(cls, ast.ClassDef)
        or cls.decorator_list
        or cls.bases
        or len(cls.keywords) != 1
        or cls.keywords[0].arg != "metaclass"
        or not isinstance(cls.keywords[0].value, ast.Name)
        or not _equal(_body(cls), "__slots__ = ()")
    ):
        return None
    attempt = candidates[0]
    imported = attempt.body[0]
    if (
        not isinstance(imported, ast.ImportFrom)
        or imported.level
        or tuple(alias.name for alias in imported.names) != _ABC_MEMBERS
        or any(alias.asname for alias in imported.names)
        or attempt.finalbody
        or len(attempt.handlers) != 1
        or len(attempt.orelse) != 1
    ):
        return None
    handler = attempt.handlers[0]
    if (
        not isinstance(handler.type, ast.Name)
        or handler.type.id != "ImportError"
        or handler.name is not None
        or not _equal(
            handler.body, "from _py_abc import ABCMeta, get_cache_token\nABCMeta.__module__ = 'abc'"
        )
    ):
        return None
    meta = attempt.orelse[0]
    members = {
        "__new__",
        "register",
        "__instancecheck__",
        "__subclasscheck__",
        "_dump_registry",
        "_abc_registry_clear",
        "_abc_caches_clear",
    }
    if (
        not isinstance(meta, ast.ClassDef)
        or meta.name != cls.keywords[0].value.id
        or not _closed_class(meta, members, ("type",))
    ):
        return None
    new = _method(meta, "__new__")
    abstract = _declared(module.tree, "abstractmethod", ast.FunctionDef)
    if (
        new is None
        or not _parameters(new, "(mcls, name, bases, namespace, /, **kwargs)")
        or not _equal(
            _body(new),
            "cls = super().__new__(mcls, name, bases, namespace, **kwargs)\n"
            "_abc_init(cls)\nreturn cls",
        )
        or not isinstance(abstract, ast.FunctionDef)
        or abstract.decorator_list
        or not _parameters(abstract, "(funcobj)")
        or not _equal(_body(abstract), "funcobj.__isabstractmethod__ = True\nreturn funcobj")
    ):
        return None
    return cls, meta, attempt, abstract


def _abstract_base(module: ParsedModule, node: ast.ClassDef, abc: ParsedModule) -> bool:
    if (
        node.decorator_list
        or node.keywords
        or len(node.bases) != 1
        or resolve_static_name(module, node.bases[0]) != f"{abc.module}.ABC"
        or _imported(module.tree, "GenericAlias") != ("types", "GenericAlias")
        or "GenericAlias" not in stable_direct_module_bindings(module)
        or not _headers_unmodified(module, {"GenericAlias"})
    ):
        return False
    members = _body(node)
    # Python 3.13 adds empty slots; they change only the instance layout.
    if len(members) == 5 and _equal([members[1]], "__slots__ = ()"):
        members = [members[0], *members[2:]]
    if len(members) != 4 or not _equal(
        [members[0]], "__class_getitem__ = classmethod(GenericAlias)"
    ):
        return False
    enter, exit, hook = (
        [child for child in members[1:] if isinstance(child, ast.FunctionDef)]
        if all(isinstance(child, ast.FunctionDef) for child in members[1:])
        else (None, None, None)
    )
    if (
        enter is None
        or exit is None
        or hook is None
        or enter.name != "__enter__"
        or exit.name != "__exit__"
        or hook.name != "__subclasshook__"
    ):
        return False
    return (
        not enter.decorator_list
        and _parameters(enter, "(self)")
        and _parameters(exit, "(self, exc_type, exc_value, traceback)")
        and _parameters(hook, "(cls, C)")
        and _equal(_body(enter), "return self")
        and len(exit.decorator_list) == 1
        and resolve_static_name(module, exit.decorator_list[0]) == f"{abc.module}.abstractmethod"
        and _equal(_body(exit), "return None")
        and len(hook.decorator_list) == 1
        and isinstance(hook.decorator_list[0], ast.Name)
        and hook.decorator_list[0].id == "classmethod"
        and _equal(
            _body(hook),
            f"if cls is {node.name}:\n"
            "    return _collections_abc._check_methods(C, '__enter__', '__exit__')\n"
            "return NotImplemented",
        )
    )


def _factory_parts(
    module: ParsedModule, name: str
) -> tuple[ast.FunctionDef, ast.FunctionDef, ast.ClassDef] | None:
    factory = _declared(module.tree, name, ast.FunctionDef)
    if (
        not isinstance(factory, ast.FunctionDef)
        or factory.decorator_list
        or not _simple_args(factory, 1)
        or name not in stable_direct_module_bindings(module)
    ):
        return None
    nodes = _body(factory)
    if len(nodes) != 2:
        return None
    helper, result = nodes
    if not isinstance(helper, ast.FunctionDef) or not isinstance(result, ast.Return):
        return None
    if (
        not isinstance(result.value, ast.Name)
        or result.value.id != helper.name
        or len(helper.decorator_list) != 1
    ):
        return None
    args, statements = helper.args, _body(helper)
    if (
        args.args
        or args.posonlyargs
        or args.kwonlyargs
        or args.defaults
        or args.kw_defaults
        or args.vararg is None
        or args.kwarg is None
        or len(statements) != 1
        or not isinstance(statements[0], ast.Return)
        or not isinstance(statements[0].value, ast.Call)
    ):
        return None
    call = statements[0].value
    if not isinstance(call.func, ast.Name):
        return None
    constructed = _declared(module.tree, call.func.id, ast.ClassDef)
    func = factory.args.args[0].arg
    if not isinstance(constructed, ast.ClassDef) or not _equal(
        statements, f"return {constructed.name}({func}, {args.vararg.arg}, {args.kwarg.arg})"
    ):
        return None
    decorate = helper.decorator_list[0]
    if (
        not isinstance(decorate, ast.Call)
        or not isinstance(decorate.func, ast.Name)
        or len(decorate.args) != 1
        or ast.unparse(decorate.args[0]) != func
        or decorate.keywords
    ):
        return None
    return factory, helper, constructed


def contextmanager_dependency_bindings(
    modules: list[ParsedModule], wanted: set[str]
) -> frozenset[str]:
    """Demand only real source imports and declarations used by a candidate factory."""
    by_name = {module.module: module for module in modules}
    demanded: set[str] = set()
    for qualified in wanted:
        module_name, _, name = qualified.rpartition(".")
        module = by_name.get(module_name)
        parts = _factory_parts(module, name) if module is not None else None
        if module is None or parts is None:
            continue
        _factory, helper, constructed = parts
        decorate = helper.decorator_list[0]
        if not isinstance(decorate, ast.Call) or not isinstance(decorate.func, ast.Name):
            continue
        demanded.add(f"{module.module}.{decorate.func.id}")
        demanded.add(f"{module.module}.{constructed.name}")
        demanded.update(
            f"{module.module}.{base.id}" for base in constructed.bases if isinstance(base, ast.Name)
        )
        for base in constructed.bases:
            cls = (
                _declared(module.tree, base.id, ast.ClassDef)
                if isinstance(base, ast.Name)
                else None
            )
            if isinstance(cls, ast.ClassDef):
                demanded.update(
                    f"{module.module}.{b.value.id}"
                    for b in cls.bases
                    if isinstance(b, ast.Attribute) and isinstance(b.value, ast.Name)
                )
        origin = resolve_static_name(module, decorate.func)
        target_module, _, target_name = origin.rpartition(".")
        tools = by_name.get(target_module)
        target = _declared(tools.tree, target_name, ast.FunctionDef) if tools is not None else None
        if isinstance(target, ast.FunctionDef):
            returns = _body(target)
            if (
                len(returns) == 1
                and isinstance(returns[0], ast.Return)
                and isinstance(returns[0].value, ast.Call)
                and returns[0].value.args
                and isinstance(returns[0].value.args[0], ast.Name)
            ):
                demanded.update((origin, f"{target_module}.{returns[0].value.args[0].id}"))
    return frozenset(demanded)


def _terminal(name: str, bindings: dict[str, ProviderBinding]) -> ProviderBinding | None:
    seen: set[str] = set()
    while name not in seen:
        seen.add(name)
        binding = bindings.get(name)
        if binding is None:
            return None
        if binding.kind is not ProviderBindingKind.ALIAS:
            return binding
        if binding.target is None:
            return None
        name = binding.target
    return None


def _unshadowed(module: ParsedModule, names: tuple[str, ...]) -> bool:
    return not any(
        name in module.scope_bound_names or name in module.global_names for name in names
    )


def _headers_unmodified(
    module: ParsedModule, names: set[str], inactive: tuple[ast.AST, ...] = ()
) -> bool:
    aliases = member_binding_closure(module.scope_nodes, names, member_surface=False)
    skipped = {child for branch in inactive for child in ast.walk(branch)}
    for node in module.scope_nodes:
        if node in skipped:
            continue
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if any(
                isinstance(part, ast.Name) and part.id in aliases for part in ast.walk(node.value)
            ):
                return False
        if (
            isinstance(node, ast.Call)
            and node.args
            and resolve_static_name(module, node.func)
            in {
                "setattr",
                "builtins.setattr",
                "delattr",
                "builtins.delattr",
                "vars",
                "builtins.vars",
            }
        ):
            if any(
                isinstance(part, ast.Name) and part.id in aliases for part in ast.walk(node.args[0])
            ):
                return False
    return True


def _abc_support(
    module: ParsedModule, abstract: ast.ClassDef, providers: dict[str, ParsedModule]
) -> list[tuple[ParsedModule, ast.AST]]:
    if len(abstract.bases) != 1:
        return []
    abc_name = resolve_static_name(module, abstract.bases[0]).rpartition(".")[0]
    abc = providers.get(abc_name)
    nodes = (
        _abc_source(abc)
        if abc is not None and _unshadowed(abc, ("type", "super", "ImportError"))
        else None
    )
    if (
        abc is None
        or nodes is None
        or not _abstract_base(module, abstract, abc)
        or not _headers_unmodified(
            abc,
            {"ABC", "ABCMeta", "abstractmethod"},
            tuple(
                handler for node in nodes if isinstance(node, ast.Try) for handler in node.handlers
            ),
        )
    ):
        return []
    return [(abc, node) for node in nodes]


def _chain_builtins(module: ParsedModule, tools: ParsedModule) -> bool:
    return _unshadowed(
        module,
        (
            "getattr",
            "type",
            "next",
            "object",
            "RuntimeError",
            "StopIteration",
            "BaseException",
            "isinstance",
            "classmethod",
            "NotImplemented",
        ),
    ) and _unshadowed(tools, ("getattr", "setattr", "ImportError"))


def _chain_support(
    module: ParsedModule,
    parts: tuple[ast.FunctionDef, ast.FunctionDef, ast.ClassDef],
    providers: dict[str, ParsedModule],
    bindings: dict[str, ProviderBinding],
    partial: CPythonPartialIntrinsic,
) -> list[tuple[ParsedModule, ast.AST]]:
    factory, helper, constructed = parts
    decorate = helper.decorator_list[0]
    if not isinstance(decorate, ast.Call) or not isinstance(decorate.func, ast.Name):
        return []
    origin = _terminal(resolve_static_name(module, decorate.func), bindings)
    tools = providers.get(origin.qualified_name.rpartition(".")[0]) if origin is not None else None
    target = (
        _declared(tools.tree, origin.qualified_name.rpartition(".")[2], ast.FunctionDef)
        if tools is not None and origin is not None
        else None
    )
    update = (
        _wraps(tools.tree, target, partial)
        if tools is not None and isinstance(target, ast.FunctionDef)
        else None
    )
    if (
        origin is None
        or tools is None
        or not isinstance(target, ast.FunctionDef)
        or update is None
        or not is_proven_decorator(
            module, decorate, factory, None, frozenset({origin.qualified_name})
        )
    ):
        return []
    if not _chain_builtins(module, tools) or not _wrapper(module.tree, constructed):
        return []
    bases = [
        _declared(module.tree, base.id, ast.ClassDef)
        for base in constructed.bases
        if isinstance(base, ast.Name)
    ]
    if len(bases) != 3 or not all(isinstance(base, ast.ClassDef) for base in bases):
        return []
    abstract = bases[1]
    if not isinstance(abstract, ast.ClassDef) or len(abstract.bases) != 1:
        return []
    abc_nodes = _abc_support(module, abstract, providers)
    if not abc_nodes or not _headers_unmodified(
        module,
        {
            factory.name,
            helper.name,
            constructed.name,
            *[base.name for base in bases if isinstance(base, ast.ClassDef)],
        },
    ):
        return []
    return (
        [
            (module, node)
            for node in (
                factory,
                helper,
                constructed,
                *[base for base in bases if isinstance(base, ast.ClassDef)],
            )
        ]
        + [(tools, target), (tools, update)]
        + abc_nodes
    )


def _iterator_payload(
    module: ParsedModule,
    node: ast.FunctionDef,
    providers: dict[str, ParsedModule],
    bindings: dict[str, ProviderBinding],
) -> tuple[str, list[tuple[ParsedModule, ast.AST]]] | None:
    annotation = node.returns
    if not isinstance(annotation, ast.Subscript):
        return None
    origin = _terminal(resolve_static_name(module, annotation.value), bindings)
    if (
        origin is None
        or origin.qualified_name != "_collections_abc.Iterator"
        or origin.kind is not ProviderBindingKind.CLASS
        or not is_proven_decorator(
            module,
            annotation.value,
            node,
            None,
            frozenset({resolve_static_name(module, annotation.value)}),
        )
    ):
        return None
    owner = providers.get(origin.qualified_name.rpartition(".")[0])
    cls = (
        _declared(owner.tree, origin.qualified_name.rpartition(".")[2], ast.ClassDef)
        if owner is not None
        else None
    )
    if (
        owner is None
        or not provider_source_eligible(owner)
        or not isinstance(cls, ast.ClassDef)
        or cls.decorator_list
        or cls.keywords
        or len(cls.bases) != 1
    ):
        return None
    iterator, advance = (
        _method(cls, "__iter__"),
        next(
            (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__next__"), None
        ),
    )
    if (
        iterator is None
        or advance is None
        or not _equal(_body(iterator), "return self")
        or not _equal(_body(advance), "raise StopIteration")
        or len(advance.decorator_list) != 1
        or resolve_static_name(owner, advance.decorator_list[0]) != "abc.abstractmethod"
    ):
        return None
    generator = any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in own_scope(node))
    return (
        (ast.unparse(annotation.slice), [(owner, cls)]) if generator and owner is not None else None
    )


def contextmanager_signatures(
    modules: list[ParsedModule],
    providers: list[ParsedModule],
    symbols: list[RawRecord],
    bindings: tuple[ProviderBinding, ...],
    evidence: dict[str, RawEvidence],
) -> None:
    """Attach a distinct effective return only after all native source witnesses close."""
    partial, abc = _partial_intrinsic(), _abc_intrinsic()
    if partial is None or abc is None:
        return
    by_provider = {module.module: module for module in providers}
    by_module = {module.module: module for module in modules}
    by_binding = {binding.qualified_name: binding for binding in bindings}
    for symbol in symbols:
        data = symbol["data"]
        module = by_module.get(data["module"])
        node = _declared(module.tree, data["name"], ast.FunctionDef) if module is not None else None
        if (
            module is None
            or not isinstance(node, ast.FunctionDef)
            or symbol["kind"] != "function"
            or data.get("source_binding_unique") is not True
            or data.get("namespace_bound") is not True
            or len(node.decorator_list) != 1
            or isinstance(node.decorator_list[0], ast.Call)
        ):
            continue
        target = resolve_static_name(module, node.decorator_list[0])
        origin = _terminal(target, by_binding)
        owner = (
            by_provider.get(origin.qualified_name.rpartition(".")[0])
            if origin is not None
            else None
        )
        parts = (
            _factory_parts(owner, origin.qualified_name.rpartition(".")[2])
            if owner is not None and origin is not None
            else None
        )
        if (
            origin is None
            or owner is None
            or parts is None
            or not is_proven_decorator(
                module, node.decorator_list[0], node, None, frozenset({target})
            )
        ):
            continue
        support = _chain_support(owner, parts, by_provider, by_binding, partial)
        payload = _iterator_payload(module, node, by_provider, by_binding)
        if not support or payload is None:
            continue
        identities = {origin.qualified_name, f"{owner.module}.{parts[2].name}"}
        if any(name not in by_binding for name in identities):
            continue
        references = [
            add_evidence(evidence, provider, child) for provider, child in (*support, *payload[1])
        ]
        references.extend(symbol["evidence_ids"])
        references.extend(
            binding.evidence_id for binding in bindings if binding.qualified_name in identities
        )
        signature = ContextManagerSignature(
            NativeSignatureKind.CONTEXTMANAGER,
            origin.qualified_name,
            ContextManagerReturn(f"{owner.module}.{parts[2].name}", payload[0]),
            tuple(sorted(set(references))),
            partial,
            abc,
        )
        data["contextmanager_signature"] = contextmanager_signature_data(signature)
