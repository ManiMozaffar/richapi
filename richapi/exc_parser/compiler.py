import ast
import builtins
import collections
import functools
import inspect
import logging
import sys
import sysconfig
import textwrap
import types
import typing
import weakref
from importlib.util import find_spec
from types import ModuleType
from typing import (
    Annotated,
    Callable,
    Generic,
    NamedTuple,
    NewType,
    Optional,
    Union,
)

import typing_extensions
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class RaisedExceptionInfo(NamedTuple):
    exception: type[Exception] | None
    raise_ast: ast.Raise


class RaisedHTTPExceptionInfo(NamedTuple):
    exception: type[StarletteHTTPException]
    raise_ast: ast.Raise


def not_supported(
    value: typing.NoReturn,
) -> typing.NoReturn: ...  # don't raise any exceptions just type checking


# Extending this list will raise typing checks on all codes.
# To support a new node, just add it to list and resolve all typing checks.

SupportedAstNodes = Union[
    ast.Call,  # Function call
    ast.FunctionDef,  # Function definition
    ast.AsyncFunctionDef,  # Async function definition
    ast.ClassDef,  # Class definition
    ast.Raise,  # Raise statement
    ast.Assign,  # Assignment statement
    ast.Attribute,  # Attribute access
    ast.Name,  # Variable name
    ast.Await,  # Await expression
]

NodeIdentifier = NewType("NodeIdentifier", str)
"""Branded type that represents a node identifier that can be used a key in a dictionary."""


def get_node_identifier(node: ast.Name) -> NodeIdentifier:
    """Get the identifier of the given node."""

    return NodeIdentifier(node.id)


def is_in_module(module: str, target_modules: list[str]) -> bool:
    """
    Module is like 'module.submodule.Class.method'
    target modules are like ['module.submodule', 'module.submodule2']
    """
    if module == "__main__":  # always look into main module
        return True

    if "." not in module:
        module = module + "."  # to match the module.* pattern

    for target in target_modules:
        if module.startswith(target):
            return True
    return False


_tree_cache: dict = {}
_def_index_cache: dict[int, tuple[ast.AST, dict[tuple[str, str], ast.AST]]] = {}


def _parse_source(obj) -> ast.Module:
    """`ast.parse(inspect.getsource(obj))`, cached per object until `ExceptionFinder.clear_cache()`."""
    try:
        return _tree_cache[obj]
    except KeyError:
        pass
    except TypeError:  # unhashable object, don't cache
        return ast.parse(_getsource(obj))

    tree = _top_level_class_tree(obj) if inspect.isclass(obj) else None
    if tree is None:
        tree = ast.parse(_getsource(obj))
    _tree_cache[obj] = tree
    return tree


def _top_level_class_tree(cls: type) -> Optional[ast.Module]:
    """
    For a class defined at the top level of its module, what `ast.parse(inspect.getsource(cls))`
    would produce, built from the already parsed module instead of re-tokenizing and re-parsing.
    None means: use the regular path (nested classes, odd cases, errors).
    """
    module = inspect.getmodule(cls)
    if module is None:
        return None
    try:
        module_tree = _parse_source(module)
        if sys.version_info >= (3, 13):  # where inspect.getsource(cls) starts on 3.13+
            first_line = vars(cls).get("__firstlineno__")
            start = None if first_line is None else first_line - 1
        else:
            start = _class_line_index(module_tree).get(cls.__qualname__)
    except Exception:
        return None

    for node in getattr(module_tree, "body", ()):
        if isinstance(node, ast.ClassDef):
            first = node.decorator_list[0] if node.decorator_list else node
            if first.lineno - 1 == start:
                return ast.Module(body=[node], type_ignores=[])
    return None


def _getsource(obj) -> str:
    """
    Same as `inspect.getsource(obj)`. Before Python 3.13, `getsource(cls)` re-parses and walks the
    class's whole module for every class; this looks classes up in a per-module index instead.
    """
    if (
        sys.version_info >= (3, 13)
        or not inspect.isclass(obj)
        or (module := inspect.getmodule(obj)) is None
    ):
        return inspect.getsource(obj)

    try:
        lines, _ = inspect.findsource(module)
        line_number = _class_line_index(_parse_source(module)).get(obj.__qualname__)
    except Exception:
        return inspect.getsource(obj)  # anything odd: let stdlib decide (or raise)
    if line_number is None:
        return inspect.getsource(obj)  # not found: let stdlib decide (or raise)
    return "".join(inspect.getblock(lines[line_number:]))


_class_line_cache: dict[int, tuple[ast.AST, dict[str, int]]] = {}


