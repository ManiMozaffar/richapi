import pytest
from fastapi import FastAPI, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = FastAPI()


def teapot():
    raise HTTPException(status_code=418, detail="Teapot!")


@app.get("/direct")
def direct():
    try:
        raise HTTPException(status_code=418, detail="Teapot!")
    except HTTPException:
        return 1


@app.get("/helper")
def helper():
    try:
        teapot()
    except HTTPException:
        return 1


@app.get("/helper-uncaught")  # same helper outside a try: still documented
def helper_uncaught():
    teapot()


@app.get("/base-class")
def base_class():
    try:
        teapot()
    except StarletteHTTPException:
        return 1


@app.get("/tuple")
def tuple_handler():
    try:
        teapot()
    except (ValueError, HTTPException):
        return 1


@app.get("/bare")
def bare():
    try:
        teapot()
    except:  # noqa: E722
        return 1


@app.get("/reraise")
def reraise():
    try:
        teapot()
    except HTTPException:
        raise


@app.get("/reraise-name")
def reraise_name():
    try:
        teapot()
    except HTTPException as error:
        raise error


@app.get("/other-type")
def other_type():
    try:
        teapot()
    except ValueError:
        return 1


@app.get("/in-handler")
def in_handler():
    try:
        teapot()
    except HTTPException:
        raise HTTPException(status_code=409, detail="Conflict!")


@pytest.fixture(scope="module")
def openapi_json() -> dict:
    return compile_openapi_from_fastapi(
        app, target_module="tests.test_caught_exceptions"
    )


def responses(openapi_json: dict, path: str) -> dict:
    return openapi_json["paths"][path]["get"]["responses"]


@pytest.mark.parametrize(
    "path", ["/direct", "/helper", "/base-class", "/tuple", "/bare"]
)
def test_caught_exception_is_dropped(openapi_json: dict, path: str):
    assert "418" not in responses(openapi_json, path)


@pytest.mark.parametrize(
    "path", ["/helper-uncaught", "/reraise", "/reraise-name", "/other-type"]
)
def test_uncaught_exception_is_kept(openapi_json: dict, path: str):
    assert "418" in responses(openapi_json, path)


def test_exception_raised_in_handler_is_kept(openapi_json: dict):
    assert "409" in responses(openapi_json, "/in-handler")
    assert "418" not in responses(openapi_json, "/in-handler")
