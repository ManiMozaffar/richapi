from fastapi import FastAPI, HTTPException

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = FastAPI()


@app.get("/assigned")
def raise_assigned(item: int):
    already_taken = HTTPException(status_code=409, detail="Already taken!")
    if item:
        raise already_taken


def test_raise_assigned_exception():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_raise_assigned_exception"
    )
    assert "409" in openapi_json["paths"]["/assigned"]["get"]["responses"]
    assert "Already taken!" in str(openapi_json["components"]["schemas"])
