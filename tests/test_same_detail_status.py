from fastapi import FastAPI, HTTPException

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = FastAPI()


@app.get("/item")
def get_item(item: int):
    if item == 1:
        raise HTTPException(404, "Gone")
    raise HTTPException(410, "Gone")


def test_same_detail_with_different_status_codes():
    openapi_json = compile_openapi_from_fastapi(app, __name__)
    responses = openapi_json["paths"]["/item"]["get"]["responses"]
    ref = {"$ref": "#/components/schemas/GoneSchema"}
    assert responses["404"]["content"]["application/json"]["schema"] == ref
    assert responses["410"]["content"]["application/json"]["schema"] == ref
    properties = openapi_json["components"]["schemas"]["GoneSchema"]["properties"]
    assert properties["detail"]["const"] == "Gone"
