import logging
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, status
from starlette.status import HTTP_404_NOT_FOUND

from richapi.exc_parser.openapi import compile_openapi_from_fastapi
from richapi.exc_parser.protocol import BaseHTTPException

app = FastAPI()


logging.getLogger().addHandler(logging.StreamHandler())


class FirstException(HTTPException): ...


class SecondException(HTTPException): ...


class ThirdException(HTTPException): ...


class FourthException(HTTPException): ...


class FifthException(BaseHTTPException):
    status_code = 405
    detail = "I hate this parsing thing :((((("


class SixthException(HTTPException): ...


class SeventhException(HTTPException): ...


class EighthException(HTTPException): ...


@lru_cache
def foo(func): ...


def raise_another():
    raise EighthException(status_code=409, detail="Another one!")


async def get_another_user():
    raise SecondException(status_code=402, detail="Yet another function!")


def get_user(opa: str = Depends(get_another_user)):
    raise ThirdException(status_code=403, detail="HAHA")


class NoNeedParanthesis(HTTPException):
    def __init__(self, status_code=407, detail="WOW!"):
        super().__init__(status_code=status_code, detail=detail)


@app.get("/home")
def home(item: int, user: str = Depends(get_user)):
    if item == 1:
        raise FourthException(
            status_code=HTTP_404_NOT_FOUND,
            detail="I need a really long sentence so I can analyze...",
        )

    if item == 2:
        exception = FifthException()
        raise exception

    if item == 3:
        raise SixthException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Hillow hillow"
        )

    if item == 4:
        raise NoNeedParanthesis

    if item == 5:
        raise SeventhException(status_code=408)

    raise_another()


def test_case():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_exc_raising_cases"
    )
    home_responses = openapi_json["paths"]["/home"]["get"]["responses"]
    assert "402" in home_responses
    assert "403" in home_responses
    assert "404" in home_responses
    assert "405" in home_responses
    assert "406" in home_responses
    assert "407" in home_responses
    assert "408" in home_responses
    assert "409" in home_responses
