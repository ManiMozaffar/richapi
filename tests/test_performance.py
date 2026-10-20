import ast
import inspect
import sys
import time

import fastapi
import fastapi.security
from pydantic.dataclasses import dataclass

from richapi.exc_parser import compiler
from richapi.exc_parser.compiler import ExceptionFinder, find_explicit_exceptions
from richapi.exc_parser.openapi import compile_openapi_from_fastapi
from richapi.exc_parser.protocol import (
    BaseHTTPException,
    RichHTTPException,
    _build_generic_json_schema,
    _generic_json_schema_builder,
)

MODULE = __name__


@dataclass
class RecursionExc(RichHTTPException):
    status_code = 410


@dataclass
class MutualExc(RichHTTPException):
    status_code = 411


class DiamondExc(BaseHTTPException):
    status_code = 412
    detail = "diamond"


def self_recursive(n: int):
    if n == 0:
        raise RecursionExc()
    self_recursive(n - 1)


def ping(n: int):
    if n == 0:
        raise MutualExc()
    pong(n - 1)


def pong(n: int):
    ping(n)


def d0():
    raise DiamondExc()


app = fastapi.FastAPI()


@app.get("/recursive")
def recursive_route():
    self_recursive(3)
    ping(3)


def test_recursive_functions_terminate_and_are_detected():
    responses = compile_openapi_from_fastapi(app, MODULE)["paths"]["/recursive"]["get"][
        "responses"
    ]
    assert "410" in responses
    assert "411" in responses


def test_call_diamond_is_linear_not_exponential():
    # 2**5 call paths lead to the same raise; it must be reported once.
    ExceptionFinder.clear_cache()
    start = time.perf_counter()
    found = find_explicit_exceptions(diamond_caller, [MODULE])
    assert time.perf_counter() - start < 2
    assert [e.exception for e in found] == [DiamondExc]
    ExceptionFinder.clear_cache()


def l1():
    d0()
    d0()


def l2():
    l1()
    l1()


def l3():
    l2()
    l2()


def l4():
    l3()
    l3()


def diamond_caller():
    l4()
    l4()


def test_compile_twice_is_stable():
    first = compile_openapi_from_fastapi(app, MODULE)
    second = compile_openapi_from_fastapi(app, MODULE)
    assert first == second


def test_schema_builders_hand_out_independent_copies():
    a = _generic_json_schema_builder(DiamondExc)
    assert a is not None
    a.response_schema_json["mutated"] = True
    b = _generic_json_schema_builder(DiamondExc)
    assert b is not None
    assert "mutated" not in b.response_schema_json

    r1 = RecursionExc.get_json_schema()
    r1.response_schema_json["mutated"] = True
    r2 = RecursionExc.get_json_schema()
    assert "mutated" not in r2.response_schema_json
    assert r2.status_code == 410


def test_unhashable_detail_behaves_like_uncached_builder():
    class DictDetailExc(fastapi.HTTPException): ...

    def outcome(builder):
        try:
            return builder(DictDetailExc, {"a": 1}, 400)
        except Exception as error:
            return type(error)

    assert outcome(_generic_json_schema_builder) == outcome(_build_generic_json_schema)


def test_find_def_matches_find_in_module():
    tree = ast.parse(inspect.getsource(sys.modules[MODULE]))
    for name in ["ping", "pong", "l4", "diamond_caller", "missing"]:
        expected = compiler._find_in_module(
            tree,
            lambda n: isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == name,
        )
        assert compiler._find_def(tree, "func", name) is expected
    for name in ["RecursionExc", "DiamondExc", "missing"]:
        expected = compiler._find_in_module(
            tree, lambda n: isinstance(n, ast.ClassDef) and n.name == name
        )
        assert compiler._find_def(tree, "class", name) is expected


def test_clear_cache_drops_parsed_trees():
    find_explicit_exceptions(diamond_caller, [MODULE])
    assert compiler._tree_cache
    ExceptionFinder.clear_cache()
    assert not compiler._tree_cache
    assert not compiler._def_index_cache
    assert not ExceptionFinder.visited


class _Outer:
    class Inner:
        def __init__(self):
            raise DiamondExc()


def _outcome(func, *args):
    try:
        return func(*args)
    except Exception as error:  # e.g. 3.13 can't find source of pydantic dataclasses
        return type(error)


def test_getsource_matches_stdlib():
    import tests.test_class as other

    for cls in [
        RecursionExc,
        DiamondExc,
        _Outer,
        _Outer.Inner,
        other.PaymentService,
        fastapi.FastAPI,
        fastapi.security.HTTPBearer,
    ]:
        assert _outcome(compiler._getsource, cls) == _outcome(inspect.getsource, cls)
    ExceptionFinder.clear_cache()


def test_top_level_class_tree_matches_parsing_getsource():
    import fastapi.params
    import fastapi.routing
    import fastapi.security
    import pydantic.main
    import starlette.responses

    checked = 0
    for module in (
        sys.modules[MODULE],
        fastapi.params,
        fastapi.routing,
        fastapi.security,
        pydantic.main,
        starlette.responses,
    ):
        for obj in vars(module).values():
            if not inspect.isclass(obj) or obj.__module__ != module.__name__:
                continue
            reused = compiler._top_level_class_tree(obj)
            if reused is None:
                continue
            assert ast.dump(reused) == ast.dump(ast.parse(inspect.getsource(obj)))
            checked += 1
    assert checked >= 20
    ExceptionFinder.clear_cache()
