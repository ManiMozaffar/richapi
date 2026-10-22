from typing import Optional

from fastapi import FastAPI, HTTPException

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = FastAPI()


class Repo:
    def find(self):
        raise HTTPException(status_code=404, detail="Repo not found!")


class Service:
    async def run(self):
        raise HTTPException(status_code=409, detail="Service conflict!")


class Inner:
    def run(self):
        raise HTTPException(status_code=418, detail="Inner teapot!")


class Outer:
    def get_inner(self) -> Inner:
        return Inner()


class Untyped:
    def find(self):
        raise HTTPException(status_code=410, detail="Untyped gone!")


def get_repo() -> Repo:
    return Repo()


def get_optional_repo() -> Optional[Repo]:
    return Repo()


def get_service() -> Service:
    return Service()


def get_outer() -> Outer:
    return Outer()


def get_untyped():
    return Untyped()


@app.get("/class")
def from_class():
    Repo().find()


@app.get("/factory")
def from_factory():
    get_repo().find()


@app.get("/optional")
def from_optional():
    repo = get_optional_repo()
    if repo is not None:
        repo.find()


@app.get("/async")
async def from_async():
    await get_service().run()


@app.get("/assigned")
def from_assigned():
    repo = get_repo()
    repo.find()


@app.get("/chained")
def from_chained():
    get_outer().get_inner().run()


@app.get("/untyped")
def from_untyped():
    get_untyped().find()


def _responses(path: str) -> dict:
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_returned_value_calls"
    )
    return openapi_json["paths"][path]["get"]["responses"]


def test_method_on_class_instance():
    assert "404" in _responses("/class")


def test_method_on_returned_value():
    assert "404" in _responses("/factory")


def test_method_on_optional_returned_value():
    assert "404" in _responses("/optional")


def test_async_method_on_returned_value():
    assert "409" in _responses("/async")


def test_method_on_value_assigned_from_call():
    assert "404" in _responses("/assigned")


def test_chained_methods_on_returned_values():
    assert "418" in _responses("/chained")


def test_unannotated_factory_finds_nothing():
    assert "410" not in _responses("/untyped")
