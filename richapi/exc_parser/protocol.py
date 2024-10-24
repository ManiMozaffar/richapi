from __future__ import annotations

from typing import Any, ClassVar, Literal

from fastapi import HTTPException
from pydantic import BaseModel, TypeAdapter, create_model
from pydantic.dataclasses import dataclass


class HTTPExceptionSchema(BaseModel):
    response_schema_json: dict[str, Any]
    """Json schema representing the respone of the exception"""
    schema_name: str
    """Name of the schema"""
    schema_desc: str
    """Description of the schema"""
    status_code: int
    """Status code of the exception"""


class BaseHTTPException(HTTPException):
    status_code: int
    detail: str

    def __init__(self):
        super().__init__(status_code=self.status_code, detail=self.detail)

    @classmethod
    def get_json_schema(cls) -> HTTPExceptionSchema:
        value = _generic_json_schema_builder(cls)
        assert (
            value is not None
        )  # should never happen because status code is always set
        return value


@dataclass
class RichHTTPException(HTTPException):
    status_code: ClassVar[int] = 422
    """HTTP Status code to raise"""

    _validate_arg_types: ClassVar[bool] = True
    """Whether to run validation on arguements"""

    @classmethod
    def get_json_schema(cls) -> HTTPExceptionSchema:
        adapter = TypeAdapter(cls)
        schema = adapter.json_schema()
        schema.pop("status_code", None)

        schema_desc = cls.__doc__
        if schema_desc == cls.__name__ + "()" or schema_desc is None:
            schema_desc = "No description provided"

        return HTTPExceptionSchema(
            response_schema_json=schema,
            schema_name=f"{cls.__name__}Schema",
            status_code=cls.status_code,
            schema_desc=schema_desc,
        )


def try_to_camel_case(string: str) -> str:
    final_str = string
    if " " in final_str:  # with space
        components = string.split(" ")
        final_str = components[0] + "".join(x.title() for x in components[1:])

    if "_" in final_str:  # snake case
        components = string.split("_")
        final_str = components[0] + "".join(x.title() for x in components[1:])

    if "-" in final_str:  # kebab case
        components = string.split("-")
        final_str = components[0] + "".join(x.title() for x in components[1:])

    return final_str


def _generic_json_schema_builder(
    cls: type[Exception],
    detail: str | None = None,
    status_code: int | None = None,
) -> HTTPExceptionSchema | None:
    name = f"{cls.__name__}ErrorSchema"

    if hasattr(cls, "detail") and cls.detail and detail is None:  # type: ignore
        detail = cls.detail  # type: ignore

    if hasattr(cls, "status_code") and cls.status_code and status_code is None:  # type: ignore
        status_code = cls.status_code  # type: ignore

    if status_code is None:
        return None

    if detail is not None:
        detail_type = Literal[detail]  # type: ignore

        name = f"{try_to_camel_case(detail)}Schema"
    else:
        detail_type = str

    schema = create_model(name, detail=(detail_type, ...))

    return HTTPExceptionSchema(
        response_schema_json=schema.model_json_schema(),
        schema_name=name,
        status_code=status_code,
        schema_desc=detail or "No description provided",  # type: ignore
    )
