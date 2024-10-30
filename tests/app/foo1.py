from richapi.exc_parser.protocol import BaseHTTPException


class HTTP500Error(BaseHTTPException):
    status_code = 500
    detail = "Internal Server Error"


def raise_exc():
    raise HTTP500Error
