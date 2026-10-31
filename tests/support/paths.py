from pathlib import Path
from typing import Final

# Where the suite and the scripts find the package: one line each when they move.
ROOT: Final = Path(__file__).resolve().parents[2]
SRC: Final = ROOT / "src" / "slen"
CONTRACT: Final = ROOT / "contract"
EXAMPLES: Final = ROOT / "examples" / "help"
SCRIPTS: Final = ROOT / "scripts"
PUBLIC_MODULES: Final = (SRC / "__init__.py", SRC / "testing.py", SRC / "otel.py")
