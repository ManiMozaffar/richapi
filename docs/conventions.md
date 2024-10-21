## Conventions

This is guideline for how to raise exceptions so that the library can generate the OpenAPI schema from them.

Since the library is a mini compiler using Abstract Syntax Tree and functions global to extract exceptions and their responses, there are some conventions that you need to follow to get the best out of it.

Keep in mind that if you don't follow these conventions, there would be alot false positive and false negative cases, and the library may not be able to extract the exceptions and their responses correctly.

### Inherit from `richapi.BaseHTTPException`

Exceptions are better to be very concrete, without having any dynamic data in them.
So that using `raise Class` is enough to raise them.

Exceptions ideally should inherit from `richapi.BaseHTTPException`. Check the ideal case below:

```python
from richapi import BaseHTTPException

class UserNotFound(BaseHTTPException):
    status_code = 404
    details = "User not found"
```

And then, only writing `raise UserNotFound` is enough to raise the exception. This is most ideal case.

### Avoiding dynamic data in the constructor of the exceptions

Exceptions should not have any dynamic data in them.
For example the code below is NOT ideal:

```python

user_id = 1 # imaginary dynamic data
error_message = f"User {user_id} is not allowed to perform this action"
raise FooException(detail=error_message)
```

Since the library is using static analyzers to extract the exceptions, it is not possible to extract the dynamic data from the exceptions. (or rather very hard to do so)

### Avoiding usage of magic methods

Magic methods are implicit, therefore extracting them from the abstract syntax tree is exteremly hard and equal to rewriting the Python interpreter.

One example that you should not do in your code:

```python
class Foo:
    def __init__(self, bar):
        self.bar = bar

    def __eq__(self, other):
        raise HTTPException(status_code=400, detail="This is not allowed")
```

### Keep it simple

The ideal way to raise exceptions is to keep it simple from syntax point of view;

This is very ideal and can be easily parsed and compiled.

```python
raise HTTPException(status_code=400, detail="This is not allowed")
```

But the below example MAY not be parsed correctly:

```python
exc = lambda: HTTPException
raise exc()(status_code=400, detail="This is not allowed")
```

Keep it simple, keep the exception type next to raise keyword; without any dynamic data in the constructor. This help the library to extract the exceptions and their responses and guarantee that they are correctly compiled into the OpenAPI schema.
