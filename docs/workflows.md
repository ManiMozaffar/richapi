## Workflows

`app.openapi = enrich_openapi(app)` runs richapi on the server, the first time someone opens the docs. That works, but you don't have to compute the schema live. This page shows two other ways to use richapi, which you can also combine:

1. Pre-compute `openapi.json` and commit it, so every pull request shows how it changes your API.
2. Document your responses yourself, and let richapi check that you didn't miss one.

### Pre-compute the OpenAPI schema

Compile the schema once, outside the server:

```bash
richapi compile myapp.main:app openapi.json
```

The first argument is `{module}:{attribute}` of your FastAPI app. The optional third argument is the module richapi searches for exceptions; it defaults to the top-level package, `myapp` here.

Then serve the file instead of analysing your code on startup:

```python
import json

from fastapi import FastAPI
from richapi import load_openapi

app = FastAPI()

with open("openapi.json") as file:
    app.openapi = load_openapi(app, json.load(file))
```

#### Your API contract as part of code review

Once `openapi.json` is committed, it becomes a reviewed artifact like any other file. A pull request that adds an error, removes a field or changes a status code shows it in the diff of `openapi.json`, next to the code that caused it. Reviewers see the change to the API, not just the change to the code.

Keep the file honest in CI by regenerating it and failing when it differs from what's committed:

```bash
richapi compile myapp.main:app openapi.json
git diff --exit-code openapi.json
```

You can go one step further and fail on **breaking** changes only, by comparing the schema on your main branch with the one in the pull request. Any OpenAPI diff tool works; for example with [oasdiff](https://github.com/oasdiff/oasdiff):

```bash
git show origin/main:openapi.json > base.json
richapi compile myapp.main:app openapi.json
oasdiff breaking base.json openapi.json --fail-on ERR
```

Because richapi documents your errors too, removing a response a client relies on, or changing an error's body, shows up in that check like any other breaking change.

### Document it yourself, let richapi check it

Some teams prefer to write every response by hand, with `responses=` on each route. That's explicit, but it's easy to forget one when the code changes. richapi can tell you what you missed, so you get both: responses you wrote yourself, and the certainty that none is missing.

Write your routes as usual:

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()


@app.get("/items/{item_id}", responses={404: {"description": "Item not found"}})
def read_item(item_id: int):
    if item_id < 0:
        raise HTTPException(400, "Invalid id")
    if item_id != 42:
        raise HTTPException(404, "Item not found")
    return {"item_id": item_id}
```

Then add a test that compares what you documented with what richapi finds:

```python
from richapi.exc_parser.openapi import compile_openapi_from_fastapi, default_openapi_getter

from myapp.main import app


def test_every_response_is_documented():
    documented = default_openapi_getter(app)  # only what you wrote by hand
    found = compile_openapi_from_fastapi(app, "myapp")  # plus what richapi found

    missing = {}
    for path, operations in found["paths"].items():
        for method, operation in operations.items():
            written = documented["paths"][path][method]["responses"]
            if undocumented := set(operation["responses"]) - set(written):
                missing[f"{method.upper()} {path}"] = sorted(undocumented)

    assert not missing, f"Undocumented responses: {missing}"
```

Here the test fails with `{'GET /items/{item_id}': ['400']}`, because the 400 isn't in `responses=`. You keep serving the schema you wrote; richapi only runs in your tests.

#### Checking single functions

To check one endpoint, or functions outside your routes such as a service layer, use `get_function_exceptions`. It returns one entry per raise statement, including the ones in functions it calls:

```python
from richapi import exception_analysis, get_function_exceptions

from myapp.main import app, read_item
from myapp.services import create_order, cancel_order

with exception_analysis():
    for exc in get_function_exceptions(read_item, "myapp", app=app):
        print(exc.status_code, exc.exception.__name__, exc.raised_in.__name__)

    for service in [create_order, cancel_order]:
        print(service.__name__, get_function_exceptions(service, "myapp"))
```

Each entry is a `FunctionException`:

| Field | What it is |
|---|---|
| `exception` | The raised exception class. Not only HTTP exceptions: a `ValueError` is listed too. |
| `status_code` | The response status code, or `None` for non-HTTP exceptions and statuses richapi can't resolve. |
| `schema` | The `HTTPExceptionSchema` richapi would document for it, or `None`. |
| `raised_in` | The function that holds the `raise` statement. |

With `app=`, the function must be one of the app's endpoints, and the exceptions of its route's dependencies, such as a security scheme's 401, are included too.

!!! info "Why `exception_analysis()`"

    richapi caches parsed source files and analysis results, which makes analysing many functions fast. `exception_analysis()` keeps those caches for the whole block and frees them when it exits, even if an error is raised. Without it, every `get_function_exceptions` call cleans up after itself, which is correct but slower when you call it many times. Compiling the schema, with `enrich_openapi` or the CLI, does the same thing internally.
