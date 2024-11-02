import ast
import builtins
import inspect
import logging
import sysconfig
import typing
from importlib.util import find_spec
from types import ModuleType
from typing import Annotated, Callable, Generic, List, NewType, Optional, Tuple, Union

import typing_extensions

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


def _get_tree(obj: Callable):
    to_search = obj
    if is_absolutely_callable_object(obj):
        to_search: Union[type, Callable] = (
            obj_type if (obj_type := type(obj)) is not type else obj
        )

    try:
        tree = ast.parse(inspect.getsource(to_search))
        return tree
    except Exception as error:
        obj_name = obj.__name__ if hasattr(obj, "__name__") else obj.__str__()
        logger.debug(f"Failed to parse source code for {obj_name}", exc_info=error)
        return None


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
        cls_tree = ast.parse(inspect.getsource(cls))
    except Exception as error:
        cls_name = cls.__name__ if hasattr(cls, "__name__") else cls.__str__()
        logger.info(
            f"Failed to parse source code for {cls_name}.__init__", exc_info=error
        )
        return []

    init_tree = _find_in_module(
        cls_tree,
        lambda n: (
            isinstance(n, ast.AsyncFunctionDef) or isinstance(n, ast.FunctionDef)
        )
        and n.name == "__init__",
    )

    result: list[tuple[Optional[type[Exception]], ast.Raise]] = []
    if init_tree is not None:
        result.extend(
            _find_explicit_expection_recursively(
                cls.__init__, to_filter_predicate, init_tree
            )
        )

    if hasattr(cls, "__call__"):
        # Not sure if __call__ was called or init, so check for both
        call_tree = _find_in_module(
            cls_tree,
            lambda n: (
                isinstance(n, ast.AsyncFunctionDef) or isinstance(n, ast.FunctionDef)
            )
            and n.name == "__call__",
        )

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
) -> list[tuple[Optional[type[Exception]], ast.Raise]]:
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

    finder = ExceptionFinder(func_obj, to_filter_predicate)
    try:
        finder.visit(tree)
    except Exception as error:
        logger.exception(
            f"Failed to analyze function {get_func_name(func_obj)}.", exc_info=error
        )

    ExceptionFinder.visited[func_obj] = finder.exceptions
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
    visited: dict[Callable, list[tuple[Optional[type[Exception]], ast.Raise]]] = {}

    def __init__(
        self, func: Callable, should_search_module_pred: Callable[[str], bool]
    ):
        self.exceptions: list[tuple[Optional[type[Exception]], ast.Raise]] = []
        self.assignments: dict[NodeIdentifier, str] = {}
        # self.cached_assignments[func] = self.assignments
        self.func = func
        self.should_search_module_pred = should_search_module_pred
        logger.debug(f"Analyzing function {func.__name__}")

    @classmethod
    def clear_cache(cls):
        cls.visited.clear()

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

        exc_type = _exctact_type(exc_variable_name, self.func.__globals__)

        if exc_type:
            self.exceptions.append((exc_type, node))

        self.generic_visit(node)
        return

    def visit_Call(self, node):
        """
        Handle function calls and recursively analyze called functions.
        """
        func_objs = _resolve_functions_from_call_node(node, self.func, self.assignments)
        for func_obj in func_objs:
            if inspect.isfunction(func_obj):
                module = inspect.getmodule(func_obj)
                if module is None or self._should_be_visited(module) is False:
                    continue

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

            elif inspect.isclass(func_obj):
                _excs = _find_all_class_exceptions(
                    func_obj, self.should_search_module_pred
                )
                self.exceptions.extend(_excs)

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
