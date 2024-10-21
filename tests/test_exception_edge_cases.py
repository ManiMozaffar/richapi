import random

from fastapi import FastAPI

from richapi.exc_parser.openapi import compile_openapi_from_fastapi, enrich_openapi
from richapi.exc_parser.protocol import BaseHTTPException

app = FastAPI()
app.openapi = enrich_openapi(app)


class InteralServer(BaseHTTPException):
    status_code = 500
    detail = "Internal server error"


class NotFound(BaseHTTPException):
    status_code = 501
    detail = "Not found"


class GatewayError(BaseHTTPException):
    status_code = 502
    detail = "Gateway error"


def very_nested():
    value = InteralServer
    raise value


def nested():
    try:
        very_nested()
    except InteralServer:
        raise NotFound


@app.get("/home")
def read_root() -> dict[str, str]:
    if random.choice([True, False]):
        nested()

    elif random.choice([True, False]):
        raise GatewayError()

    return {"Hello": "World"}


def test_read_root():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_exception_edge_cases"
    )
    home_responses = openapi_json["paths"]["/home"]["get"]["responses"]
    print(home_responses)
    assert "500" in home_responses
    assert "501" in home_responses
    assert "502" in home_responses