def _child_nodes(node: ast.AST) -> list[ast.AST]:
    """`ast.iter_child_nodes` order, minus leaf nodes (`_LEAF_NODE_TYPES`), without its generators."""
    children: list[ast.AST] = []
    for field in node._fields:
        value = getattr(node, field, None)
        if isinstance(value, list):
            children.extend(
                item
                for item in value
                if isinstance(item, ast.AST) and type(item) not in _LEAF_NODE_TYPES
            )
        elif isinstance(value, ast.AST) and type(value) not in _LEAF_NODE_TYPES:
            children.append(value)
    return children


def _class_line_index(tree: ast.AST) -> dict[str, int]:
    """
    qualname -> 0-based first line of the class, following `inspect._ClassFinder` (Python 3.10-3.12):
    first match in traversal order, decorators included, functions add a `<locals>` level.
    """
    entry = _class_line_cache.get(id(tree))
    if entry is not None and entry[0] is tree:
        return entry[1]

    index: dict[str, int] = {}

    def walk(node: ast.AST, stack: list[str]):
        for child in _child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, [*stack, child.name, "<locals>"])
            elif isinstance(child, ast.ClassDef):
                inner = [*stack, child.name]
                first = child.decorator_list[0] if child.decorator_list else child
                index.setdefault(".".join(inner), first.lineno - 1)
                walk(child, inner)
            else:
                walk(child, stack)

    walk(tree, [])
    _class_line_cache[id(tree)] = (tree, index)
    return index


_returned_exc_cache: dict = {}

# Globals of the function each collected raise sits in, so status/detail names can be looked up.
# A side table instead of a RaisedExceptionInfo field keeps `exc, raise_ast = info` unpacking working.
_raise_globals: "weakref.WeakKeyDictionary[ast.Raise, dict]" = (
    weakref.WeakKeyDictionary()
)


def get_raise_globals(raise_ast: ast.Raise) -> Optional[dict]:
    """Globals of the function `raise_ast` was collected from, if known."""
    return _raise_globals.get(raise_ast)


def _find_def(tree: ast.AST, kind: str, name: str) -> Optional[ast.AST]:
    """
    Same result as `_find_in_module` looking for a function ("func") or class ("class") by name,
    but walks each tree only once and then answers from an index.
    """
    entry = _def_index_cache.get(id(tree))
    if entry is None or entry[0] is not tree:
        index: dict[tuple[str, str], ast.AST] = {}
        todo = collections.deque([tree])  # breadth-first, same order as ast.walk
        while todo:
            node = todo.popleft()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                index.setdefault(("func", node.name), node)
            elif isinstance(node, ast.ClassDef):
                index.setdefault(("class", node.name), node)
            todo.extend(_child_nodes(node))
        entry = (tree, index)
        _def_index_cache[id(tree)] = entry
    return entry[1].get((kind, name))


def _get_tree(obj: Callable):
    to_search = obj
    if is_absolutely_callable_object(obj):
        to_search: Union[type, Callable] = (
            obj_type if (obj_type := type(obj)) is not type else obj
        )

    try:
        return _parse_source(to_search)
    except Exception as error:
        obj_name = obj.__name__ if hasattr(obj, "__name__") else obj.__str__()
        logger.debug(f"Failed to parse source code for {obj_name}", exc_info=error)
        return None


def find_explicit_exceptions(
    func: Callable,
    target_modules: list[str],
    should_search_module_pred: Union[Callable[[str], bool], None] = None,
) -> list[RaisedExceptionInfo]:
    """
    Analyze the given function and find all explicitly raised exceptions,
    including those in nested functions and class methods.

    Returns:
        A list of tuples where each tuple contains:
            - The exception class (or None if it couldn't be resolved)
            - The ast.Raise node
    """

    if should_search_module_pred is None:

        def should_search_module_pred_func(target):
            return is_in_module(target, target_modules)

        should_search_module_pred = should_search_module_pred_func

    module = inspect.getmodule(func)
    if module is None or _should_be_visited(module, should_search_module_pred) is False:
        return []

    tree = _get_tree(func)
    if tree is None:
        return []

    return _find_explicit_expection_recursively(func, should_search_module_pred, tree)


def get_func_name(func: Callable) -> str:
    return func.__name__ if hasattr(func, "__name__") else func.__str__()


def _find_all_class_exceptions(
    cls: Union[type, Callable],
    to_filter_predicate: Callable[[str], bool],
):
    cls_module = inspect.getmodule(cls)
    if cls_module and is_stdlib(cls_module.__name__):
        return []
    if cls_module and to_filter_predicate(cls_module.__name__) is False:
        return []

    try:
        cls_tree = _parse_source(cls)
    except Exception as error:
        cls_name = cls.__name__ if hasattr(cls, "__name__") else cls.__str__()
        logger.info(
            f"Failed to parse source code for {cls_name}.__init__", exc_info=error
        )
        return []

    init_tree = _find_def(cls_tree, "func", "__init__")

    result: list[RaisedExceptionInfo] = []
    if init_tree is not None:
        result.extend(
            _find_explicit_expection_recursively(
                cls.__init__, to_filter_predicate, init_tree
            )
        )

    if hasattr(cls, "__call__"):
        # Not sure if __call__ was called or init, so check for both
        call_tree = _find_def(cls_tree, "func", "__call__")

        if call_tree is not None:
            result.extend(
                _find_explicit_expection_recursively(
                    getattr(cls, "__call__"), to_filter_predicate, call_tree
                )
            )

    return result


