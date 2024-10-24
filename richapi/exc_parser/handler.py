from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter
from starlette.requests import Request
from starlette.responses import Response

from richapi.exc_parser.protocol import RichHTTPException


async def _handle_rich_http_exception(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RichHTTPException)

    adapter = TypeAdapter(exc.__class__)
    if exc._validate_arg_types:
        adapter.validate_python(exc)

    json_response = adapter.dump_python(exc)
    return JSONResponse(content=json_response, status_code=exc.status_code)


def add_exc_handler(app: FastAPI):
    app.add_exception_handler(RichHTTPException, handler=_handle_rich_http_exception)
