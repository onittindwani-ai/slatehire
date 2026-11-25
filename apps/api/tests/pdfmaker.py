"""Build small test PDFs with pypdf: a blank page, one font, and a hand written content stream."""

from __future__ import annotations

import io

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def make_pdf(content: str, width: int = 612, height: int = 792) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width, height)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(content.encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def line(text: str, y: int, *, size: float = 11, extra: str = "") -> str:
    return f"BT {extra} /F1 {size} Tf 72 {y} Td ({text}) Tj ET\n"