def is_absolutely_callable_object(obj: Callable) -> bool:
    return (
        inspect.isclass(type(obj))
        and (not inspect.isfunction(obj))
        and (not inspect.ismethod(obj))
    )


def _find_explicit_expection_recursively(
    func_obj: Callable,
    to_filter_predicate: Callable[[str], bool],
    tree: ast.AST,
) -> list[RaisedExceptionInfo]:
    if func_obj in ExceptionFinder.visited:
        return ExceptionFinder.visited[func_obj]

    module = inspect.getmodule(func_obj)
    if module is None or _should_be_visited(module, to_filter_predicate) is False:
        return []

    if is_absolutely_callable_object(func_obj):
        class_type: Union[type, Callable] = (
            obj_type if (obj_type := type(func_obj)) is not type else func_obj
        )
        return _find_all_class_exceptions(class_type, to_filter_predicate)

    # Mark as in-progress so (mutually) recursive calls stop here instead of recursing until RecursionError.
    ExceptionFinder.visited[func_obj] = []
    finder = ExceptionFinder(func_obj, to_filter_predicate)
    try:
        finder.visit(tree)
    except Exception as error:
        logger.exception(
            f"Failed to analyze function {get_func_name(func_obj)}.", exc_info=error
        )

    ExceptionFinder.visited[func_obj] = finder.exceptions
    return finder.exceptions


def _returned_exceptions(func: Callable) -> list[RaisedExceptionInfo]:
    """
    Exceptions `func` builds and returns (`return HTTPException(...)`), so `raise func()` resolves.
    Each one points at a synthetic `raise <returned call>` node, so status/detail extraction reads
    the returned call's arguments. Returns inside nested functions/classes are ignored.
    """
    func = getattr(func, "__func__", func)  # bound method -> function
    if not inspect.isfunction(func):
        return []
    if func in _returned_exc_cache:
        return _returned_exc_cache[func]

    result: list[RaisedExceptionInfo] = []
    _returned_exc_cache[func] = result
    try:
        func_ast = ast.parse(textwrap.dedent(inspect.getsource(func))).body[0]
    except Exception as error:
        logger.debug(f"Failed to parse source code for {func.__name__}", exc_info=error)
        return result

    todo = collections.deque(getattr(func_ast, "body", []))
    while todo:
        node = todo.popleft()
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            continue
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Call):
            exc_name = _extract_node_name(node.value, {})
            exc_type = exc_name and _exctact_type(exc_name, func.__globals__)
            if exc_type:
                raise_ast = ast.copy_location(
                    ast.Raise(exc=_inline_headers_call(node.value, func), cause=None),
                    node,
                )
                _raise_globals[raise_ast] = func.__globals__
                result.append(RaisedExceptionInfo(exc_type, raise_ast))
        todo.extend(ast.iter_child_nodes(node))
    return result


def _inline_headers_call(call: ast.Call, func: Callable) -> ast.Call:
    """
    `HTTPException(..., headers=self.make_headers())` -> a copy with the dict literal `make_headers`
    returns in place of the call, so header names can be read (FastAPI's HTTPBase does this).
    """
    for i, kwarg in enumerate(call.keywords):
        if kwarg.arg != "headers" or not isinstance(kwarg.value, ast.Call):
            continue
        method = _self_method(kwarg.value, func)
        method_def = _method_def(method) if method is not None else None
        for stmt in getattr(method_def, "body", []):
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                keywords = list(call.keywords)
                keywords[i] = ast.keyword(arg="headers", value=stmt.value)
                return ast.Call(func=call.func, args=call.args, keywords=keywords)
    return call


def _find_in_module(module: ast.Module, predicate: Callable[[ast.AST], bool]):
    for node in ast.walk(module):
        if predicate(node):
            return node
    return None


def _find_method_node_in_cls(cls: ast.ClassDef, method_name: str):
    for node in cls.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == method_name
        ):
            return node
    return None


