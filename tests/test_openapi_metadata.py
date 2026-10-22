import inspect

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from richapi.exc_parser.openapi import compile_openapi_from_fastapi, enrich_openapi
from richapi.exc_parser.protocol import RichHTTPException


class ItemMissing(RichHTTPException):
    status_code = 404


async def get_item(item_id: int) -> None:
    raise ItemMissing()


async def on_new_item() -> None:
    pass


EXTERNAL_DOCS = "external_docs" in inspect.signature(get_openapi).parameters


def make_app() -> FastAPI:
    extra = {"openapi_external_docs": {"url": "https://docs"}} if EXTERNAL_DOCS else {}
    app = FastAPI(
        title="T",
        version="1",
        summary="s",
        description="d",
        terms_of_service="https://tos",
        contact={"name": "c"},
        license_info={"name": "MIT"},
        servers=[{"url": "https://x"}],
        openapi_tags=[{"name": "a"}],
        **extra,
    )
    app.get("/items/{item_id}", tags=["a"])(get_item)
    app.webhooks.post("new-item")(on_new_item)
    return app


def assert_fastapi_schema_plus_exceptions(schema: dict) -> None:
    expected = make_app().openapi()

    responses = schema["paths"]["/items/{item_id}"]["get"]["responses"]
    added = responses.pop("404")
    name = added["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
    schema["components"]["schemas"].pop(name)

    assert schema == expected


def test_compile_keeps_app_metadata():
    schema = compile_openapi_from_fastapi(make_app(), __name__)

    assert schema["servers"] == [{"url": "https://x"}]
    assert schema["tags"] == [{"name": "a"}]
    assert schema["info"]["summary"] == "s"
    assert schema["info"]["contact"] == {"name": "c"}
    assert schema["info"]["license"] == {"name": "MIT"}
    assert schema["info"]["termsOfService"] == "https://tos"
    assert "new-item" in schema["webhooks"]
    if EXTERNAL_DOCS:
        assert schema["externalDocs"] == {"url": "https://docs"}

    assert_fastapi_schema_plus_exceptions(schema)


def test_enrich_openapi_keeps_app_metadata():
    app = make_app()
    app.openapi = enrich_openapi(app, __name__)

    assert_fastapi_schema_plus_exceptions(app.openapi())
