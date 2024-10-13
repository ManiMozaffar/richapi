import ast
import builtins
import inspect
import logging
import typing
from typing import Callable, List, NewType, Optional, Tuple, Union

from loguru import logger

from richapi.exceptions import FetchSourceException


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
]

NodeIdentifier = NewType("NodeIdentifier", str)
"""Branded type that represents a node identifier that can be used a key in a dictionary."""


def get_node_identifier(node: ast.Name) -> NodeIdentifier:
    """Get the identifier of the given node."""
    return NodeIdentifier(node.id)


def find_explicit_exceptions(func: Callable) -> List[Tuple[Optional[type], ast.Raise]]:
    """
    Analyze the given function and find all explicitly raised exceptions,
    including those in nested functions and class methods.

    Returns:
        A list of tuples where each tuple contains:
            - The exception class (or None if it couldn't be resolved)
            - The ast.Raise node
    """
    return _find_explicit_exceptions_recursive(func, visited=set())


def _find_in_module(module: ast.Module, cls_name: str):
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            return node
    return None


def _find_in_class(cls: ast.ClassDef, method_name: str):
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    return None


def _split_chain(attr_chain: str, func_globals: dict):
    try:
        parts = attr_chain.split(".")
        obj = func_globals.get(parts[0], None)

        for attr in parts[1:]:
            if obj is None:
                break
            obj = getattr(obj, attr, None)

        return obj
    except Exception:
        logger.exception(f"Failed to resolve attribute chain: {attr_chain}")
        return None


def _get_full_attr_name(node) -> str | None:
    """
    Reconstruct the full attribute name from an AST Attribute node.
    """
    names = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        names.append(node.id)
        names.reverse()
        return ".".join(names)
    logger.warning(f"Failed to get full attribute name: {node}")
    return None


def _resolve_function_object(
    node: ast.FunctionDef | ast.AsyncFunctionDef, func_globals: dict
):
    """
    Resolve a function object by name from the globals.
    """
    func_name = node.name
    value = func_globals.get(func_name, None)
    if value is None:
        logger.warning(f"Function '{func_name}' not found in globals")

    return value


def _resolve_function_object_from_call(node, func_globals: dict):
    """
    Attempt to resolve the function object from a call node.
    Handles both simple function calls and method calls.
    """
    if isinstance(node, ast.Name):
        # Simple function call: func()
        value = func_globals.get(node.id, None)
        if value is None:
            logger.warning(f"Function '{node.id}' not found in globals")
        return value

    elif isinstance(node, ast.Attribute):
        # Method call: obj.method()
        attr_chain = _get_full_attr_name(node)
        if not attr_chain:
            logger.warning(f"Failed to resolve attribute chain: {node}")
            return None
        return _split_chain(attr_chain, func_globals)
    else:
        return None


def _resolve_method_object(class_name: str, method_name: str, func_globals: dict):
    """
    Resolve a method object given the class and method names.
    """
    try:
        cls = func_globals.get(class_name, None)
        if cls and hasattr(cls, method_name):
            return getattr(cls, method_name)
    except Exception:
        logger.exception(f"Failed to resolve method: {class_name}.{method_name}")
        pass
    logging.warning(f"Method '{class_name}.{method_name}' not found")
    return None


def _get_exception_name(node, assignments: dict[NodeIdentifier, str]) -> Optional[str]:
    """
    Extract the exception name from the raised expression.
    """
    if isinstance(node, ast.Call):
        return _get_exception_name(node.func, assignments)
    elif isinstance(node, ast.Name):
        var_name = get_node_identifier(node)
        return assignments.get(var_name, var_name)
    elif isinstance(node, ast.Attribute):
        return _get_full_attr_name(node)
    else:
        logger.warning(f"Failed to get exception name: {node}")
        return None


def _resolve_exception_type(exc_name: str, func_globals: dict, func) -> Optional[type]:
    """
    Attempt to resolve the exception name to an actual exception class.
    """
    try:
        exc_type = eval(exc_name, func_globals)
        if isinstance(exc_type, type) and issubclass(exc_type, BaseException):
            return exc_type
    except (NameError, AttributeError, SyntaxError):
        return None

    try:
        # Fallback to builtins
        return getattr(builtins, exc_name, None)
    except Exception:
        logger.exception(f"Failed to resolve exception type: {exc_name} for {func}")


