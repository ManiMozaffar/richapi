import importlib
import json
from pathlib import Path
from typing import Annotated, Optional, Union

import typer
from fastapi import FastAPI

from richapi.exc_parser.openapi import compile_openapi_from_fastapi

app = typer.Typer()


def dynamic_import(module_name: str, attribute: Optional[str] = None):
    """
    Dynamically import a module and optionally get an attribute from it.
    """
    try:
        module = importlib.import_module(module_name)
        if attribute:
            return getattr(module, attribute)
        return module
    except ModuleNotFoundError:
        raise typer.BadParameter(f"Module '{module_name}' not found.")
    except AttributeError:
        raise typer.BadParameter(
            f"Attribute '{attribute}' not found in module '{module_name}'."
        )


@app.command()
def compile(
    fastapi_path: Annotated[
        str,
        typer.Argument(help="The FastAPI application path."),
    ],
    target_path: Annotated[
        Union[Path, None],
        typer.Argument(help="The target path to save the OpenAPI schema."),
    ] = None,
    module_to_compile: Annotated[
        Optional[str],
        typer.Argument(help="The module to look for the FastAPI application."),
    ] = None,
):
    """
    Compile an OpenAPI schema from a FastAPI application, extending all possible FastAPI exceptions to the OpenAPI schema.
    Compile the module and attribute using the format {module_name}:{attribute}.
    """
    if ":" not in fastapi_path:
        raise typer.BadParameter(
            "Invalid format. Please use the format {module}.{module}:{app}."
        )

    if not target_path:
        target_path = Path.cwd() / "openapi.json"

    module_name, attribute = fastapi_path.split(":")

    if module_to_compile is None:
        module_to_compile = module_name.split(".")[0]

    app_object = dynamic_import(module_name, attribute)
    if not isinstance(app_object, FastAPI):
        raise typer.BadParameter(
            f"Expected FastAPI object, but got `{type(app_object).__name__}`."
        )
    typer.echo(
        f"Successfully accessed '{attribute}' in module '{module_name}', compiling OpenAPI..."
    )

    openapi_json = compile_openapi_from_fastapi(app_object, module_to_compile)

    with open(target_path, "w") as file:
        file.write(json.dumps(openapi_json, indent=2))

    typer.echo(f"OpenAPI schema saved to '{target_path}'")
    return


@app.command(name="test-compile")
def test():
    typer.echo("Hello, World!")


if __name__ == "__main__":
    app()
