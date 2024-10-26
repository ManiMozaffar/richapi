import fastapi
import fastapi.security
from pydantic import BaseModel
from pydantic.dataclasses import dataclass

from richapi.exc_parser.handler import add_exc_handler
from richapi.exc_parser.openapi import compile_openapi_from_fastapi, enrich_openapi
from richapi.exc_parser.protocol import RichHTTPException

app = fastapi.FastAPI()
app.openapi = enrich_openapi(app)
add_exc_handler(app)


@dataclass
class NotEnoughBalance(RichHTTPException):
    """Custom exception for user balance"""

    user_id: int
    balance: float
    status_code = 409


class SuccessResponse(BaseModel):
    balance: float


def make_payment_or_raise():
    raise NotEnoughBalance(user_id=1, balance=0.5)


class PaymentService:
    def __init__(self):
        pass

    def create(self):
        make_payment_or_raise()


@app.post("/payment")
async def make_payment():
    obj = PaymentService()
    obj.create()


def test_class_is_detected():
    openapi_json = compile_openapi_from_fastapi(app, target_module="tests.test_class")
    home_responses = openapi_json["paths"]["/payment"]["post"]["responses"]
    assert "409" in home_responses
