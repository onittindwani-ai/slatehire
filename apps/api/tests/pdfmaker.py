"""Build small test PDFs with pypdf: a blank page, one font, and a hand written content stream."""

from __future__ import annotations

import io

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, TextStringObject


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


def _stream(data: bytes, entries: dict) -> DecodedStreamObject:
    obj = DecodedStreamObject()
    obj.set_data(data)
    for key, value in entries.items():
        obj[NameObject(key)] = value
    return obj


def build_pdf(content: str, *, forms: dict[str, str] | None = None, images: dict[str, int] | None = None, cropbox: tuple[float, float, float, float] | None = None,
              layers: dict[str, bool] | None = None, extra_pages: list[str] | None = None, form_matrix: list[float] | None = None, form_layers: dict[str, str] | None = None) -> bytes:
    """A PDF for the hidden text tests, with the things a plain page cannot have.

    forms:  name -> content of a Form XObject, drawn with `/name Do` (it has its own copy of the font).
    images: name -> grey level 0..255 of a one pixel image, drawn with `/name Do` (it fills the unit square of the current matrix).
    cropbox: (left, bottom, right, top) of the page.
    layers: name -> True when the layer is on and False when it is off by default; use it in the content as `/OC /name BDC ... EMC`.
    extra_pages: more pages, each a content string that can draw the same forms and images.
    form_layers: form name -> layer name, which puts that layer's /OC on the form.
    """
    from pypdf.generic import ArrayObject, FloatObject, NumberObject

    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")}))
    xobjects = DictionaryObject()
    ocgs: dict[str, object] = {}
    props = DictionaryObject()
    for name in layers or {}:
        ocgs[name] = writer._add_object(DictionaryObject({NameObject("/Type"): NameObject("/OCG"), NameObject("/Name"): TextStringObject(name)}))
        props[NameObject(f"/{name}")] = ocgs[name]
    for name, body in (forms or {}).items():
        res = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        entries = {"/Type": NameObject("/XObject"), "/Subtype": NameObject("/Form"), "/BBox": ArrayObject([NumberObject(0), NumberObject(0), NumberObject(612), NumberObject(792)]), "/Resources": res}
        if form_matrix:
            entries["/Matrix"] = ArrayObject([FloatObject(v) for v in form_matrix])
        if form_layers and name in form_layers:
            entries["/OC"] = ocgs[form_layers[name]]
        xobjects[NameObject(f"/{name}")] = writer._add_object(_stream(body.encode("latin-1"), entries))
    for name, grey in (images or {}).items():
        entries = {"/Type": NameObject("/XObject"), "/Subtype": NameObject("/Image"), "/Width": NumberObject(1), "/Height": NumberObject(1), "/ColorSpace": NameObject("/DeviceGray"), "/BitsPerComponent": NumberObject(8)}
        xobjects[NameObject(f"/{name}")] = writer._add_object(_stream(bytes([grey]), entries))
    for body in [content, *(extra_pages or [])]:
        page = writer.add_blank_page(612, 792)
        resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        if xobjects:
            resources[NameObject("/XObject")] = xobjects
        if layers:
            resources[NameObject("/Properties")] = props
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = writer._add_object(_stream(body.encode("latin-1"), {}))
        if cropbox:
            page[NameObject("/CropBox")] = ArrayObject([FloatObject(v) for v in cropbox])
    if layers:
        off = [ocgs[n] for n, on in layers.items() if not on]
        default = DictionaryObject({NameObject("/OFF"): ArrayObject(off), NameObject("/BaseState"): NameObject("/ON")})
        writer._root_object[NameObject("/OCProperties")] = DictionaryObject({NameObject("/OCGs"): ArrayObject(list(ocgs.values())), NameObject("/D"): default})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
