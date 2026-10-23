from __future__ import annotations

import functools
import re
from typing import Any, ClassVar, Literal, NamedTuple, Union

from fastapi import HTTPException
from pydantic import BaseModel, Field, TypeAdapter, create_model
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
    headers: list[str] = []
    """Names of the response headers the exception sets"""


class FStringDetail(NamedTuple):
    """detail=f"..." read from source: literal parts, None for each placeholder."""

    parts: tuple[Union[str, None], ...]


class DictDetail(NamedTuple):
    """detail={...} read from source: (key, value) pairs, each value a JSON type
    name, a nested DictDetail, or None when it can't be known statically."""

    items: tuple[tuple[str, Union[str, DictDetail, None]], ...]


_INVALID_NAME_CHARS = re.compile(r"[^a-zA-Z0-9.\-_]")
_REGEX_META_CHARS = re.compile(r"([\\^$.|?*+()\[\]{}])")


def _dict_detail_json_schema(detail: DictDetail) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for key, value in detail.items:
        if isinstance(value, DictDetail):
            properties[key] = _dict_detail_json_schema(value)
        else:
            properties[key] = {} if value is None else {"type": value}
    return {"properties": properties, "required": list(properties), "type": "object"}


class BaseHTTPException(HTTPException):
    status_code: int
    detail: str
    headers: dict[str, str] | None = None

    def __init__(self):
        super().__init__(
            status_code=self.status_code, detail=self.detail, headers=self.headers
        )

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
        # Building a TypeAdapter is expensive; build once per class, hand out copies.
        return _rich_json_schema(cls).model_copy(deep=True)


@functools.lru_cache(maxsize=None)
def _rich_json_schema(cls: type[RichHTTPException]) -> HTTPExceptionSchema:
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
    detail: str | FStringDetail | DictDetail | None = None,
    status_code: int | None = None,
) -> HTTPExceptionSchema | None:
    try:
        hash((cls, detail, status_code))
    except TypeError:  # e.g. dict detail, can't be cached
        return _build_generic_json_schema(cls, detail, status_code)

    # create_model() is expensive and the same exception is seen over and over; build once, hand out copies.
    schema = _cached_generic_json_schema(cls, detail, status_code)
    return None if schema is None else schema.model_copy(deep=True)


@functools.lru_cache(maxsize=4096)
def _cached_generic_json_schema(
    cls: type[Exception],
    detail: str | FStringDetail | DictDetail | None,
    status_code: int | None,
) -> HTTPExceptionSchema | None:
    return _build_generic_json_schema(cls, detail, status_code)


def _build_generic_json_schema(
    cls: type[Exception],
    detail: str | FStringDetail | DictDetail | None = None,
    status_code: int | None = None,
) -> HTTPExceptionSchema | None:
    name = f"{cls.__name__}ErrorSchema"

    if hasattr(cls, "detail") and cls.detail and detail is None:  # type: ignore
        detail = cls.detail  # type: ignore

    if hasattr(cls, "status_code") and cls.status_code and status_code is None:  # type: ignore
        status_code = cls.status_code  # type: ignore

    if status_code is None:
        return None

    class_headers = getattr(cls, "headers", None)
    headers = list(class_headers) if isinstance(class_headers, dict) else []

    if isinstance(detail, FStringDetail):
        literal = " ".join(part for part in detail.parts if part is not None)
        # templates differing only in punctuation share a name; a clash gets a suffix later
        name = f"{_INVALID_NAME_CHARS.sub('', try_to_camel_case(literal))}Schema"
        template = "".join("{...}" if p is None else p for p in detail.parts)
        pattern = "".join(
            ".*" if p is None else _REGEX_META_CHARS.sub(r"\\\1", p)
            for p in detail.parts
        )
        schema = create_model(name, detail=(str, Field(..., pattern=f"^{pattern}$")))
        return HTTPExceptionSchema(
            response_schema_json=schema.model_json_schema(),
            schema_name=name,
            status_code=status_code,
            schema_desc=template,
            headers=headers,
        )

    if isinstance(detail, DictDetail):
        keys = [
            _INVALID_NAME_CHARS.sub("", try_to_camel_case(k)) for k, _ in detail.items
        ]
        name = f"{cls.__name__}{''.join(k[:1].upper() + k[1:] for k in keys)}Schema"
        return HTTPExceptionSchema(
            response_schema_json={
                "properties": {
                    "detail": {**_dict_detail_json_schema(detail), "title": "Detail"}
                },
                "required": ["detail"],
                "title": name,
                "type": "object",
            },
            schema_name=name,
            status_code=status_code,
            schema_desc="No description provided",
            headers=headers,
        )

    if detail is not None:
        detail_type = Literal[detail]  # type: ignore

        # OpenAPI component keys must match ^[a-zA-Z0-9.\-_]+$
        camel = _INVALID_NAME_CHARS.sub("", try_to_camel_case(detail))
        if camel:
            name = f"{camel}Schema"
    else:
        detail_type = str

    schema = create_model(name, detail=(detail_type, ...))

    return HTTPExceptionSchema(
        response_schema_json=schema.model_json_schema(),
        schema_name=name,
        status_code=status_code,
        schema_desc=detail or "No description provided",  # type: ignore
        headers=headers,
    )
