from fastapi import APIRouter, Depends, FastAPI, HTTPException

from richapi.exc_parser.openapi import (
    compile_openapi_from_fastapi,
    find_exceptions_in_api_functions,
)
from richapi.exc_parser.protocol import RichHTTPException


class NotAllowed(RichHTTPException):
    status_code = 403


class ItemMissing(RichHTTPException):
    status_code = 404


class Conflict(RichHTTPException):
    status_code = 409


def check_admin() -> None:
    raise NotAllowed()


def check_tenant() -> None:
    raise HTTPException(status_code=401, detail="Unknown tenant")


items = APIRouter(prefix="/items", dependencies=[Depends(check_admin)])
admin = APIRouter(prefix="/admin")
hidden = APIRouter(prefix="/hidden")


@items.get("/{item_id}")
async def get_item(item_id: int) -> None:
    raise ItemMissing()


@admin.post("/")
async def create_admin() -> None:
    raise Conflict()


@hidden.get("/")
async def hidden_route() -> None:
    raise Conflict()


admin.include_router(items)
app = FastAPI()
app.include_router(admin, prefix="/v1", dependencies=[Depends(check_tenant)])
app.include_router(hidden, include_in_schema=False)


def test_nested_include_router():
    schema = compile_openapi_from_fastapi(app, target_module="tests")
    assert set(schema["paths"]) == {"/v1/admin/items/{item_id}", "/v1/admin/"}

    item = schema["paths"]["/v1/admin/items/{item_id}"]["get"]["responses"]
    assert {"401", "403", "404"} <= set(item)

    created = schema["paths"]["/v1/admin/"]["post"]["responses"]
    assert {"401", "409"} <= set(created)
    assert "403" not in created  # items' dependency must not leak to its parent


def test_find_exceptions_in_included_route():
    result = find_exceptions_in_api_functions(
        [get_item], fastapi_app=app, target_module="tests"
    )
    assert {NotAllowed, ItemMissing} <= result
