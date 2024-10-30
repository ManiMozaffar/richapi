from typing import Annotated

from richapi.exc_parser.compiler import _retrieve_from_annotations


def foo(value: Annotated[int, Annotated[str, str]]): ...


def test_get_from_annotated():
    result = _retrieve_from_annotations(foo, "value")
    print(type(result))
    assert result is int
