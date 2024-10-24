## Advance

This is guideline for how to use the library in more advanced ways.

### Customization of the OpenAPI schema

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

If your intention is to have a custom response schema, then recommended way is to use [custom exception feature](index.md#customization-of-exception).

### Finding exceptions in other modules

By default, the library only looks at the FastAPI app module to search for exceptions.
This is to avoid parsing countless dependency modules that are not related to the FastAPI app.
But sometimes you may be using some other libraries that raises HTTPExceptions.
For example using a third library for JWT authentication.

In that case, you can simply pass the module name to the `parse_exceptions` function.

```python
from richapi import enrich_openapi
from fastapi import FastAPI

app = FastAPI()
# add your routers ....
app.openapi = enrich_openapi(app, ["your_module_name", "some-other-package"])
```
