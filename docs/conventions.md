# Conventions

This is guideline for how to raise exceptions so that the library can generate the OpenAPI schema from them.

Since the library is a mini compiler using Abstract Syntax Tree and functions global to extract exceptions and their responses, there are some conventions that you need to follow to get the best out of it.

Keep in mind that if you don't follow these conventions, there would be alot false positive and false negative cases, and the library may not be able to extract the exceptions and their responses correctly.

## Inherit from `richapi.BaseHTTPException` or `richapi.RichHTTPException`

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

!!! info "Expected Behavior"

    Library **MIGHT skip** adding the exception to the OpenAPI schema if it could not gather necessary and missing informations from the abstract syntax tree.

## Avoiding dynamic data in the constructor of the exceptions and stringifying errors

Exceptions should not have any dynamic data in them.
For example the code below is NOT ideal:

```python

user_id = 1 # imaginary dynamic data
error_message = f"User {user_id} is not allowed to perform this action"
raise FooException(detail=error_message)
```

This is not even a good practice to begin with, because ideally your RestAPI should not be aware of what text shown to the user. The error message should be handled by the client, not the server. There is a better way you can do to pass information to client about the error.
Read the [advance usage](advance.md) section for more information.

Since the library is using static analyzers to extract the exceptions, it is not possible to extract the dynamic data from the exceptions. (or rather very hard to do so)

!!! info "Expected Behavior"

    Library **WILL add** the exception to the OpenAPI schema, but the detail of response won't be precisely shown and instead you will see `str` as the response type. However, if you follow this convention, library exactly show the string that you have written in the `detail` attribute of the exception as a **literal string type**.

## Avoiding usage of magic methods

Magic methods are implicit, therefore extracting them from the abstract syntax tree is exteremly hard and equal to rewriting the Python interpreter.

One example that you should not do in your code:

```python
class Foo:
    def __init__(self, bar):
        self.bar = bar

    def __eq__(self, other):
        raise HTTPException(status_code=400, detail="This is not allowed")
```

!!! info "Expected Behavior"

    Library **WILL skip** adding the exception to the OpenAPI schema.

## Keep it simple

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

!!! info "Expected Behavior"

    Library **MIGHT skip** adding the exception to the OpenAPI schema depending on how complicated the exception raising is.

## Always Provide Type Annotations For Class/Instance Attributes And Function Arguments

To enable accurate type resolution during static analysis, always provide type annotations for your variables, function parameters, and return types. Without type annotations, it's nearly impossible for the library to infer types correctly, which may lead to false positives or negatives. That stands for class attributes and function arguments.

Example:

```Python hl_lines="6 12"
class Foo:
    def foo(self) -> None:
        raise HTTPException(status_code=400, detail="This is not allowed")

class Baz:
    foo: Foo # this is very important to have type annotations for class/instance attributes

    def __init__(self, foo: Foo):
        self.foo = foo

    def foo(self) -> None:
        # if you don't type annotate, RichAPI doesn't have any idea about the type of self.fo
        self.foo.foo()
```

!!! info "Expected Behavior"

    Library **WILL skip** adding exceptions to the OpenAPI schema if it cannot resolve types due to missing annotations.
