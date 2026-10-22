import re

from fastapi import FastAPI, HTTPException, status
from starlette.exceptions import HTTPException as StarletteHTTPException

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = FastAPI()


@app.get("/fetch")
def fetch(item: int):
    try:
        return {"item": item}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error fetching details: {str(e)}",
        )


@app.get("/positional")
def positional(item_id: int):
    raise HTTPException(404, detail=f"Item {item_id!r:>10} not found (try again)")


@app.get("/only-placeholder")
def only_placeholder(item: int):
    try:
        return {"item": item}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{e}")


@app.get("/only-placeholder-positional")
def only_placeholder_positional(item: int):
    try:
        return {"item": item}
    except Exception as e:
        raise HTTPException(500, detail=f"{e!r}")


@app.get("/user")
def user(user_id: int):
    raise HTTPException(status_code=404, detail=f"User {user_id} does not exist")


@app.get("/order")
def order(order_id: int):
    raise HTTPException(status_code=404, detail=f"Order {order_id} was cancelled")


@app.get("/dict")
def dict_detail():
    raise HTTPException(
        status_code=422,
        detail={
            "field": "value",
            "code": 7,
            "ratio": 0.5,
            "retry": False,
            "hint": None,
        },
    )


@app.get("/dict-fstring")
def dict_fstring(value: int):
    raise HTTPException(
        status_code=409, detail={"msg": f"Value {value} is taken", "value": value}
    )


KEY = "field"


@app.get("/dict-name-key")
def dict_name_key():
    raise HTTPException(status_code=422, detail={KEY: "value"})


@app.get("/constant")
def constant():
    raise HTTPException(status_code=404, detail="Item not found")


@app.get("/positional-fstring")
def positional_fstring(item_id: int):
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown id {item_id}")


@app.get("/positional-dict")
def positional_dict():
    raise HTTPException(422, {"field": "item_id", "msg": f"bad {1}"})


@app.get("/starlette-positional")
def starlette_positional(item_id: int):
    raise StarletteHTTPException(403, f"Access denied to {item_id}")


class WhatNotFound(HTTPException):
    def __init__(self, what: str):
        super().__init__(404, detail=f"{what} is gone")


@app.get("/custom-signature")
def custom_signature(item_id: int):
    raise WhatNotFound(f"Order {item_id} lookup")


FORBIDDEN = 403


@app.get("/constant-status-fstring")
def constant_status_fstring(item_id: int):
    raise HTTPException(FORBIDDEN, f"No access to {item_id}")


def _openapi() -> dict:
    return compile_openapi_from_fastapi(app, __name__)


def _response(openapi: dict, path: str, status_code: int) -> dict:
    return openapi["paths"][path]["get"]["responses"][str(status_code)]


def _component(openapi: dict, path: str, status_code: int) -> dict:
    ref = _response(openapi, path, status_code)["content"]["application/json"]
    name = ref["schema"]["$ref"].rsplit("/", 1)[-1]
    return openapi["components"]["schemas"][name]


def _ref_name(openapi: dict, path: str, status_code: int) -> str:
    ref = _response(openapi, path, status_code)["content"]["application/json"]
    return ref["schema"]["$ref"].rsplit("/", 1)[-1]


def test_fstring_detail_keyword_status():
    openapi = _openapi()
    assert _ref_name(openapi, "/fetch", 400) == "ErrorFetchingDetailsSchema"
    assert _response(openapi, "/fetch", 400)["description"] == (
        "Error fetching details: {...}"
    )
    detail = _component(openapi, "/fetch", 400)["properties"]["detail"]
    assert detail["type"] == "string"
    assert detail["pattern"] == "^Error fetching details: .*$"
    assert re.fullmatch(detail["pattern"], "Error fetching details: timeout")


def test_fstring_detail_positional_status():
    openapi = _openapi()
    assert _ref_name(openapi, "/positional", 404) == "ItemNotFoundTryAgainSchema"
    assert _response(openapi, "/positional", 404)["description"] == (
        "Item {...} not found (try again)"
    )
    detail = _component(openapi, "/positional", 404)["properties"]["detail"]
    assert detail["pattern"] == r"^Item .* not found \(try again\)$"
    assert re.fullmatch(detail["pattern"], "Item         42 not found (try again)")
    assert not re.fullmatch(detail["pattern"], "Item 42 not found")


