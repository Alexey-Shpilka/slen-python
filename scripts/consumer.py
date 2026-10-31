"""consumer.py <dist>: the help examples type-checked as a user's code, against the installed wheel.

The wheel goes into an empty environment beside the type checkers of the dev group, at their pins; every
examples/help/*/python.py is copied into an empty directory, so it imports the installed package and never src/;
each is checked with mypy --strict and all with pyright strict, and pyright --verifytypes holds the public surface
to full type completeness. Needs the package index. Exit 0, or the status of the first check that failed.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("mypy", "pyright", "fastapi", "django", "django-stubs")


def pins() -> list[str]:
    dev = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["dependency-groups"]["dev"]

    return [line for line in dev if re.split(r"[\[=<>]", line, maxsplit=1)[0] in TOOLS]


def run(command: list[str], where: Path) -> None:
    print("$", " ".join(command), flush=True)
    subprocess.run(command, cwd=where, check=True)


def main(argv: list[str]) -> int:
    dist = Path(argv[0] if argv else "dist").resolve()
    wheel = next(dist.glob("slen-*-py3-none-any.whl"))

    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        python = work / "venv" / "bin" / "python"
        run([sys.executable, "-m", "venv", str(work / "venv")], work)
        run([str(python), "-m", "pip", "install", "--quiet", f"{wheel}[otel]", *pins()], work)
        code = work / "examples"
        code.mkdir()

        for example in sorted((ROOT / "examples" / "help").glob("*/python.py")):
            shutil.copy(example, code / f"help_{example.parent.name.replace('-', '_')}.py")

        config = {"typeCheckingMode": "strict", "pythonVersion": "3.11", "include": ["examples"]}
        (work / "pyrightconfig.json").write_text(json.dumps(config), encoding="utf-8")

        try:
            for example in sorted(code.glob("*.py")):
                run([str(python), "-m", "mypy", "--strict", "--no-incremental", str(example)], work)

            run([str(work / "venv" / "bin" / "pyright"), "--pythonpath", str(python)], work)
            run(
                [
                    str(work / "venv" / "bin" / "pyright"),
                    "--pythonpath",
                    str(python),
                    "--verifytypes",
                    "slen",
                    "--ignoreexternal",
                ],
                work,
            )
        except subprocess.CalledProcessError as failed:
            return failed.returncode or 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
