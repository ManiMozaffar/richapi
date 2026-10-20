"""Benchmark richapi on a generated project.

Usage:
    uv run python benchmarks/bench.py [--size small|medium|large] [--out schema.json]

Runs in a fresh process each time so no state leaks between runs.
"""

import argparse
import importlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from generate_project import generate  # noqa: E402

SIZES: dict[str, dict[str, Any]] = {
    "small": dict(n_services=5, n_funcs=20, n_routers=4, n_endpoints=5),
    "medium": dict(n_services=30, n_funcs=40, n_routers=20, n_endpoints=15),
    "large": dict(n_services=80, n_funcs=80, n_routers=60, n_endpoints=20),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", choices=SIZES, default="medium")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        pkg = generate(Path(tmp), **SIZES[args.size])
        sys.path.insert(0, tmp)
        app = importlib.import_module(f"{pkg}.main").app

        from richapi.exc_parser.openapi import compile_openapi_from_fastapi

        n_routes = len(app.routes)
        timings = []
        schema = None
        for _ in range(args.repeat):
            start = time.perf_counter()
            schema = compile_openapi_from_fastapi(app, pkg)
            timings.append(time.perf_counter() - start)

    print(
        f"size={args.size} routes={n_routes} "
        f"best={min(timings):.3f}s runs={[round(t, 3) for t in timings]}"
    )
    if args.out:
        args.out.write_text(json.dumps(schema, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
