from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = FastAPI()


class NotFoundBody(BaseModel):
    reason: str


@app.get("/description-only", responses={404: {"description": "nope"}})
async def description_only():
    raise HTTPException(404, "missing")


@app.get(
    "/text-only",
    responses={
        404: {
            "description": "nope",
            "content": {"text/plain": {"schema": {"type": "string"}}},
        }
    },
)
async def text_only():
    raise HTTPException(404, "missing")


@app.get("/json-model", responses={404: {"model": NotFoundBody}})
async def json_model():
    raise HTTPException(404, "missing")


def _404(path: str) -> dict:
    openapi_json = compile_openapi_from_fastapi(app, "tests")
    return openapi_json["paths"][path]["get"]["responses"]["404"]


def test_description_only_response_gets_json_schema():
    resp = _404("/description-only")
    assert resp["description"] == "nope"
    assert "$ref" in resp["content"]["application/json"]["schema"]


def test_non_json_content_is_kept():
    resp = _404("/text-only")
    assert resp["description"] == "nope"
    assert resp["content"]["text/plain"] == {"schema": {"type": "string"}}
    assert "$ref" in resp["content"]["application/json"]["schema"]


def test_json_content_is_merged_with_any_of():
    any_of = _404("/json-model")["content"]["application/json"]["schema"]["anyOf"]
    assert any_of[0] == {"$ref": "#/components/schemas/NotFoundBody"}
    assert len(any_of) == 2