def _self_method(call: ast.Call, func: Callable) -> Optional[Callable]:
    """
    The function behind `self.method()` or `cls.method()` inside `func`, looked up (MRO included)
    on the class `func` is defined in. Static and class methods come back as plain functions.
    """
    func_node = call.func
    if not (
        isinstance(func_node, ast.Attribute)
        and isinstance(func_node.value, ast.Name)
        and func_node.value.id in ("self", "cls")
    ):
        return None
    qual_names = getattr(func, "__qualname__", "").split(".")
    owner = func.__globals__.get(qual_names[-2]) if len(qual_names) > 1 else None
    method = getattr(owner, func_node.attr, None)
    return getattr(method, "__func__", method)


def _method_def(method: Callable) -> Optional[ast.AST]:
    """The def of a method, found in the class its `__qualname__` names."""
    owner_name, _, method_name = getattr(method, "__qualname__", "").rpartition(".")
    module = inspect.getmodule(method)
    if module is None or not owner_name or "." in owner_name:
        return None
    try:
        tree = _parse_source(module)
    except Exception as error:
        logger.debug(f"Failed to parse source code for {owner_name}", exc_info=error)
        return None
    cls_ast = _find_def(tree, "class", owner_name)
    if cls_ast is None:
        return None
    return _find_method_node_in_cls(typing.cast(ast.ClassDef, cls_ast), method_name)


def _resolve_full_attribute_path(node: ast.AST) -> Union[str, None]:
    """
    Reconstruct the full attribute name from an AST node, handling nested attributes and calls.

    Examples:
        sa.select(...).where(...) -> "sa.select.where"
        obj.method1().method2 -> "obj.method1.method2"
        module.submodule.Class.method -> "module.submodule.Class.method"
    """
    names: list[str] = []

    def recurse(n):
        if isinstance(n, ast.Attribute):
            names.append(n.attr)
            recurse(n.value)
        elif isinstance(n, ast.Call):
            recurse(n.func)
        elif isinstance(n, ast.Name):
            names.append(n.id)
        else:
            # Unsupported node type encountered
            pass

    recurse(node)

    if names:
        # The names are collected in reverse order, so reverse them back
        return ".".join(reversed(names))

    return None


def _retrieve_from_annotations(func: Callable, var_name: str) -> Optional[type]:
    result = func.__annotations__.get(var_name, None)
    if result is None:
        return None

    origin = typing.get_origin(result)
    if origin is Annotated:
        return result.__origin__
    elif origin is not None and origin != Generic:
        return origin
    return result


def _returned_class(callee) -> Optional[type]:
    """
    The class a call to `callee` gives back: the class itself, or a function's return annotation
    when it names a single class (Annotated, Optional and generic parameters are dropped).
    """
    if inspect.isclass(callee):
        return callee
    if not (inspect.isfunction(callee) or inspect.ismethod(callee)):
        return None
    try:
        hint = typing.get_type_hints(callee).get("return")
    except Exception:
        return None

    origin = typing.get_origin(hint)
    if origin is Union or origin is types.UnionType:
        classes = [arg for arg in typing.get_args(hint) if arg is not type(None)]
        hint = classes[0] if len(classes) == 1 else None
        origin = typing.get_origin(hint)
    if origin is not None:
        hint = origin
    return hint if inspect.isclass(hint) else None


def _resolve_type_from_assigment(
    resolved_value: Union[str, type, None],
    assignments: dict[NodeIdentifier, str],
    func: Callable,
):
    if resolved_value is None:
        return None

    # because assigment are stored as string
    # ! A string type could be also called like str("Foo").lower() so we fallback to parent_attr in case it remains as string

    if isinstance(resolved_value, str):
        resolved_value = func.__globals__.get(resolved_value, resolved_value)

    if isinstance(resolved_value, str):
        resolved_value = assignments.get(NodeIdentifier(resolved_value), resolved_value)

    if isinstance(resolved_value, str):
        resolved_value = (
            _retrieve_from_annotations(func, resolved_value) or resolved_value
        )

    if isinstance(resolved_value, str):  # last fallback
        resolved_value = _exctact_type(resolved_value, func.__globals__)

    return resolved_value


