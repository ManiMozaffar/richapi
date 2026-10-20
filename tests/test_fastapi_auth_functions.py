import fastapi
import fastapi.security

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = fastapi.FastAPI()


http_bearer = fastapi.security.HTTPBearer()


def get_at_11(
    token: fastapi.security.HTTPAuthorizationCredentials = fastapi.Depends(http_bearer),
) -> str:
    return "12312"


@app.get("/refresh")
async def refresh_token(
    token_data: str = fastapi.Depends(get_at_11),
) -> None:
    pass


def test_fastapi_call_detected():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_fastapi_auth_functions"
    )
    home_responses = openapi_json["paths"]["/refresh"]["get"]["responses"]
    # Newer FastAPI raises self.make_not_authenticated_error() (401), older raised 403 inline.
    new_style = hasattr(fastapi.security.HTTPBearer, "make_not_authenticated_error")
    assert ("401" if new_style else "403") in home_responses
