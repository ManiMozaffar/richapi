## Advance

This is guideline for how to use the library in more advanced ways.

### Customization of the OpenAPI schema

Sometimes, your exceptions is more than 'details'.
In that case, you can very explicitly define the exception JSON schema inside the exception class. You may even use Pydantic to define the schema dynamically so you don't need to write the schema manually.

All you need to do, is to return type HTTPExceptionSchema correctly on the method `get_json_schema` of your exception class which you inherited from `BaseHTTPException`.

Imagine you are writing an exception that is returning a user balance and a time to retry again a failed bank transaction, you can define the schema like this:

```python
from richapi import  BaseHTTPException
from richapi.exc_parser import HTTPExceptionSchema
from pydantic import create_model

class YourException(BaseHTTPException):
    user_balance: int
    retry_again_in: int
    status_code: int = 400

    @classmethod
    def get_json_schema(cls) -> HTTPExceptionSchema:
        schema = create_model(name, user_balance=(int, ...), retry_again_in=(int, ...))
        return HTTPExceptionSchema(
            schema_name="YourException",
            schema_desc="This is a custom exception",
            status_code=cls.status_code,
            response_schema_json=schema.model_json_schema(),
        )

```

Remember that the responsbility of raising and returning the correct data on FastAPI is not library responsibility, but the responsibility of the developer. The library is only responsible for generating the OpenAPI schema by looking at the functions and classes that are raising exceptions.
