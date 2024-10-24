import fastapi
import fastapi.security
import pytest
from httpx import ASGITransport, AsyncClient
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


@app.post("/payment")
async def make_payment() -> SuccessResponse:
    raise NotEnoughBalance(user_id=1, balance=0.5)


def test_custom_exc_detected():
    openapi_json = compile_openapi_from_fastapi(
        app, target_module="tests.test_custom_exc"
    )
    home_responses = openapi_json["paths"]["/payment"]["post"]["responses"]
    assert "409" in home_responses


@pytest.mark.asyncio
async def test_make_payment():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post("/payment")

    assert response.status_code == 409
    expected_response = {"user_id": 1, "balance": 0.5}
    assert response.json() == expected_response
