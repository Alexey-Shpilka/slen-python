"""check_dist.py <dist>: what the wheel and the sdist of the package carry, and nothing else.

The wheel is slen/** and its metadata; the sdist is src/, pyproject.toml, README.md, LICENSE and CHANGELOG.md.
Exit 0 — both are what they should be; 1 — what differs, one line each; 2 — no single wheel and sdist in <dist>.
"""

import email.message
import email.parser
import re
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
NAME, VERSION = PROJECT["name"], PROJECT["version"]
# What a build or a machine leaves behind, and what is the repository's, not the package's.
NEVER = re.compile(r"__pycache__|\.pyc$|\.egg-info|(^|/)tests?/|(^|/)\.|/examples/|/scripts/|/contract/|uv\.lock")
WHEEL_NEEDS = {"slen/__init__.py", "slen/py.typed", "slen/testing.py", "slen/otel.py", "slen/_version.py"}
# PKG-INFO and .gitignore are hatchling's own: the metadata, and what a wheel built from the sdist leaves out.
SDIST_FILES = {"pyproject.toml", "README.md", "LICENSE", "CHANGELOG.md", "PKG-INFO", ".gitignore"}


def wheel_problems(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        info = f"{NAME}-{VERSION}.dist-info/"
        metadata = email.parser.Parser().parsestr(wheel.read(f"{info}METADATA").decode())

    found = [f"wheel: {name} is not the package's" for name in names if not name.startswith(("slen/", info))]
    found += [f"wheel: {name} is not to be shipped" for name in names if NEVER.search(name)]
    found += [f"wheel: {name} is missing" for name in sorted(WHEEL_NEEDS - set(names))]
    found += [] if f"{info}licenses/LICENSE" in names else ["wheel: the LICENSE is missing"]

    return found + metadata_problems(metadata)


def metadata_problems(metadata: email.message.Message) -> list[str]:
    wanted = {
        "Name": NAME,
        "Version": VERSION,
        "Requires-Python": PROJECT["requires-python"],
        "License-Expression": PROJECT["license"],
    }
    found = [f"metadata: {key} is {metadata.get(key)!r}" for key, value in wanted.items() if metadata.get(key) != value]
    requires = metadata.get_all("Requires-Dist") or []
    found += [] if "httpx<1,>=0.27" in requires else [f"metadata: Requires-Dist {requires}"]
    found += [] if "otel" in (metadata.get_all("Provides-Extra") or []) else ["metadata: no extra otel"]

    return found + [
        f"metadata: a requirement outside the extra: {line}"
        for line in requires
        if "httpx" not in line and "extra ==" not in line
    ]


def sdist_problems(path: Path) -> list[str]:
    prefix = f"{NAME}-{VERSION}/"

    with tarfile.open(path) as sdist:
        names = [member.name for member in sdist.getmembers() if member.isfile()]

    inside = [name.removeprefix(prefix) for name in names]
    found = [f"sdist: {name} is outside {prefix}" for name in names if not name.startswith(prefix)]
    found += [
        f"sdist: {name} is not to be shipped"
        for name in inside
        if name not in SDIST_FILES and not name.startswith("src/slen/")
    ]
    found += [f"sdist: {name} is not to be shipped" for name in inside if NEVER.search(name) and name != ".gitignore"]
    found += [f"sdist: {name} is missing" for name in sorted(SDIST_FILES - set(inside))]

    return found + [f"sdist: src/{name} is missing" for name in sorted(WHEEL_NEEDS) if f"src/{name}" not in inside]


def main(argv: list[str]) -> int:
    dist = Path(argv[0]) if argv else Path("dist")
    wheels = sorted(dist.glob(f"{NAME}-{VERSION}-py3-none-any.whl"))
    sdists = sorted(dist.glob(f"{NAME}-{VERSION}.tar.gz"))

    # uv writes a .gitignore beside what it builds.
    built = [path for path in dist.iterdir() if not path.name.startswith(".")]

    if len(wheels) != 1 or len(sdists) != 1 or len(built) != 2:
        print(
            f"check_dist: {dist} holds {sorted(p.name for p in built)}, not one wheel and one sdist",
            file=sys.stderr,
        )
        return 2

    found = wheel_problems(wheels[0]) + sdist_problems(sdists[0])

    for line in found:
        print(line)

    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