def _resolve_functions_from_call_node(
    call_node: ast.Call,
    func: Callable,
    assignments: dict[NodeIdentifier, str],
) -> list[type]:
    """
    Attempt to resolve the function object from a call node.
    Handles both simple function calls and method calls.
    """
    node = call_node.func

    if isinstance(node, ast.Name):
        # Simple function call: func()
        value = func.__globals__.get(node.id, None)

        if value is None:
            value = getattr(builtins, node.id, None)

        if value is None:
            logger.debug(f"Function '{node.id}' not found in {func.__name__}")

        if value is not None:
            return [value]
        return []

    elif isinstance(node, ast.Attribute):
        attr_chain = _resolve_full_attribute_path(node)
        if attr_chain is None:
            logger.debug(
                f"Failed to get full attribute name: {ast.dump(node)} in {func.__name__}"
            )
            return []

        try:
            parts = attr_chain.split(".")
            parent_part = parts[0]

            parent_attr = func.__globals__.get(parent_part, None)

            if parent_attr is None:
                node_id = NodeIdentifier(parent_part)
                parent_attr = assignments.get(node_id, None)

            if parent_attr is None and parent_part in func.__annotations__:
                parent_attr = _retrieve_from_annotations(func, parent_part)

            if parent_attr is None:
                # use case where you're calling self.foo.do_something(), where self.foo is a class attribute that is a class itself
                if parent_part == "self" or parent_part == "cls":
                    property_name = parts[1]
                    # ['class_name', 'method_name']
                    qual_names = func.__qualname__.split(".")
                    # ['class_name']
                    func_name_index = qual_names.index(func.__name__)
                    # 'class_name'
                    cls_name = qual_names[func_name_index - 1]
                    # class_name (type)
                    cls: Union[Callable, None] = func.__globals__.get(cls_name, None)

                    if cls is None:
                        logger.debug(
                            f"Failed to resolve parent class {cls} for parts {attr_chain}. Chain: {ast.dump(node)} for func {func.__name__}"
                        )
                        return []
                    attr_class = _retrieve_from_annotations(cls, property_name)
                    if attr_class is None:  # part of convention
                        return []

                    results: list[type] = []
                    try:
                        obj = getattr(attr_class, "__init__", None)
                        if obj is not None:
                            results.append(obj)
                    except Exception:
                        pass

                    for attr in parts[2:]:
                        try:
                            obj = getattr(attr_class, attr, None)

                            if obj is not None:
                                results.append(obj)
                        except Exception:
                            break

                    return results

                # ast.dump is costly and this path is hot
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        f"Failed to resolve parent attribute {parent_part} for parts {attr_chain}. Chain: {ast.dump(node)} for func {func.__name__}"
                    )
                return []

            parent_attr = _resolve_type_from_assigment(parent_attr, assignments, func)
            results: list[type] = []
            for attr in parts[1:]:
                try:
                    obj = getattr(parent_attr, attr, None)
                    if obj is not None:
                        results.append(obj)

                except Exception:
                    break

            return results

        except Exception:
            logger.exception(f"Failed to resolve attribute chain: {attr_chain}")
            return []

    return []


def _extract_node_name(
    node: SupportedAstNodes, assignments: dict[NodeIdentifier, str]
) -> Optional[str]:
    """
    Extract the exception name a node recursively.
    """
    if isinstance(node, ast.Call):
        return _extract_node_name(
            typing.cast(SupportedAstNodes, node.func), assignments
        )
    elif isinstance(node, ast.Name):
        var_name = get_node_identifier(node)
        return assignments.get(var_name, var_name)
    elif isinstance(node, ast.Attribute):
        return _resolve_full_attribute_path(node)

    elif isinstance(node, ast.Await):
        return _extract_node_name(
            typing.cast(SupportedAstNodes, node.value), assignments
        )

    elif isinstance(
        node,
        (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Raise, ast.Assign),
    ):
        ...  # not supported -> we cannot resolve the exception name

    else:
        not_supported(node)
        return None


@functools.lru_cache(maxsize=4096)
def _compile_expr(expr: str):
    return compile(expr, "<string>", "eval")


def _exctact_type(var_tyep: str, func_globals: dict) -> Optional[type]:
    """
    Attempt to resolve the exception name to an actual exception class.
    """
    try:
        exc_type = eval(_compile_expr(var_tyep), func_globals)
        if isinstance(exc_type, type) and issubclass(exc_type, BaseException):
            return exc_type
    except BaseException:
        return None

    try:
        # Fallback to builtins
        return getattr(builtins, var_tyep, None)
    except Exception:
        logger.exception(f"Failed to resolve variable type: {var_tyep}")


def _should_be_visited(
    module: ModuleType,
    should_search_module_pred: Callable[[str], bool],
):
    if (
        is_stdlib(module.__name__)
        or should_search_module_pred(module.__name__) is False
    ):
        return False

    return True


@functools.lru_cache(maxsize=None)
def _stdlib_path() -> str:
    return sysconfig.get_paths()["stdlib"]


@functools.lru_cache(maxsize=None)
def is_stdlib(module_name: str) -> bool:
    """Check if a given module is part of the Python standard library."""
    try:
        module_spec = find_spec(module_name)
    except Exception:
        return False

    if module_spec is None or module_spec.origin is None:
        return False
    return module_spec.origin.startswith(_stdlib_path())


def _reraises(handler: ast.ExceptHandler) -> bool:
    """Whether the handler re-raises what it caught: bare `raise`, or `raise e` for `as e`."""
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise) and (
            node.exc is None
            or (isinstance(node.exc, ast.Name) and node.exc.id == handler.name)
        ):
            return True
    return False


