"""A route that gets its database session with a bare `Depends(db)` saves AFTER the answer has gone out (FastAPI 0.165), so a failed save still shows success."""

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "src" / "slatehire" / "api"


def test_every_route_asks_for_its_session_with_the_function_scope():
    bare = [f.name for f in API.glob("*.py") if re.search(r"Depends\(db\)", f.read_text())]
    assert bare == []
