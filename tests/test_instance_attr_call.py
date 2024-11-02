import logging

import fastapi
import fastapi.security
from pydantic.dataclasses import dataclass

from richapi.exc_parser.openapi import compile_openapi_from_fastapi, enrich_openapi
from richapi.exc_parser.protocol import RichHTTPException

logging.getLogger().addHandler(logging.StreamHandler())

app = fastapi.FastAPI()
app.openapi = enrich_openapi(app, target_module="tests.test_instance_attr_call")


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

    def foo2(self):
        foo2()

    def foo3(self):
        foo3()


class PaymentOrchestrator:
    service: PaymentService

    def __init__(self, payment_service: PaymentService):
        self.service = payment_service

    def create_outer(self):
        self.service.foo2()
        self.update_outer()

    def update_outer(self):
        self.service.foo3()


@app.post("/payment")
async def make_payment():
    obj = PaymentOrchestrator(payment_service=PaymentService())
    obj.create_outer()


def test_class_is_detected():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_instance_attr_call"
    )
    home_responses = openapi_json["paths"]["/payment"]["post"]["responses"]
    print(home_responses)
    assert "408" in home_responses
    assert "407" not in home_responses
    assert "409" in home_responses
