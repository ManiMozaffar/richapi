import ast
import inspect
import typing
from functools import reduce
from logging import getLogger
from typing import Callable, Union

import fastapi
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.openapi.utils import get_openapi as _get_openapi
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from richapi.exc_parser.compiler import (
    ExceptionFinder,
)
from richapi.exc_parser.compiler import (
    find_explicit_exceptions as _find_explicit_exceptions,
)
from richapi.exc_parser.protocol import (
    BaseHTTPException,
    HTTPExceptionSchema,
    _generic_json_schema_builder,
)
from richapi.exceptions import BaseRichAPIException

logger = getLogger(__name__)


def load_openapi(
    app: FastAPI,
    openapi_json: dict,
) -> Callable:
    return lambda: openapi_json


def enrich_openapi(
    app: FastAPI,
    target_module: Union[list[str], str, None] = None,
    open_api_getter: Callable[[FastAPI], dict] = lambda app: _get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    ),
) -> Callable:
    if target_module is None:
        target_module = _find_module_name_where_app_defined_in(app)

        if target_module is None or target_module == "__main__":
            raise BaseRichAPIException(
                "Could not determine the module where the FastAPI instance was created.\n"
                "Please provide the module name as a string or list of strings.\n"
                "Example: enrich_openapi(app, target_module='src')\n"
            )

        target_module = target_module.split(".")[0]  # get the top-level module

    def _custom_openapi() -> dict:
        if app.openapi_schema:  # pragma: no cover
            return app.openapi_schema

        app.openapi_schema = compile_openapi_from_fastapi(
            app, target_module, open_api_getter
        )
        return app.openapi_schema

    return _custom_openapi


def compile_openapi_from_fastapi(
    app: FastAPI,
    target_module: Union[list[str], str],
    open_api_getter: Callable[[FastAPI], dict] = lambda app: _get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    ),
) -> dict:
    target_module = [target_module] if isinstance(target_module, str) else target_module
    target_module.append("fastapi")

    openapi_schema = open_api_getter(app)
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        if route.include_in_schema:
            exceptions = _extract_starlette_exceptions(route, target_module)

            _fill_openapi_with_excpetions(openapi_schema, route, exceptions)

    ExceptionFinder.clear_cache()

    return openapi_schema


def _find_module_name_where_app_defined_in(app: FastAPI) -> Union[str, None]:
    frame = inspect.currentframe()
    target_module = None
    while frame:
        for var_name, var_value in frame.f_globals.items():
            if isinstance(var_value, FastAPI) and var_value is app:
                target_module = frame.f_globals["__name__"]
                break
        if target_module:
            break
        frame = frame.f_back

    return target_module


def _resolve_status_and_detail_from_exc_type(
    exc_type: type[Exception],
    ast_raise: ast.Raise,
) -> Union[tuple[int, Union[str, None]], None]:
    if hasattr(exc_type, "status_code") and hasattr(exc_type, "detail"):
        return (int(exc_type.status_code), exc_type.detail)  # type: ignore

    ast_exc = ast_raise.exc
    if not ast_exc:
        return None

    ast_kwargs = getattr(ast_exc, "keywords", None)
    kwargs = {}
    found_status_code: Union[int, None] = None
    found_detail: Union[str, None] = None

    if isinstance(ast_kwargs, list):
        for kwarg in ast_kwargs:
            if not hasattr(kwarg, "arg"):
                continue

            # that's the keyword argument in StarletteHTTPException
            if kwarg.arg == "status_code":
                status_code_value = kwarg.value

                if isinstance(status_code_value, ast.Constant):
                    found_status_code: Union[int, None] = int(status_code_value.value)

                elif isinstance(status_code_value, ast.Attribute):
                    # maybe used like: status.HTTP_404_NOT_FOUND
                    left_hand_side = status_code_value.attr
                    found_status_code = getattr(fastapi.status, left_hand_side, None)

                elif isinstance(status_code_value, ast.Name):
                    # maybe used like: HTTP_404_NOT_FOUND
                    left_hand_side = status_code_value.id
                    found_status_code = getattr(fastapi.status, left_hand_side, None)

            elif kwarg.arg == "detail":
                detail_value = kwarg.value
                if isinstance(detail_value, ast.Constant):
                    found_detail: Union[str, None] = detail_value.value

            else:
                if isinstance(kwarg.value, ast.Constant):
                    kwargs[kwarg.arg] = kwarg.value.value

    if found_detail and found_status_code:
        return found_status_code, found_detail

    ast_args = getattr(ast_exc, "args", None)
    args = []

    if isinstance(ast_args, list):
        arg_values = [arg.value for arg in ast_args if isinstance(arg, ast.Constant)]

        # we have some non-constant args and some constant args
        if arg_values and len(arg_values) != len(ast_args):
            status_arg = [arg for arg in arg_values if isinstance(arg, int)]
            #  We can't construct the exception object anymore
            if found_status_code:  # we have found status code in kwargs
                return found_status_code, None
            elif status_arg:  #  fall back to finding any integer value
                return status_arg[0], None
            return None  # give up

        args.extend(arg_values)
    else:
        logger.debug(
            f"Could not extract args from exception {exc_type}: {ast.dump(ast_exc)}"
        )

    try:
        exc = exc_type(*args, **kwargs)
        if hasattr(exc, "status_code") and hasattr(exc, "detail"):
            return (int(exc.status_code), exc.detail)  # type: ignore

        if found_status_code:
            return found_status_code, None

    except Exception as err:
        logger.debug(
            f"Could not construct exception {exc_type} with args: {args} and kwargs: {kwargs}",
            exc_info=err,
        )

        if found_status_code:
            return found_status_code, None

    return None


