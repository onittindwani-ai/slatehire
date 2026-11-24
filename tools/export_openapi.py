"""Write docs/openapi.json from the real app. Run: python tools/export_openapi.py"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from slatehire.api.app import create_app  # noqa: E402
from slatehire.config import Settings  # noqa: E402


def main() -> dict:
    with tempfile.TemporaryDirectory() as d:
        app = create_app(Settings(_env_file=None, database_url=f"sqlite:///{d}/x.sqlite3", export_dir=d))
        spec = app.openapi()
    (ROOT / "docs" / "openapi.json").write_text(json.dumps(spec, indent=1) + "\n")
    ops = sum(len(v) for v in spec["paths"].values())
    print(f"{len(spec['paths'])} paths, {ops} operations")
    return spec


if __name__ == "__main__":
    main()
