from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import (
    APIKeyQuery,
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
    OpenIdConnect,
)

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = FastAPI()

optional_bearer = HTTPBearer(auto_error=False)


def check_key(key: str, auto_error: bool) -> Optional[str]:
    if not key:
        if auto_error:
            raise HTTPException(status_code=401, detail="Missing key")
        return None
    return key


class KeyScheme:  # passes the flag in, like APIKeyBase.check_api_key on FastAPI 0.115.8
    def __init__(self, auto_error: bool = True):
        self.auto_error = auto_error

    def __call__(self, key: str = "") -> Optional[str]:
        return check_key(key, self.auto_error)


@app.get("/key")
def key(_=Depends(KeyScheme())):
    pass


@app.get("/optional-key")
def optional_key(_=Depends(KeyScheme(auto_error=False))):
    pass


@app.get("/bearer")
def bearer(_=Depends(HTTPBearer())):
    pass


@app.get("/optional-bearer")
def optional_bearer_route(_=Depends(optional_bearer)):
    pass


@app.get("/optional-bearer-inline")
def optional_bearer_inline(
    _: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(HTTPBearer(auto_error=False))
    ],
):
    pass


def current_user(
    _: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(HTTPBearer(auto_error=False))
    ],
) -> str:
    return "anonymous"


@app.get("/optional-bearer-nested")
def optional_bearer_nested(_: Annotated[str, Depends(current_user)]):
    pass


@app.get("/optional-api-key")
def optional_api_key(_=Depends(APIKeyQuery(name="key", auto_error=False))):
    pass


@app.get("/optional-oauth2")
def optional_oauth2(
    _=Depends(OAuth2PasswordBearer(tokenUrl="token", auto_error=False)),
):
    pass


@app.get("/optional-openid")
def optional_openid(
    _=Depends(OpenIdConnect(openIdConnectUrl="/.well-known", auto_error=False)),
):
    pass


# Analyzed after the auto_error=False routes, so their results must not leak into it.
@app.get("/bearer-again")
def bearer_again(_=Depends(HTTPBearer())):
    pass


def error_statuses(openapi_json: dict, path: str) -> set[str]:
    responses = openapi_json["paths"][path]["get"]["responses"]
    return {status for status in responses if status.startswith("4")} - {"422"}


def test_auto_error_false_skips_the_errors_it_turns_off():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_auto_error"
    )
    assert error_statuses(openapi_json, "/bearer")
    assert error_statuses(openapi_json, "/bearer-again")
    assert error_statuses(openapi_json, "/key") == {"401"}
    for path in (
        "/optional-bearer",
        "/optional-bearer-inline",
        "/optional-bearer-nested",
        "/optional-api-key",
        "/optional-oauth2",
        "/optional-openid",
        "/optional-key",
    ):
        assert not error_statuses(openapi_json, path), path
