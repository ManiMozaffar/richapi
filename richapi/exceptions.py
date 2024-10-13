from typing import Callable


class BaseRichAPIException(Exception):
    """Base class for all exceptions in richapi module"""


class FetchSourceException(BaseRichAPIException):
    """Exception raised when fetching source code"""

    def __init__(self, func: Callable) -> None:
        message = f"Failed to fetch source code for function {func.__name__}"
        super().__init__(message)
