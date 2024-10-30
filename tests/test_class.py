import fastapi
import fastapi.security
from pydantic.dataclasses import dataclass

from richapi.exc_parser.handler import add_exc_handler
from richapi.exc_parser.openapi import compile_openapi_from_fastapi, enrich_openapi
from richapi.exc_parser.protocol import RichHTTPException

app = fastapi.FastAPI()
app.openapi = enrich_openapi(app)
add_exc_handler(app)


@dataclass
class Exception1(RichHTTPException):
    status_code = 409


@dataclass
class Exception2(RichHTTPException):
    status_code = 408


@dataclass
class Exception3(RichHTTPException):
    status_code = 407


def foo1():
    raise Exception1()


def foo2():
    raise Exception2()


def foo3():
    raise Exception3()


class PaymentService:
    def __init__(self):
        foo1()

    def create(self):
        foo2()

    def update(self):
        foo3()


def make_payment_dep():
    obj = PaymentService()
    return obj


@app.post("/payment")
async def make_payment(
    obj2: PaymentService = fastapi.Depends(make_payment_dep),
):
    obj = PaymentService()
    obj.create()
    obj2.update()


def test_class_is_detected():
    openapi_json = compile_openapi_from_fastapi(app, target_module="tests.test_class")
    home_responses = openapi_json["paths"]["/payment"]["post"]["responses"]
    print(home_responses)
    assert "408" in home_responses
    assert "407" in home_responses
    assert "409" in home_responses
