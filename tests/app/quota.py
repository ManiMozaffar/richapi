from pydantic.dataclasses import dataclass

from richapi.exc_parser.protocol import RichHTTPException


@dataclass
class Quota(RichHTTPException):
    """Daily quota reached"""

    resets_in: int
    status_code = 429
