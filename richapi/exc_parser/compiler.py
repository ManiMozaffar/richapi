import ast
import builtins
import inspect
import logging
import sysconfig
import typing
from functools import lru_cache
from importlib.util import find_spec
from typing import Callable, List, NewType, Optional, Tuple, Union

logger = logging.getLogger(__name__)


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


def find_explicit_exceptions(
    func: Callable,
    target_modules: list[str],
    should_search_module_pred: Union[Callable[[str], bool], None] = None,
) -> List[Tuple[Optional[type[Exception]], ast.Raise]]:
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

    return _find_explicit_expection_recursively(func, should_search_module_pred)


def get_func_name(func: Callable) -> str:
    return func.__name__ if hasattr(func, "__name__") else func.__str__()


def _find_all_class_exceptions(
    cls: type,
    to_filter_predicate: Callable[[str], bool],
    tree: Optional[ast.AST] = None,
):
    try:
        tree = tree or ast.parse(inspect.getsource(cls))
    except Exception as error:
        logger.exception(
            f"Failed to parse source code for {cls.__name__}.", exc_info=error
        )
        return []

    result = _find_explicit_expection_recursively(
        cls.__init__, to_filter_predicate, tree
    )
    if hasattr(cls, "__call__"):
        # Not sure if __call__ was called or init, so check for both

        result.extend(
            _find_explicit_expection_recursively(
                cls.__call__,  # type: ignore
                to_filter_predicate,
                tree,
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
    tree: Optional[ast.AST] = None,
) -> list[tuple[Optional[type[Exception]], ast.Raise]]:
    if func_obj in ExceptionFinder.visited:
        return []

    module = inspect.getmodule(func_obj)
    if module and is_stdlib(module.__name__):
        return []

    if module and to_filter_predicate(module.__name__) is False:
        return []

    if is_absolutely_callable_object(func_obj):
        cls_module = inspect.getmodule(type(func_obj))
        if cls_module and is_stdlib(cls_module.__name__):
            return []
        if cls_module and to_filter_predicate(cls_module.__name__) is False:
            return []

        return _find_all_class_exceptions(type(func_obj), to_filter_predicate, tree)

    ExceptionFinder.visited.add(func_obj)

    if tree is None:
        try:
            source = inspect.getsource(func_obj)
        except (OSError, TypeError) as error:
            logger.exception(
                f"Failed to get source code for {get_func_name(func_obj)}.",
                exc_info=error,
            )
            return []

        try:
            tree = ast.parse(source)
        except IndentationError as error:
            logger.exception(
                f"Failed to get source code for {get_func_name(func_obj)}.",
                exc_info=error,
            )
            return []

    finder = ExceptionFinder(func_obj, to_filter_predicate)
    try:
        finder.visit(tree)
    except Exception as error:
        logger.exception(
            f"Failed to analyze function {get_func_name(func_obj)}.", exc_info=error
        )

    return finder.exceptions


def _find_in_module(module: ast.Module, predicate: Callable[[ast.AST], bool]):
    for node in ast.walk(module):
        if predicate(node):
            return node
    return None


def _find_method_node_in_cls(cls: ast.ClassDef, method_name: str):
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    return None


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


def _resolve_function_from_call_node(
    call_node: ast.Call,
    func_globals: dict,
    func: Callable,
    assignments: dict[NodeIdentifier, str],
):
    """
    Attempt to resolve the function object from a call node.
    Handles both simple function calls and method calls.
    """
    node = call_node.func

    if isinstance(node, ast.Name):
        # Simple function call: func()
        value = func_globals.get(node.id, None)

        if value is None:
            value = getattr(builtins, node.id, None)

        if value is None:
            logger.debug(f"Function '{node.id}' not found in {func.__name__}")

        return value

    elif isinstance(node, ast.Attribute):
        attr_chain = _resolve_full_attribute_path(node)
        if attr_chain is None:
            logger.debug(
                f"Failed to get full attribute name: {ast.dump(node)} in {func.__name__}"
            )
            return None

        try:
            parts = attr_chain.split(".")
            parent_part = parts[0]

            parent_attr = func_globals.get(parent_part, None)

            if parent_attr is None:
                if parent_part in func.__annotations__:
                    return func.__annotations__[parent_part]

                parent_attr = getattr(builtins, parent_part, None)

            if parent_attr is None:
                node_id = NodeIdentifier(parent_part)
                parent_attr = assignments.get(node_id, None)

            if parent_attr is None:
                if (
                    parent_part == "self"
                ):  # don't need to log -> we already know this is class
                    return None

                logger.debug(
                    f"Failed to resolve parent attribute {parent_part} for parts {attr_chain}. Chain: {ast.dump(node)} for func {func.__name__}"
                )
                return None

            for attr in parts[1:]:
                try:
                    obj = getattr(parent_attr, attr, None)
                except Exception:
                    break

                return obj

        except Exception:
            logger.exception(f"Failed to resolve attribute chain: {attr_chain}")
            return None


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


def _exctact_type(var_tyep: str, func_globals: dict) -> Optional[type]:
    """
    Attempt to resolve the exception name to an actual exception class.
    """
    try:
        exc_type = eval(var_tyep, func_globals)
        if isinstance(exc_type, type) and issubclass(exc_type, BaseException):
            return exc_type
    except BaseException:
        return None

    try:
        # Fallback to builtins
        return getattr(builtins, var_tyep, None)
    except Exception:
        logger.exception(f"Failed to resolve variable type: {var_tyep}")


@lru_cache
def is_stdlib(module_name: str) -> bool:
    """Check if a given module is part of the Python standard library."""
    try:
        module_spec = find_spec(module_name)
    except Exception:
        return False

    if module_spec is None or module_spec.origin is None:
        return False
    std_lib_paths = sysconfig.get_paths()["stdlib"]
    return module_spec.origin.startswith(std_lib_paths)


class ExceptionFinder(ast.NodeVisitor):
    visited: set[Callable] = set()

    def __init__(
        self, func: Callable, should_search_module_pred: Callable[[str], bool]
    ):
        self.exceptions: list[tuple[Optional[type[Exception]], ast.Raise]] = []
        self.assignments: dict[NodeIdentifier, str] = {}
        self.func = func
        self.func_globals = func.__globals__
        self.should_search_module_pred = should_search_module_pred
        logger.info(f"Analyzing function {func.__name__}")

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
                var_identifier = get_node_identifier(target)
                var_name = _extract_node_name(value, self.assignments)
                if var_name is not None:
                    self.assignments[var_identifier] = var_name

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
            self.exceptions.append((None, node))
            self.generic_visit(node)
            return

        exc_variable_name = _extract_node_name(
            typing.cast(SupportedAstNodes, exc), self.assignments
        )
        if exc_variable_name is None:
            # We are raising an exception that is assigned to a variable we don't know
            # Maybe global variable ?
            self.exceptions.append((None, node))
            self.generic_visit(node)
            logger.debug(f"Failed to get exception name: {ast.dump(node)}")
            return

        exc_type = _exctact_type(exc_variable_name, self.func_globals)

        if exc_type:
            self.exceptions.append((exc_type, node))

        self.generic_visit(node)
        return

    def visit_Call(self, node):
        """
        Handle function calls and recursively analyze called functions.
        """
        func_obj = _resolve_function_from_call_node(
            node, self.func_globals, self.func, self.assignments
        )
        if func_obj and inspect.isfunction(func_obj):
            module = inspect.getmodule(func_obj)
            if not module:
                self.generic_visit(node)
                return

            if (
                is_stdlib(module.__name__)
                or self.should_search_module_pred(module.__name__) is False
            ):
                self.generic_visit(node)
                return

            source = inspect.getsource(module)
            try:
                tree = ast.parse(source)
            except BaseException as error:
                logger.exception(
                    f"Failed to parse source code for {func_obj.__name__}.",
                    exc_info=error,
                )
                self.generic_visit(node)
                return

            founded_func_ast = _find_in_module(
                tree,
                lambda n: (
                    isinstance(n, ast.AsyncFunctionDef)
                    or isinstance(n, ast.FunctionDef)
                )
                and n.name == func_obj.__name__,
            )
            if founded_func_ast:
                excs = _find_explicit_expection_recursively(
                    func_obj, self.should_search_module_pred, founded_func_ast
                )
                self.exceptions.extend(excs)
            else:
                logger.debug(
                    f"Failed to find function {func_obj.__name__} in module {module.__name__}"
                )

        self.generic_visit(node)
        return

    def visit_Attribute(self, node):
        node_value = typing.cast(SupportedAstNodes, node.value)

        if isinstance(node_value, ast.Name):
            caller_node_name = self.assignments.get(get_node_identifier(node_value))
            if not caller_node_name:
                self.generic_visit(node)
                return

            try:
                caller_type = _exctact_type(caller_node_name, self.func_globals)
            except Exception:
                logger.critical(
                    f"Failed to resolve attribute chain: {caller_node_name}"
                )
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
            if not module:
                self.generic_visit(node)
                return

            source = inspect.getsource(module)
            try:
                tree = ast.parse(source)
            except BaseException as error:
                logger.exception(
                    f"Failed to parse source code for {caller_type.__name__}.",
                    exc_info=error,
                )
                self.generic_visit(node)
                return

            cls_ast = _find_in_module(
                tree,
                lambda n: isinstance(n, ast.ClassDef)
                and n.name == caller_type.__name__,
            )
            if cls_ast:
                casted_cls_ast = typing.cast(ast.ClassDef, cls_ast)
                submethod_ast = _find_method_node_in_cls(casted_cls_ast, node.attr)
                if submethod_ast:
                    excs = _find_explicit_expection_recursively(
                        method_func, self.should_search_module_pred, submethod_ast
                    )
                    self.exceptions.extend(excs)

        self.generic_visit(node)
        return
