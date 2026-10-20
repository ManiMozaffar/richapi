from fastapi import Depends, FastAPI, HTTPException

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = FastAPI()


def make_error():
    return HTTPException(status_code=409, detail="Conflict!")


class Checker:
    def make_error(self):
        def nested():
            return HTTPException(
                status_code=499
            )  # nested scope, not returned by make_error

        return HTTPException(status_code=410, detail="Gone!")

    def __call__(self):
        raise self.make_error()


checker = Checker()


@app.get("/func")
def raise_func(item: int):
    raise make_error()


@app.get("/method")
def raise_method(_: None = Depends(checker)):  # like fastapi.security.HTTPBearer
    pass


@app.get("/obj-method")
def raise_obj_method(item: int):
    raise checker.make_error()


def test_raise_returned_exception():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_raise_returned_exception"
    )
    paths = openapi_json["paths"]
    assert "409" in paths["/func"]["get"]["responses"]
    assert "410" in paths["/method"]["get"]["responses"]
    assert "410" in paths["/obj-method"]["get"]["responses"]
    assert "499" not in paths["/method"]["get"]["responses"]
    details = str(openapi_json["components"]["schemas"])
    assert "Conflict!" in details and "Gone!" in details
