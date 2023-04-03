from .base import QueryMixin
from typing import Type


class Model:

    _query_mixin_instance = None

    @classmethod
    @property
    def objects(cls) -> QueryMixin:
        if cls._query_mixin_instance is None:
            cls._query_mixin_instance = QueryMixin(cls)
        return cls._query_mixin_instance