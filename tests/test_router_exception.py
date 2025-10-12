# from dataclasses import dataclass
# from typing import Literal

import random
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from richapi.exc_parser.handler import add_exc_handler
from richapi.exc_parser.openapi import enrich_openapi, find_exceptions_in_api_functions
from richapi.exc_parser.protocol import RichHTTPException


@dataclass
class Exception1(RichHTTPException):
    status_code = 409


@dataclass
class Exception2(RichHTTPException):
    status_code = 408


class NWrapper(BaseModel):
    value: int


def lol():
    if random.randint(1, 3) == 2:
        raise Exception1()
    return lol()


app = FastAPI()

app.openapi = enrich_openapi(app, target_module="tests.test_recursive_func")
add_exc_handler(app)


@app.get("/{n}", response_model=NWrapper)
async def index(n: int) -> JSONResponse:
    lol()
    if n % 2 == 0:
        raise Exception2()
    return JSONResponse(content=jsonable_encoder(NWrapper(value=n)))


def test_find_exceptions_in_api_functions():
    result = find_exceptions_in_api_functions(
        [index],
        target_module="tests.test_router_exception",
        fastapi_app=app,
    )
    assert result == {Exception1, Exception2}
