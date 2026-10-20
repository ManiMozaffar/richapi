"""Compare richapi from a git ref (default: main) against the working tree.

Usage:
    uv run python benchmarks/compare.py [--ref main] [--size medium]

Checks out <ref> into a temporary git worktree, runs bench.py with each
version on the same generated project, and verifies both produce the
exact same OpenAPI schema.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = Path(__file__).resolve().parent / "bench.py"


def run(richapi_root: Path, size: str, out: Path, repeat: int) -> str:
    env = {**os.environ, "PYTHONPATH": str(richapi_root)}
    cmd = [sys.executable, str(BENCH), "--size", size, "--out", str(out)]
    cmd += ["--repeat", str(repeat)]
    return subprocess.run(
        cmd, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="main")
    parser.add_argument("--size", default="medium")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        worktree = tmp / "ref"
        subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "worktree",
                "add",
                "-q",
                "--detach",
                str(worktree),
                args.ref,
            ],
            check=True,
        )
        try:
            print(
                f"{args.ref:>10}: {run(worktree, args.size, tmp / 'ref.json', args.repeat)}"
            )
            print(
                f"{'current':>10}: {run(ROOT, args.size, tmp / 'cur.json', args.repeat)}"
            )
            same = (tmp / "ref.json").read_text() == (tmp / "cur.json").read_text()
            print("schemas identical" if same else "SCHEMAS DIFFER")
        finally:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(ROOT),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                ],
                check=True,
            )
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
