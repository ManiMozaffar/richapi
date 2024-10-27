import fastapi
import fastapi.security

from richapi.exc_parser.openapi import compile_openapi_from_fastapi, enrich_openapi
from tests.app import foo1 as FooService

app = fastapi.FastAPI()
app.openapi = enrich_openapi(app)


@app.post("/payment")
async def make_payment():
    FooService.raise_exc()


def test_class_is_detected():
    openapi_json = compile_openapi_from_fastapi(app, target_module="tests")
    home_responses = openapi_json["paths"]["/payment"]["post"]["responses"]
    print(home_responses)
    assert "500" in home_responses
