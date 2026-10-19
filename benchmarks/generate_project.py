"""Generate a synthetic, large FastAPI project to benchmark richapi's analysis.

The layout mimics a real service: exceptions, many service modules full of
helpers/classes calling each other, shared dependencies and routers.
"""

import random
import textwrap
from pathlib import Path


def _w(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip())


def generate(
    root: Path,
    pkg: str = "bench_app",
    n_services: int = 30,
    n_funcs: int = 40,
    n_routers: int = 20,
    n_endpoints: int = 15,
    seed: int = 0,
) -> str:
    rnd = random.Random(seed)
    base = root / pkg
    _w(base / "__init__.py", "")
    _w(base / "services" / "__init__.py", "")
    _w(base / "routes" / "__init__.py", "")

    exc_lines = [
        "from fastapi import HTTPException",
        "from pydantic.dataclasses import dataclass",
        "from richapi import BaseHTTPException, RichHTTPException",
        "",
    ]
    for i in range(40):
        exc_lines += [
            "@dataclass",
            f"class Rich{i}(RichHTTPException):",
            f'    """Rich error {i}"""',
            f"    status_code = {400 + i % 30}",
            f"    field_{i}: int = 0",
            "",
            f"class Plain{i}(HTTPException): ...",
            "",
            f"class Base{i}(BaseHTTPException):",
            f"    status_code = {400 + (i * 7) % 30}",
            f'    detail = "base error {i}"',
            "",
        ]
    _w(base / "exceptions.py", "\n".join(exc_lines) + "\n")

    for s in range(n_services):
        lines = [
            "from fastapi import HTTPException, status",
            f"from {pkg} import exceptions as E",
            f"from {pkg}.exceptions import Rich{s % 40}, Plain{s % 40}",
        ]
        if s > 0:
            lines.append(f"from {pkg}.services import svc_{s - 1} as prev")
        lines.append("")
        for f in range(n_funcs):
            kind = rnd.randrange(5)
            lines.append(f"def helper_{f}(x: int = 0):")
            if kind == 0:
                lines.append(f"    raise Rich{s % 40}()")
            elif kind == 1:
                lines.append(
                    f'    raise Plain{s % 40}(status_code={400 + f % 30}, detail="svc {s} helper {f}")'
                )
            elif kind == 2:
                lines.append(f"    exc = E.Base{(s + f) % 40}()")
                lines.append("    raise exc")
            elif kind == 3 and f > 0:
                lines.append(f"    helper_{rnd.randrange(f)}(x)")
                lines.append(
                    '    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="missing")'
                )
            else:
                lines.append("    total = 0")
                lines.append("    for i in range(x):")
                lines.append("        total += i")
                lines.append("    return total")
            if s > 0 and rnd.random() < 0.3:
                lines.append(f"    prev.helper_{rnd.randrange(n_funcs)}(x)")
            lines.append("")
        # filler to make modules realistically large
        for f in range(n_funcs):
            lines += [
                f"def _private_{f}(a, b, c=None):",
                '    """Some unrelated code that richapi has to parse anyway."""',
                "    data = {'a': a, 'b': b, 'c': c}",
                "    return [v for v in data.values() if v is not None]",
                "",
            ]
        lines += [
            f"class Repo{s}:",
            "    def get(self, x):",
            f"        helper_{rnd.randrange(n_funcs)}(x)",
            "        return x",
            "",
            f"class Service{s}:",
            f"    repo: Repo{s}",
            "",
            "    def __init__(self):",
            f"        self.repo = Repo{s}()",
            f"        helper_{rnd.randrange(n_funcs)}()",
            "",
        ]
        for m in range(10):
            lines += [
                f"    def method_{m}(self, x: int):",
                f"        helper_{rnd.randrange(n_funcs)}(x)",
                "        self.repo.get(x)",
                "        return self",
                "",
            ]
        _w(base / "services" / f"svc_{s}.py", "\n".join(lines) + "\n")

    _w(
        base / "deps.py",
        f"""
        import fastapi
        import fastapi.security
        from {pkg}.services import svc_0

        bearer = fastapi.security.HTTPBearer()

        def get_token(token=fastapi.Depends(bearer)):
            svc_0.helper_0()
            return token

        def get_user(token: str = fastapi.Depends(get_token)):
            if not token:
                raise fastapi.HTTPException(status_code=401, detail="unauthorized")
            return token
        """,
    )

    for r in range(n_routers):
        lines = [
            "from fastapi import APIRouter, Depends, HTTPException",
            f"from {pkg}.deps import get_user",
        ]
        used = sorted({rnd.randrange(n_services) for _ in range(4)})
        for s in used:
            lines.append(f"from {pkg}.services import svc_{s}")
            lines.append(f"from {pkg}.services.svc_{s} import Service{s}")
        lines += ["", "router = APIRouter()", ""]
        for e in range(n_endpoints):
            s = rnd.choice(used)
            lines += [
                f'@router.get("/r{r}/e{e}")',
                f"async def endpoint_{r}_{e}(x: int, user: str = Depends(get_user)):",
                f"    svc = Service{s}()",
                f"    svc.method_{rnd.randrange(10)}(x).method_{rnd.randrange(10)}(x)",
                f"    svc_{s}.helper_{rnd.randrange(n_funcs)}(x)",
                "    if x < 0:",
                f'        raise HTTPException(status_code={400 + e % 20}, detail="route {r} {e}")',
                "    return {'ok': True}",
                "",
            ]
        _w(base / "routes" / f"r_{r}.py", "\n".join(lines) + "\n")

    lines = ["from fastapi import FastAPI"]
    lines += [f"from {pkg}.routes import r_{r}" for r in range(n_routers)]
    lines += ["", "app = FastAPI()"]
    lines += [f"app.include_router(r_{r}.router)" for r in range(n_routers)]
    _w(base / "main.py", "\n".join(lines) + "\n")
    return pkg
