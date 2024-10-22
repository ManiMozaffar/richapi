# Implementation detail

Library is made of few components working together to generate the OpenAPI schema.

## Exception Finder

- **Input**: A function
- **Output**: List of exception type with their `raise` abstract syntax tree nodes

1. Check if this function was ever analyzed before, if yes, then skip.
2. Get source code of the callable object.
3. Parse the source code to AST.
4. Start visiting every node in the callable.
5. Track assigmnets to a variable.
6. On visiting a node ...
   1. If the node is a `raise` statement, then extract the exception type and return as output.
   2. If a node is a `call` statement, then recursively visit the callable that is being called.
   3. If a node is an `assign` statement, then track the variable name and the assigned value.
   4. If a node is an `attribute` statement, then track the attribute name and the parent object. Might have to recursively visit the parent object.

Note that the only way to extract the exception type is to use the tracked assigmnets with `eval` function so that the type is returned.
That's why it's best to run the library on CLI rather than on the fly. To understand this better look at below code;

```python

def foo():
    err = Exception
    raise err
```

The only way that you can understand err is Exception is to keep tracking the assignments and then use `eval` to get the type. Running `eval("err")` will get you the type of the error which is a requirement to function properly.

## FastAPI Excption Parser

- **Input**: An excpetion with its `raise` AST node
- **Output**: Json schema

1. Check if the exception type already has a schema defined by itself.
   - If yes, then simply construct the Json schema from that.
   - If not, continue to the next step.
2. Analyze and extract arg and kwargs from the `raise` AST node.
3. Try to construct the exception schema from the arguments.
4. Try to dynamically generate the schema using Pydantic.
5. Return the schema if successfully generated, otherwise return None.

## OpenAPI Generator

- **Input**: FastAPI Module, Previous OpenAPI schema
- **Output**: OpenAPI schema

1. Iterating over all fastapi routers to analyze each at a time.
2. Each router has few callable dependency. All callable dependencies are analyzed using `Exception Finder`.
3. Result of the `Exception Finder` is passed to the `FastAPI Excption Parser` to get the Json schema.
4. Using the Json schema, the OpenAPI schema is extended with new responses for that router.
5. The result is cached so that the same router is not analyzed again.