def _concrete_subclasses(*bases: type) -> set[type]:
    found: set[type] = set()
    stack = list(bases)
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        found.add(cls)
    return found


# Nodes that never hold another node worth visiting (Name only holds its Load/Store context).
# Without a visit_<Type> handler there is nothing to do in them, so traversal skips them.
_LEAF_NODE_TYPES = frozenset(
    _concrete_subclasses(
        ast.expr_context, ast.boolop, ast.operator, ast.unaryop, ast.cmpop
    )
    | {ast.Name, ast.Constant, ast.Pass, ast.Break, ast.Continue, ast.alias}
)
_LEGACY_CONSTANT_VISITORS = (
    "visit_Num",
    "visit_Str",
    "visit_Bytes",
    "visit_NameConstant",
    "visit_Ellipsis",
)


@functools.lru_cache(maxsize=None)
def _node_handler(visitor_cls: type, node_cls: type) -> Optional[Callable]:
    """The visit_<Type> method `ast.NodeVisitor.visit` would pick, or None for generic_visit."""
    name = "visit_" + node_cls.__name__
    handler = getattr(visitor_cls, name, None)
    base_handler = getattr(ast.NodeVisitor, name, None)
    # NodeVisitor.visit_Constant only forwards to the deprecated visit_Num & co (Python < 3.14).
    if handler is not None and handler is base_handler:
        if not any(hasattr(visitor_cls, n) for n in _LEGACY_CONSTANT_VISITORS):
            return None
    return handler


