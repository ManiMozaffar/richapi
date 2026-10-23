from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.routing import APIRoute

from richapi import FunctionException, exception_analysis, get_function_exceptions
from richapi.exc_parser import compiler, protocol
from richapi.exc_parser.openapi import compile_openapi_from_fastapi
from richapi.exceptions import BaseRichAPIException

MODULE = __name__

app = FastAPI()


def load_item(item_id: int):
    if item_id < 0:
        raise ValueError("negative id")
    raise HTTPException(404, "Item not found")


def require_token(token: str = ""):
    if not token:
        raise HTTPException(401, "Missing token")


@app.get("/items/{item_id}", responses={404: {"description": "Item not found"}})
def read_item(item_id: int, _: Annotated[None, Depends(require_token)]):
    return load_item(item_id)


@app.get("/documented", responses={401: {}, 404: {}})
def documented(item_id: int, _: Annotated[None, Depends(require_token)]):
    return load_item(item_id)


def not_a_route():
    raise HTTPException(418, "teapot")


def _caches_empty() -> bool:
    return not (
        compiler._tree_cache
        or compiler.ExceptionFinder.visited
        or compiler._returned_exc_cache
        or protocol._cached_generic_json_schema.cache_info().currsize
    )


def test_function_exceptions_lists_every_raise():
    found = get_function_exceptions(load_item, MODULE)

    assert all(isinstance(exc, FunctionException) for exc in found)
    by_type = {exc.exception: exc for exc in found}
    assert set(by_type) == {ValueError, HTTPException}

    not_found = by_type[HTTPException]
    assert not_found.status_code == 404
    assert not_found.schema is not None
    assert not_found.schema.schema_name == "ItemNotFoundSchema"
    assert not_found.raised_in is load_item

    # not an HTTP exception: no response to document
    assert by_type[ValueError].status_code is None
    assert by_type[ValueError].schema is None


def test_raised_in_points_at_the_callee():
    found = get_function_exceptions(read_item, MODULE)
    assert {exc.raised_in for exc in found if exc.status_code == 404} == {load_item}


def test_app_adds_route_dependencies():
    without_app = {
        exc.status_code for exc in get_function_exceptions(read_item, MODULE)
    }
    with_app = {
        exc.status_code for exc in get_function_exceptions(read_item, MODULE, app=app)
    }
    assert 401 not in without_app
    assert {401, 404} <= with_app


def test_app_given_but_function_is_not_a_route():
    with pytest.raises(BaseRichAPIException):
        get_function_exceptions(not_a_route, MODULE, app=app)


def test_call_outside_context_clears_caches():
    get_function_exceptions(load_item, MODULE)
    assert _caches_empty()


def test_context_keeps_caches_until_exit():
    with exception_analysis():
        get_function_exceptions(load_item, MODULE)
        assert compiler._tree_cache  # reused by later calls in the block
        get_function_exceptions(read_item, MODULE)
        assert compiler._tree_cache
    assert _caches_empty()


def test_nested_contexts_clear_on_outermost_exit():
    with exception_analysis():
        with exception_analysis():
            get_function_exceptions(load_item, MODULE)
        assert compiler._tree_cache
    assert _caches_empty()


def test_context_clears_caches_on_error():
    with pytest.raises(RuntimeError):
        with exception_analysis():
            get_function_exceptions(load_item, MODULE)
            raise RuntimeError
    assert _caches_empty()


def test_compile_openapi_clears_every_cache():
    compile_openapi_from_fastapi(app, MODULE)
    assert _caches_empty()


def test_compile_inside_context_keeps_caches():
    with exception_analysis():
        compile_openapi_from_fastapi(app, MODULE)
        assert compiler._tree_cache
    assert _caches_empty()


def test_check_every_exception_is_documented():
    # the docs' "document it yourself, let richapi check it" example
    missing = {}
    with exception_analysis():
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            found = get_function_exceptions(route.endpoint, MODULE, app=app)
            raised = {exc.status_code for exc in found if exc.status_code}
            documented = {int(code) for code in route.responses}
            if raised - documented:
                missing[route.path] = raised - documented

    assert missing == {"/items/{item_id}": {401}}
