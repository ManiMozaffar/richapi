# from dataclasses import dataclass
# from typing import Literal

import random
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from richapi.exc_parser.handler import add_exc_handler
from richapi.exc_parser.openapi import compile_openapi_from_fastapi, enrich_openapi
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


def test_recursive_error_in_function():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_recursive_func"
    )
    openapi_responses = openapi_json["paths"]["/{n}"]["get"]["responses"]
    assert "409" in openapi_responses
    assert "408" in openapi_responses