class ExceptionFinder(ast.NodeVisitor):
    visited: dict[Callable, list[RaisedExceptionInfo]] = {}

    # Same traversal order and dispatch as ast.NodeVisitor, minus its per-node string building,
    # getattr and generator overhead, and minus descending into leaf nodes. This is the hot loop.
    def visit(self, node):
        handler = _node_handler(type(self), type(node))
        if handler is not None:
            return handler(self, node)
        if type(node) not in _LEAF_NODE_TYPES:
            self.generic_visit(node)

    def generic_visit(self, node):
        visit = self.visit
        for field in node._fields:
            value = getattr(node, field, None)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        visit(item)
            elif isinstance(value, ast.AST):
                visit(value)

    def __init__(
        self, func: Callable, should_search_module_pred: Callable[[str], bool]
    ):
        self.exceptions: list[RaisedExceptionInfo] = []
        # (exception, id(raise_ast)) already in self.exceptions. The same raise reached through many
        # call paths carries no extra info, and keeping every copy grows exponentially on call diamonds.
        self._seen: set[tuple] = set()
        self.assignments: dict[NodeIdentifier, str] = {}
        # exc = HTTPException(401, ...) keeps the call, so `raise exc` can read its arguments
        self.assigned_calls: dict[NodeIdentifier, ast.Call] = {}
        # self.cached_assignments[func] = self.assignments
        self.func = func
        self.should_search_module_pred = should_search_module_pred
        logger.debug(f"Analyzing function {func.__name__}")

    @classmethod
    def clear_cache(cls):
        cls.visited.clear()
        _tree_cache.clear()
        _def_index_cache.clear()
        _class_line_cache.clear()
        _returned_exc_cache.clear()
        _raise_globals.clear()

    def _add_exceptions(self, excs: list[RaisedExceptionInfo]):
        for exc in excs:
            key = (exc.exception, id(exc.raise_ast))
            if key not in self._seen:
                self._seen.add(key)
                self.exceptions.append(exc)

    def populate_cache_if_not_exists(self, func_obj: Callable):
        if func_obj not in ExceptionFinder.visited:
            ExceptionFinder.visited[func_obj] = []

    def _should_be_visited(
        self, module: ModuleType
    ) -> typing_extensions.TypeGuard[ModuleType]:
        return _should_be_visited(module, self.should_search_module_pred)

    def visit_Assign(self, node):
        """
        Track assignments to variables that are exceptions or exception instances.
        Since we don't know the type of the variable, we just store the name.

        Handled scenarios:
            - Case 1: Name assigment
                exc = ValueError("An error occurred")
                raise exc

            - Other cases:
                They should be handled by raise statement visitor.
                They are assigned to a variable and assuming we visit and resolve it, should be enough.
                But sometimes it's impossible to resolve the exception name from these nodes.

                Example:

                    exc_callback = lambda: ValueError("An error occurred")
                    raise exc_callback()
        """
        value = typing.cast(SupportedAstNodes, node.value)
        targets = typing.cast(list[SupportedAstNodes], node.targets)

        for target in targets:
            if isinstance(target, ast.Name):
                var_name = get_node_identifier(target)
                var_result = _extract_node_name(value, self.assignments)
                if isinstance(value, ast.Call):
                    self.assigned_calls[var_name] = value
                else:
                    self.assigned_calls.pop(var_name, None)

                if var_result is not None:
                    self.assignments[var_name] = var_result

                else:
                    # no need to log here. it would be very spammy
                    # basically anything can happen here because, and won't be very unexpected
                    # imagine a lambda function assigned to a variable and raised later.
                    # so we only support whatever cases handled by `_extract_node_name`
                    ...

            elif isinstance(
                target,
                (
                    ast.Call,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.Raise,
                    ast.Assign,
                    ast.Attribute,
                    ast.Await,
                ),
            ):
                pass  # should be handled by raise statement visitor

            else:
                not_supported(target)

        self.generic_visit(node)

    def visit_Raise(self, node):
        """
        Handle raise statements and collect exceptions.
        """
        exc = node.exc
        if exc is None:
            # Could not resolve exception name -> maybe just using 'raise' without an exception
            # this edge case basically can raise anything
            logger.debug("Please don't use 'raise' without declaring what to raise")
            self._add_exceptions([RaisedExceptionInfo(None, node)])
            self.generic_visit(node)
            return

        exc_variable_name = _extract_node_name(
            typing.cast(SupportedAstNodes, exc), self.assignments
        )
        if exc_variable_name is None:
            # We are raising an exception that is assigned to a variable we don't know
            # Maybe global variable ?
            self._add_exceptions([RaisedExceptionInfo(None, node)])
            self.generic_visit(node)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Failed to get exception name: {ast.dump(node)}")
            return

        exc_type = _exctact_type(exc_variable_name, self.func.__globals__)

        if exc_type:
            raise_ast = node
            assigned_call = (
                self.assigned_calls.get(get_node_identifier(exc))
                if isinstance(exc, ast.Name)
                else None
            )
            if assigned_call is not None:
                # raise exc: status and detail are the arguments of the call exc came from
                raise_ast = ast.copy_location(
                    ast.Raise(exc=assigned_call, cause=None), node
                )
            _raise_globals[raise_ast] = self.func.__globals__
            self._add_exceptions([RaisedExceptionInfo(exc_type, raise_ast)])
        elif isinstance(exc, ast.Call):
            # raise make_error() / raise self.make_error(): the callee returns the exception
            for callee in self._resolve_raised_callees(exc):
                self._add_exceptions(_returned_exceptions(callee))

        self.generic_visit(node)
        return

    def visit_Try(self, node):
        self._visit_try(node)

    def visit_TryStar(
        self, node
    ):  # except* (3.11+) catches the same way for our purposes
        self._visit_try(node)

    def _visit_try(self, node: typing.Any):
        """
        Drop what the try body raises (directly or through calls) when a handler catches it and
        doesn't re-raise it. Handlers, else and finally are visited as usual.
        """
        start = len(self.exceptions)
        for stmt in node.body:
            self.visit(stmt)

        handlers = [
            (self._handler_types(handler), _reraises(handler))
            for handler in node.handlers
        ]
        kept = []
        for exc in self.exceptions[start:]:
            if self._is_caught(exc.exception, handlers):
                self._seen.discard((exc.exception, id(exc.raise_ast)))
            else:
                kept.append(exc)
        # filter our own list, never the cached lists of callees
        self.exceptions[start:] = kept

        for stmt in [*node.handlers, *node.orelse, *node.finalbody]:
            self.visit(stmt)

    def _handler_types(self, handler: ast.ExceptHandler) -> Optional[tuple[type, ...]]:
        """Types the handler catches, None if any of them can't be resolved."""
        if handler.type is None:  # bare except
            return (BaseException,)
        nodes = (
            handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        )
        caught = []
        for type_node in nodes:
            name = _resolve_full_attribute_path(type_node)
            exc_type = name and _exctact_type(name, self.func.__globals__)
            if not exc_type:
                return None
            caught.append(exc_type)
        return tuple(caught)

    @staticmethod
    def _is_caught(
        exc_type: Optional[type],
        handlers: list[tuple[Optional[tuple[type, ...]], bool]],
    ) -> bool:
        if exc_type is None:
            return False
        for caught, reraises in handlers:  # the first matching handler wins
            if caught is None:
                return False  # unknown handler may be the one catching it: keep
            if issubclass(exc_type, caught):
                return not reraises
        return False

    def _resolve_raised_callees(self, call: ast.Call) -> list[Callable]:
        callees = _resolve_functions_from_call_node(call, self.func, self.assignments)
        if not callees:
            callee = _self_method(call, self.func)
            callees = [callee] if callee is not None else []

        result = []
        for callee in callees:
            module = inspect.getmodule(callee)
            if module is not None and self._should_be_visited(module):
                result.append(callee)
        return result

    def _visit_method(self, method: Callable):
        """Collect what a `self.method()` call can raise, like FastAPI's `self.check_api_key()`."""
        module = inspect.getmodule(method)
        if module is None or self._should_be_visited(module) is False:
            return
        method_def = _method_def(method)
        if method_def is not None:
            self._add_exceptions(
                _find_explicit_expection_recursively(
                    method, self.should_search_module_pred, method_def
                )
            )

    def _call_result_class(self, call: ast.Call) -> Optional[type]:
        """The class `call` returns, following chains like `get_a().get_b()`."""
        func_node = call.func
        if isinstance(func_node, ast.Attribute) and isinstance(
            func_node.value, ast.Call
        ):
            owner = self._call_result_class(func_node.value)
            callee = getattr(owner, func_node.attr, None) if owner else None
        else:
            callees = _resolve_functions_from_call_node(
                call, self.func, self.assignments
            )
            callee = callees[-1] if callees else None
        if inspect.isfunction(callee) or inspect.ismethod(callee):
            module = inspect.getmodule(callee)  # only trust factories we would analyze
            if module is None or self._should_be_visited(module) is False:
                return None
        return _returned_class(callee)

    def visit_Call(self, node):
        """
        Handle function calls and recursively analyze called functions.
        """
        func_objs = _resolve_functions_from_call_node(node, self.func, self.assignments)
        if not func_objs:
            method = _self_method(node, self.func)
            if method is not None:
                self._visit_method(method)

        # get_repo().find() / repo = get_repo(); repo.find(): a method of the returned class
        if isinstance(node.func, ast.Attribute):
            receiver = node.func.value
            if isinstance(receiver, ast.Name):
                receiver = self.assigned_calls.get(get_node_identifier(receiver))
            elif isinstance(receiver, ast.Await):
                receiver = receiver.value
            if isinstance(receiver, ast.Call):
                owner = self._call_result_class(receiver)
                method = getattr(owner, node.func.attr, None) if owner else None
                if method is not None:
                    self._visit_method(getattr(method, "__func__", method))

        for func_obj in func_objs:
            if inspect.isfunction(func_obj):
                module = inspect.getmodule(func_obj)
                if module is None or self._should_be_visited(module) is False:
                    continue

                try:
                    tree = _parse_source(module)
                except BaseException as error:
                    logger.exception(
                        f"Failed to parse source code for {func_obj.__name__}.",
                        exc_info=error,
                    )
                    self.generic_visit(node)
                    return

                founded_func_ast = _find_def(tree, "func", func_obj.__name__)
                if founded_func_ast:
                    excs = _find_explicit_expection_recursively(
                        func_obj, self.should_search_module_pred, founded_func_ast
                    )
                    self._add_exceptions(excs)
                else:
                    logger.debug(
                        f"Failed to find function {func_obj.__name__} in module {module.__name__}"
                    )

            elif inspect.isclass(func_obj):
                _excs = _find_all_class_exceptions(
                    func_obj, self.should_search_module_pred
                )
                self._add_exceptions(_excs)
                self.populate_cache_if_not_exists(func_obj)

        self.generic_visit(node)
        self.populate_cache_if_not_exists(self.func)
        return

    def visit_Attribute(self, node):
        node_value = typing.cast(SupportedAstNodes, node.value)

        if isinstance(node_value, ast.Name):
            caller_node_name = self.assignments.get(get_node_identifier(node_value))
            if not caller_node_name:
                self.generic_visit(node)
                return

            try:
                caller_type = _exctact_type(caller_node_name, self.func.__globals__)
            except Exception:
                logger.debug(f"Failed to resolve attribute chain: {caller_node_name}")
                self.generic_visit(node)
                return

            if not caller_type:
                self.generic_visit(node)
                return

            method_func = getattr(caller_type, node.attr, None)
            if not method_func:
                self.generic_visit(node)
                return

            module = inspect.getmodule(caller_type)
            if module is None or self._should_be_visited(module) is False:
                self.generic_visit(node)
                return

            try:
                tree = _parse_source(module)
            except BaseException as error:
                logger.exception(
                    f"Failed to parse source code for {caller_type.__name__}.",
                    exc_info=error,
                )
                self.generic_visit(node)
                return

            cls_ast = _find_def(tree, "class", caller_type.__name__)
            if cls_ast:
                casted_cls_ast = typing.cast(ast.ClassDef, cls_ast)
                submethod_ast = _find_method_node_in_cls(casted_cls_ast, node.attr)
                if submethod_ast:
                    excs = _find_explicit_expection_recursively(
                        method_func, self.should_search_module_pred, submethod_ast
                    )
                    self._add_exceptions(excs)

        self.generic_visit(node)
        return
