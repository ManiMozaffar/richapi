import re

import fastapi
from fastapi import HTTPException
from pydantic.dataclasses import dataclass

from richapi.exc_parser.openapi import compile_openapi_from_fastapi
from richapi.exc_parser.protocol import RichHTTPException
from tests.app import quota as other

VALID_KEY = re.compile(r"^[a-zA-Z0-9\.\-_]+$")

app = fastapi.FastAPI()


@dataclass
class Quota(RichHTTPException):
    """Monthly quota reached"""

    plan: str
    status_code = 402


@app.get("/invalid")
async def invalid():
    raise HTTPException(400, "Bad input! (see docs)")


@app.get("/only-symbols")
async def only_symbols():
    raise HTTPException(400, "!!!")


@app.get("/valid")
async def valid():
    raise HTTPException(404, "Not found")


@app.get("/quota")
async def quota():
    raise Quota(plan="free")


@app.get("/other-quota")
async def other_quota():
    raise other.Quota(resets_in=60)


@app.get("/quota-again")
async def quota_again():
    raise Quota(plan="pro")


@app.get("/not-found-spaced")
async def not_found_spaced():
    raise HTTPException(404, "not found")


@app.get("/not-found-snake")
async def not_found_snake():
    raise HTTPException(404, "not_found")


def _compile() -> dict:
    return compile_openapi_from_fastapi(app, "tests")


def _ref(openapi: dict, path: str, status: str) -> str:
    schema = openapi["paths"][path]["get"]["responses"][status]["content"][
        "application/json"
    ]["schema"]
    return schema["$ref"].rsplit("/", 1)[-1]


def test_all_component_names_are_valid():
    schemas = _compile()["components"]["schemas"]
    assert [name for name in schemas if not VALID_KEY.match(name)] == []


def test_invalid_characters_are_stripped():
    openapi = _compile()
    assert _ref(openapi, "/invalid", "400") == "BadInputSeeDocsSchema"


def test_detail_without_valid_characters_falls_back_to_class_name():
    openapi = _compile()
    assert _ref(openapi, "/only-symbols", "400") == "HTTPExceptionErrorSchema"


def test_valid_names_are_unchanged():
    openapi = _compile()
    assert _ref(openapi, "/valid", "404") == "NotFoundSchema"
    assert _ref(openapi, "/quota", "402") == "QuotaSchema"


def test_same_named_classes_get_distinct_components():
    openapi = _compile()
    schemas = openapi["components"]["schemas"]
    mine = _ref(openapi, "/quota", "402")
    theirs = _ref(openapi, "/other-quota", "429")
    assert mine != theirs
    assert "plan" in schemas[mine]["properties"]
    assert "resets_in" in schemas[theirs]["properties"]


def test_identical_schemas_share_one_component():
    openapi = _compile()
    assert _ref(openapi, "/quota", "402") == _ref(openapi, "/quota-again", "402")
    quota_names = [n for n in openapi["components"]["schemas"] if "Quota" in n]
    assert len(quota_names) == 2


def test_details_camel_casing_to_same_name_get_distinct_components():
    openapi = _compile()
    schemas = openapi["components"]["schemas"]
    spaced = _ref(openapi, "/not-found-spaced", "404")
    snake = _ref(openapi, "/not-found-snake", "404")
    assert spaced != snake
    assert schemas[spaced]["properties"]["detail"]["const"] == "not found"
    assert schemas[snake]["properties"]["detail"]["const"] == "not_found"


def test_compile_twice_gives_same_names():
    assert _compile() == _compile()
