import fastapi
import fastapi.security
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from richapi.exc_parser.openapi import compile_openapi_from_fastapi
from richapi.exc_parser.protocol import BaseHTTPException

app = FastAPI()

STRING_HEADER = {"schema": {"type": "string"}}


class TooManyRequests(BaseHTTPException):
    status_code = 429
    detail = "Slow down"
    headers = {"Retry-After": "60"}


class AuthRequired(HTTPException):
    def __init__(self):
        super().__init__(401, "Login first", headers={"WWW-Authenticate": "Basic"})


class Guard:
    # same shape as FastAPI's HTTPBase on newer versions
    def make_headers(self) -> dict[str, str]:
        return {"WWW-Authenticate": f"{type(self).__name__}"}

    def make_error(self) -> HTTPException:
        return HTTPException(401, "Not allowed", headers=self.make_headers())

    def __call__(self):
        raise self.make_error()


@app.get("/literal")
def literal():
    raise HTTPException(401, "auth", headers={"WWW-Authenticate": "Bearer"})


@app.get("/class-attr")
def class_attr():
    raise TooManyRequests()


@app.get("/constructed")
def constructed():
    raise AuthRequired()


@app.get("/merged")
def merged(item: int):
    if item:
        raise HTTPException(401, "first", headers={"WWW-Authenticate": "Bearer"})
    raise HTTPException(401, "second", headers={"X-Reason": "expired"})


@app.get("/no-headers")
def no_headers():
    raise HTTPException(404, "missing")


@app.get("/returned-method")
def returned_method(_: None = Depends(Guard())):
    pass


@app.get("/bearer")
def bearer(_=Depends(fastapi.security.HTTPBearer())):
    pass


def _responses(path: str) -> dict:
    openapi_json = compile_openapi_from_fastapi(app, __name__)
    return openapi_json["paths"][path]["get"]["responses"]


def test_literal_headers():
    assert _responses("/literal")["401"]["headers"] == {
        "WWW-Authenticate": STRING_HEADER
    }


def test_class_attribute_headers():
    assert _responses("/class-attr")["429"]["headers"] == {"Retry-After": STRING_HEADER}
    # and they are actually sent
    response = TestClient(app).get("/class-attr")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_constructed_exception_headers():
    assert _responses("/constructed")["401"]["headers"] == {
        "WWW-Authenticate": STRING_HEADER
    }


def test_same_status_headers_are_merged():
    response = _responses("/merged")["401"]
    assert "anyOf" in response["content"]["application/json"]["schema"]
    assert response["headers"] == {
        "WWW-Authenticate": STRING_HEADER,
        "X-Reason": STRING_HEADER,
    }


def test_no_headers_no_key():
    assert "headers" not in _responses("/no-headers")["404"]


def test_headers_from_returned_method():
    assert _responses("/returned-method")["401"]["headers"] == {
        "WWW-Authenticate": STRING_HEADER
    }


def test_http_bearer_headers():
    responses = _responses("/bearer")
    # Newer FastAPI raises self.make_not_authenticated_error() (401 + WWW-Authenticate),
    # older raised a bare 403.
    if hasattr(fastapi.security.HTTPBearer, "make_not_authenticated_error"):
        assert responses["401"]["headers"] == {"WWW-Authenticate": STRING_HEADER}
    else:
        assert "headers" not in responses["403"]
