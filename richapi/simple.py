import importlib
import inspect
import tokenize
from inspect import iscoroutinefunction, isfunction
from io import BytesIO
from tokenize import TokenInfo
from typing import Callable, Generator, List, Tuple


def build_statement(exc: TokenInfo, tokens: Generator[TokenInfo, None, None]) -> str:
    statement = exc.string
    while True:
        token = next(tokens)
        statement += token.string.replace("\n", "")
        if token.type == tokenize.NEWLINE:
            return statement


def is_function_or_coroutine(obj):
    return isfunction(obj) or iscoroutinefunction(obj)


def exceptions_functions(
    endpoint: Callable, tokens: Generator[TokenInfo, None, None]
) -> Tuple[List[Exception], List[Callable]]:
    exceptions, functions = [], []
    module = importlib.import_module(endpoint.__module__)
    try:
        while True:
            token = next(tokens)
            try:
                obj = getattr(module, token.string)
                if inspect.isclass(obj):
                    statement = build_statement(token, tokens)
                    exc = eval(statement)
                    if isinstance(exc, Exception):
                        exceptions.append(exc)
                if is_function_or_coroutine(obj) and obj is not endpoint:
                    functions.append(obj)
            except Exception:
                ...
    except StopIteration:
        ...
    return exceptions, functions


def extract_exceptions(callable: Callable):
    exceptions: list[Exception] = []
    functions: list[Callable] = [callable]
    while len(functions) > 0:
        this_func = functions.pop()
        source = inspect.getsource(this_func)
        tokens = tokenize.tokenize(BytesIO(source.encode("utf-8")).readline)
        _exceptions, _functions = exceptions_functions(this_func, tokens)
        exceptions.extend(_exceptions)
        functions.extend(_functions)
    return exceptions
