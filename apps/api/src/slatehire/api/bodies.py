"""Reading a request body with a ceiling. The shared base already refuses a body over MAX_BODY_BYTES (25 MB); these limits are the ones this app needs: a signed
application is a few kilobytes and a resume file is at most UPLOAD_MAX_BYTES."""

from __future__ import annotations

from fastapi import HTTPException, Request


async def read_limited(request: Request, limit: int, what: str = "The request") -> bytes:
    """The body, read with a ceiling. A declared length over the limit is refused before a byte is read, and a body that lies about its
    length (or has none, chunked) is counted while it arrives and cut off at the limit."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        raise HTTPException(413, f"{what} is larger than the limit.")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, f"{what} is larger than the limit.")
        chunks.append(chunk)
    return b"".join(chunks)
