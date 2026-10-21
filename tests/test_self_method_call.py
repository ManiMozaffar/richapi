from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = FastAPI()


class BaseChecker:
    def check(self, value: str) -> str:
        if not value:
            raise HTTPException(status_code=401, detail="Missing value!")
        return value

    @staticmethod
    def check_static(value: str) -> str:
        if not value:
            raise HTTPException(status_code=403, detail="Missing static value!")
        return value


class Checker(BaseChecker):  # like APIKeyHeader calling APIKeyBase.check_api_key
    def __call__(self, value: str = "") -> str:
        return self.check(value)


class StaticChecker(BaseChecker):
    def __call__(self, value: str = "") -> str:
        return self.check_static(value)


@app.get("/method")
def method(_: str = Depends(Checker())):
    pass


@app.get("/static-method")
def static_method(_: str = Depends(StaticChecker())):
    pass


@app.get("/api-key")
def api_key(_: str = Depends(APIKeyHeader(name="X-Key"))):
    pass


def test_self_method_call():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_self_method_call"
    )
    paths = openapi_json["paths"]
    assert "401" in paths["/method"]["get"]["responses"]
    assert "403" in paths["/static-method"]["get"]["responses"]
    # FastAPI >= 0.115.8 raises from self.check_api_key(): 403 before 0.122, 401 after
    assert {"401", "403"} & set(paths["/api-key"]["get"]["responses"])
    details = str(openapi_json["components"]["schemas"])
    assert "Missing value!" in details and "Missing static value!" in details
