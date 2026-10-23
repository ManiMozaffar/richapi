from fastapi import APIRouter, FastAPI, HTTPException

from richapi.exc_parser.openapi import (
    compile_openapi_from_fastapi,
    default_openapi_getter,
)

app = FastAPI()
router = APIRouter(prefix="/orders")


@app.get("/items/{item_id}", responses={404: {"description": "Item not found"}})
def read_item(item_id: int):
    if item_id < 0:
        raise HTTPException(400, "Invalid id")
    if item_id != 42:
        raise HTTPException(404, "Item not found")
    return {"item_id": item_id}


@router.get("/{order_id}", responses={404: {"description": "Order not found"}})
def read_order(order_id: int):
    if order_id != 1:
        raise HTTPException(404, "Order not found")
    raise HTTPException(409, "Order locked")


app.include_router(router)


def test_docs_check_finds_undocumented_responses():
    # same code as the "Document it yourself, let richapi check it" example in docs/workflows.md
    documented = default_openapi_getter(app)
    found = compile_openapi_from_fastapi(app, __name__)

    missing = {}
    for path, operations in found["paths"].items():
        for method, operation in operations.items():
            written = documented["paths"][path][method]["responses"]
            if undocumented := set(operation["responses"]) - set(written):
                missing[f"{method.upper()} {path}"] = sorted(undocumented)

    # the included router's route is checked too, on every FastAPI version
    assert missing == {
        "GET /items/{item_id}": ["400"],
        "GET /orders/{order_id}": ["409"],
    }