def test_fstring_detail_only_placeholders_falls_back():
    openapi = _openapi()
    assert _ref_name(openapi, "/only-placeholder", 500) == "HTTPExceptionErrorSchema"
    assert _response(openapi, "/only-placeholder", 500)["description"] == (
        "No description provided"
    )
    assert _component(openapi, "/only-placeholder", 500) == {
        "properties": {"detail": {"title": "Detail", "type": "string"}},
        "required": ["detail"],
        "title": "HTTPExceptionErrorSchema",
        "type": "object",
    }


def test_fstring_detail_only_placeholders_positional_status_unchanged():
    openapi = _openapi()
    assert (
        _ref_name(openapi, "/only-placeholder-positional", 500)
        == "InternalServerErrorSchema"
    )


def test_different_fstrings_get_distinct_components():
    openapi = _openapi()
    user_name = _ref_name(openapi, "/user", 404)
    order_name = _ref_name(openapi, "/order", 404)
    assert user_name == "UserDoesNotExistSchema"
    assert order_name == "OrderWasCancelledSchema"
    user_pattern = _component(openapi, "/user", 404)["properties"]["detail"]["pattern"]
    order_pattern = _component(openapi, "/order", 404)["properties"]["detail"][
        "pattern"
    ]
    assert re.fullmatch(user_pattern, "User 3 does not exist")
    assert not re.fullmatch(user_pattern, "Order 3 was cancelled")
    assert re.fullmatch(order_pattern, "Order 3 was cancelled")


def test_dict_detail_with_constant_values():
    openapi = _openapi()
    assert (
        _ref_name(openapi, "/dict", 422) == "HTTPExceptionFieldCodeRatioRetryHintSchema"
    )
    detail = _component(openapi, "/dict", 422)["properties"]["detail"]
    assert detail["type"] == "object"
    assert detail["required"] == ["field", "code", "ratio", "retry", "hint"]
    assert detail["properties"] == {
        "field": {"type": "string"},
        "code": {"type": "integer"},
        "ratio": {"type": "number"},
        "retry": {"type": "boolean"},
        "hint": {"type": "null"},
    }


def test_dict_detail_with_fstring_value():
    openapi = _openapi()
    assert _ref_name(openapi, "/dict-fstring", 409) == "HTTPExceptionMsgValueSchema"
    detail = _component(openapi, "/dict-fstring", 409)["properties"]["detail"]
    assert detail["required"] == ["msg", "value"]
    assert detail["properties"] == {"msg": {"type": "string"}, "value": {}}


def test_dict_detail_with_non_constant_key_falls_back():
    openapi = _openapi()
    assert _ref_name(openapi, "/dict-name-key", 422) == "HTTPExceptionErrorSchema"


def test_constant_detail_unchanged():
    openapi = _openapi()
    assert _response(openapi, "/constant", 404)["description"] == "Item not found"
    assert _component(openapi, "/constant", 404) == {
        "properties": {
            "detail": {
                "const": "Item not found",
                "enum": ["Item not found"],
                "title": "Detail",
                "type": "string",
            }
        },
        "required": ["detail"],
        "title": "ItemNotFoundSchema",
        "type": "object",
    }


def test_positional_fstring_detail():
    openapi = _openapi()
    assert _ref_name(openapi, "/positional-fstring", 400) == "UnknownIdSchema"
    assert _response(openapi, "/positional-fstring", 400)["description"] == (
        "Unknown id {...}"
    )
    pattern = _component(openapi, "/positional-fstring", 400)["properties"]["detail"][
        "pattern"
    ]
    assert re.fullmatch(pattern, "Unknown id 12")


def test_positional_dict_detail():
    openapi = _openapi()
    assert _ref_name(openapi, "/positional-dict", 422) == "HTTPExceptionFieldMsgSchema"
    detail = _component(openapi, "/positional-dict", 422)["properties"]["detail"]
    assert detail["properties"] == {
        "field": {"type": "string"},
        "msg": {"type": "string"},
    }


def test_starlette_positional_fstring_detail():
    openapi = _openapi()
    assert _ref_name(openapi, "/starlette-positional", 403) == "AccessDeniedToSchema"
    pattern = _component(openapi, "/starlette-positional", 403)["properties"]["detail"][
        "pattern"
    ]
    assert re.fullmatch(pattern, "Access denied to 7")


def test_custom_signature_positional_arg_is_not_detail():
    openapi = _openapi()
    # `what` is not the detail; output stays what it was before positional support
    assert "404" not in openapi["paths"]["/custom-signature"]["get"]["responses"]


def test_positional_fstring_detail_with_constant_status():
    openapi = _openapi()
    assert _ref_name(openapi, "/constant-status-fstring", 403) == "NoAccessToSchema"