def _extract_json_schema(
    ast_node: ast.Raise, exc: type[StarletteHTTPException]
) -> Union[HTTPExceptionSchema, None]:
    status_detail_pair = _resolve_status_and_detail_from_exc_type(exc, ast_node)
    if status_detail_pair is None:
        logger.debug(f"Could not resolve status code and detail for exception {exc}")
        return None
    status_code, detail = status_detail_pair
    schema = _generic_json_schema_builder(exc, detail, status_code)
    return schema


def _fill_openapi_with_excpetions(
    api_schema: dict,
    route: APIRoute,
    exceptions: list[tuple[type[StarletteHTTPException], ast.Raise]],
) -> None:
    added_schema_names = set()

    for exc, ast_node in exceptions:
        if hasattr(exc, "get_json_schema"):
            casted_exc = typing.cast(type[BaseHTTPException], exc)
            schema = casted_exc.get_json_schema()
        else:
            schema = _extract_json_schema(ast_node, exc)

        if schema is None or schema.schema_name in added_schema_names:
            continue

        added_schema_names.add(schema.schema_name)

        str_status_code = str(schema.status_code)
        component_schemas = api_schema.get("components", {}).get("schemas", {})
        if schema.schema_name not in component_schemas:
            if "components" not in api_schema:
                api_schema["components"] = {"schemas": {}}
            if "schemas" not in api_schema["components"]:
                api_schema["components"]["schemas"] = {}

            api_schema["components"]["schemas"][schema.schema_name] = (
                schema.response_schema_json
            )

        path = route.path
        methods = [method.lower() for method in getattr(route, "methods")]

        for method in methods:
            this_status_resp = api_schema["paths"][path][method]["responses"].get(
                str_status_code, None
            )

            if this_status_resp is None:
                api_schema["paths"][path][method]["responses"][str_status_code] = {
                    "description": schema.schema_desc,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": f"#/components/schemas/{schema.schema_name}"
                            }
                        }
                    },
                }

            else:
                # HANDLE UNION
                this_schema = this_status_resp["content"]["application/json"]["schema"]

                if "anyOf" not in this_schema:
                    this_status_resp["content"]["application/json"]["schema"] = {
                        "anyOf": [
                            this_schema,
                            {"$ref": f"#/components/schemas/{schema.schema_name}"},
                        ]
                    }

                else:
                    this_schema["anyOf"].append(
                        {"$ref": f"#/components/schemas/{schema.schema_name}"}
                    )


def build_dependency_tree(dependant: Dependant) -> list[Callable]:
    """
    Traverse the dependency tree and find all functions ('call' attribute)
    from the dependencies that include 'func' in their name or signature.
    """
    dependencies_with_func: list[Callable] = []
    if dependant.call:
        dependencies_with_func.append(dependant.call)
    for inner_dep in dependant.dependencies:
        dependencies_with_func.extend(build_dependency_tree(inner_dep))
    return dependencies_with_func


T = typing.TypeVar("T")


def flatten(to_be_flatten: list[list[T]]) -> list[T]:
    return list(reduce(lambda x, y: x + y, to_be_flatten, []))


def _extract_starlette_exceptions(
    route: APIRoute, target_module: list[str]
) -> list[tuple[type[StarletteHTTPException], ast.Raise]]:
    dependency_tree = build_dependency_tree(route.dependant)
    exceptions = flatten(
        [_find_explicit_exceptions(dep, target_module) for dep in dependency_tree]
    )

    starlette_http_exc_types = [
        exc
        for exc in exceptions
        if exc[0] is not None and issubclass(exc[0], StarletteHTTPException)
    ]
    casted_exceptions = typing.cast(
        list[tuple[type[StarletteHTTPException], ast.Raise]],
        starlette_http_exc_types,
    )
    return casted_exceptions
