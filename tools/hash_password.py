"""Make an argon2 hash for OWNER_PASSWORD_HASH. Run: python tools/hash_password.py   (the password is typed hidden and never shown)."""

from __future__ import annotations

import getpass

import _common  # noqa: F401
from sendora_core.auth import hash_password


def main() -> None:
    pw = getpass.getpass("New password (at least 8 characters): ")
    if pw != getpass.getpass("Again: "):
        raise SystemExit("The two passwords differ. Nothing was made.")
    print("Put this line in your environment file:")
    print("OWNER_PASSWORD_HASH='" + hash_password(pw) + "'")


if __name__ == "__main__":
    main()
