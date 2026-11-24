"""Offer handoff to a signing tool. Slatehire never sends an offer to a candidate itself.

The default `package` adapter writes the approved offer as a file you open in Breezedoc (or any signing tool) and send from there.
Breezedoc publishes a small API (documents, send, from a template) but sources disagree on what it can do, so no live call is built: UNVERIFIED.
"""

from __future__ import annotations

import re
from pathlib import Path

from sendora_core.adapters import AdapterError


class PackageHandoff:
    name = "package"

    def __init__(self, settings):
        self.dir = Path(settings.export_dir)

    def hand_off(self, *, offer_id: int, title: str, candidate_code: str, body: str) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "offer"
        path = self.dir / f"offer-{offer_id}-{candidate_code.lower()}-{stem}.txt"
        path.write_text(body + "\n", encoding="utf-8")
        return {"ref": path.name, "detail": f"Saved as {path.name}. Open it in your signing tool and send it from there."}

    def healthcheck(self):
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            return True, f"Export folder {self.dir.name} is writable."
        except OSError:
            return False, "The export folder is not writable."


class SeedHandoff(PackageHandoff):
    name = "seed"

    def hand_off(self, *, offer_id: int, title: str, candidate_code: str, body: str) -> dict:
        return {"ref": f"seed-offer-{offer_id}", "detail": "Offline demo: kept in the app only."}


class BreezedocHandoff:
    name = "breezedoc"

    def __init__(self, settings):
        raise AdapterError("A live Breezedoc call is not built. Its API could not be confirmed (see docs/facts/breezedoc.md). Use the package adapter and send from Breezedoc.")
