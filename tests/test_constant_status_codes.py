from http import HTTPStatus

import pytest
import starlette.status
from fastapi import FastAPI, HTTPException

from richapi.exc_parser.openapi import compile_openapi_from_fastapi
from tests import constant_errors as errors

app = FastAPI()

FORBIDDEN = 403
MSG = "Forbidden by constant"


def compute() -> int:
    return 418


@app.get("/positional")
def positional():
    raise HTTPException(FORBIDDEN, MSG)


@app.get("/keyword")
def keyword():
    raise HTTPException(status_code=FORBIDDEN, detail=MSG)


@app.get("/http-status")
def http_status():
    raise HTTPException(HTTPStatus.NOT_FOUND, "Not found by enum")


@app.get("/http-status-keyword")
def http_status_keyword():
    raise HTTPException(status_code=HTTPStatus.GONE)


@app.get("/starlette-status")
def starlette_status():
    raise HTTPException(status_code=starlette.status.HTTP_409_CONFLICT)


@app.get("/module-attr")
def module_attr():
    raise HTTPException(status_code=errors.CONFLICT, detail=errors.CONFLICT_DETAIL)


@app.get("/call")
def call():
    raise HTTPException(status_code=compute())


@app.get("/call-positional")
def call_positional():
    raise HTTPException(compute(), "Computed")


@app.get("/local-shadow")
def local_shadow():
    FORBIDDEN = compute()
    raise HTTPException(FORBIDDEN, "Shadowed by local")


@app.get("/param-shadow")
def param_shadow(FORBIDDEN: int = 0):
    raise HTTPException(status_code=FORBIDDEN, detail=MSG)


def _responses(openapi_json: dict, path: str) -> dict:
    return openapi_json["paths"][path]["get"]["responses"]


@pytest.mark.parametrize(
    ("path", "status_code", "detail"),
    [
        ("/positional", "403", MSG),
        ("/keyword", "403", MSG),
        ("/http-status", "404", "Not found by enum"),
        ("/http-status-keyword", "410", None),
        ("/starlette-status", "409", None),
        ("/module-attr", "409", errors.CONFLICT_DETAIL),
    ],
)
def test_constant_status_codes(path: str, status_code: str, detail: str | None):
    openapi_json = compile_openapi_from_fastapi(app, __name__)
    assert status_code in _responses(openapi_json, path)
    if detail is not None:
        assert detail in str(openapi_json["components"]["schemas"])


def test_unresolvable_status_code_is_skipped():
    openapi_json = compile_openapi_from_fastapi(app, __name__)
    assert set(_responses(openapi_json, "/call")) == {"200"}
    assert set(_responses(openapi_json, "/call-positional")) == {"200"}


@pytest.mark.parametrize("path", ["/local-shadow", "/param-shadow"])
def test_local_name_shadowing_global_is_not_resolved(path: str):
    openapi_json = compile_openapi_from_fastapi(app, __name__)
    assert "403" not in _responses(openapi_json, path)