class ExceptionFinder(ast.NodeVisitor):
    def __init__(self, func, visited):
        self.exceptions: List[Tuple[Optional[type], ast.Raise]] = []
        self.assignments: dict[NodeIdentifier, str] = {}
        self.func_globals = func.__globals__
        self.func = func
        self.visited = visited

    def visit_Raise(self, node):
        """
        Handle raise statements and collect exceptions.
        """
        exc = node.exc
        if exc is None:
            # Could not resolve exception name -> maybe just using 'raise' without an exception
            # this edge case basically can raise anything
            logger.warning("Please don't use 'raise' without declaring what to raise")
            self.exceptions.append((None, node))
            self.generic_visit(node)
            return

        exc_variable_name = _get_exception_name(exc, self.assignments)
        if exc_variable_name is None:
            # We are raising an exception that is assigned to a variable we don't know
            # Maybe global variable ?
            self.exceptions.append((None, node))
            self.generic_visit(node)
            return

        exc_type = _resolve_exception_type(
            exc_variable_name, self.func_globals, self.func
        )
        if exc_type:
            self.exceptions.append((exc_type, node))
            self.generic_visit(node)
            return

        # at this point we're not raising the exception directly.
        # like raise foo() which foo is a function that returns an exception

        supported_nodes = typing.cast(SupportedAstNodes, exc)
        if isinstance(supported_nodes, ast.Call):
            func_obj = _resolve_function_object_from_call(
                supported_nodes.func, self.func_globals
            )
            if func_obj and inspect.isfunction(func_obj):
                result = func_obj
                print(result)

        elif isinstance(
            supported_nodes,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Raise,
                ast.Assign,
                ast.Attribute,
                ast.Name,
            ),
        ):
            # i don't want to support other use cases
            ...

        else:
            not_supported(supported_nodes)

        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            identifier = NodeIdentifier(node.name)
            exc_name = _get_exception_name(node.type, self.assignments)
            if exc_name:
                self.assignments[identifier] = exc_name

        self.generic_visit(node)

    def visit_Assign(self, node):
        """
        Track assignments to variables that are exceptions or exception instances.

        Handled scenarios:
            - Case 1: Name assigment
                exc = ValueError("An error occurred")
                raise exc

            - Other cases:
                They should be handled by raise statement visitor.
                Because it's impossible to raise an exception from these cases.

                exc_callback = lambda: ValueError("An error occurred")
                raise exc_callback()
        """
        value = typing.cast(SupportedAstNodes, node.value)
        targets = typing.cast(list[SupportedAstNodes], node.targets)

        for target in targets:
            if isinstance(target, ast.Name):
                var_name = get_node_identifier(target)
                exc_name = _get_exception_name(value, self.assignments)
                if exc_name is not None:
                    self.assignments[var_name] = exc_name

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
                ),
            ):
                pass  # should be handled by raise statement visitor

            else:
                not_supported(target)

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """
        Visit nested functions within the current function.

        Example:
            def foo():
                def inner_func():
                    raise ValueError("An error in inner function")

                inner_func()
        """
        func_obj = _resolve_function_object(node, self.func_globals)
        if func_obj and inspect.isfunction(func_obj):
            self.exceptions.extend(
                _find_explicit_exceptions_recursive(func_obj, self.visited)
            )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        """
        Visit nested async functions within the current function.

        Example:
            async def foo():
                async def inner_func():
                    raise ValueError("An error in inner function")

                await inner_func()
        """
        func_obj = _resolve_function_object(node, self.func_globals)
        if func_obj and inspect.isfunction(func_obj):
            self.exceptions.extend(
                _find_explicit_exceptions_recursive(func_obj, self.visited)
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        """
        Visit classes within the current function and analyze their methods.

        Example:
            class Foo:
                def bar(self):
                    raise ValueError("An error in class method
        """
        for body_item in node.body:
            if isinstance(body_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_name = body_item.name
                method_obj = _resolve_method_object(
                    node.name, method_name, self.func_globals
                )
                if method_obj and inspect.isfunction(method_obj):
                    self.exceptions.extend(
                        _find_explicit_exceptions_recursive(method_obj, self.visited)
                    )
        self.generic_visit(node)

    def visit_Call(self, node):
        """
        Handle function calls and recursively analyze called functions.
        """
        func_obj = _resolve_function_object_from_call(node.func, self.func_globals)
        if func_obj and inspect.isfunction(func_obj):
            self.exceptions.extend(
                _find_explicit_exceptions_recursive(func_obj, self.visited)
            )
        self.generic_visit(node)

    def visit_Attribute(self, node):
        node_value = typing.cast(ast.Name, node.value)
        caller_node_name = self.assignments.get(get_node_identifier(node_value))
        if not caller_node_name:
            self.generic_visit(node)
            return

        caller_type: type = eval(caller_node_name, self.func_globals)
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
        tree = ast.parse(source)
        cls_ast = _find_in_module(tree, caller_type.__name__)
        if cls_ast:
            submethod = _find_in_class(cls_ast, node.attr)
            if submethod:
                finder = ExceptionFinder(method_func, self.visited)
                finder.visit(submethod)
                self.exceptions.extend(finder.exceptions)

        self.generic_visit(node)


def _find_explicit_exceptions_recursive(
    func: Callable, visited: set[SupportedAstNodes | Callable]
) -> List[Tuple[Optional[type], ast.Raise]]:
    if func in visited:
        return []
    visited.add(func)

    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        raise FetchSourceException(func)

    tree = ast.parse(source)
    finder = ExceptionFinder(func, visited)
    finder.visit(tree)
    return finder.exceptions
