"""Which text on a PDF page a person looking at the page could not see.

A resume PDF can carry words nobody can read on the page (white on white, a tiny size, outside the page, in a layer that is switched off) so that a scorer reads what a person does
not. This module follows the drawing instructions of a page the way a viewer would, as far as that matters for one question: when this text was drawn, could a person read it?
It follows, per piece of text: the text render mode (3 draws nothing), the fill and stroke colour, the transparency set with `gs`, the size after every matrix, the horizontal
scale (`Tz`) and the rise (`Ts`), the clip and the crop box, optional content layers (`BDC /OC`, and `/OC` on a form) that are off by default, and what was painted behind the text.

What was painted behind the text is the colour of the last filled shape (a rectangle, or any path that fills most of its box) that was drawn BEFORE the text and holds the whole of it; a page
with nothing there is white. Text whose colour is too close to that is hidden (a white line on a dark header band is a design and is read; a white line anywhere else is not). A picture is
never counted as a backdrop, because the reader cannot see its colours, so white text over a picture is reported as hidden text and the kept original is there for a person to look at.

It is a heuristic and it says so: text covered by a shape drawn afterwards, a colour in a space it cannot convert (Separation, DeviceN, Lab, a pattern) and text a viewer would draw
differently from the sizes it estimates are not found. The width of a piece of text is estimated from the number of characters, not measured from the font.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

MIN_VISIBLE_POINTS = 2.0  # text drawn smaller than this (in points) cannot be read by a person
MIN_CONTRAST = 0.15  # text whose lightness is within this of what is behind it cannot be read (white, or 0.85 and up, on white)
MIN_HSCALE = 0.1  # a horizontal scale (Tz) under 10 percent squeezes the words to nothing
MIN_ALPHA = 0.1  # a fill drawn with this much opacity or less is not there
BACKDROP_ALPHA = 0.5  # a shape drawn with less opacity than this does not change what is behind the text
BIG_IMAGE_SHARE = 0.5  # a picture that covers this share of the page is the page (a scan)
GLYPH_EM = 0.5  # the width of a character in ems when only the number of characters is known
ASCENT_EM = 0.7
EDGE = 5.0  # points of slack around the page and the clip
MAX_BOXES = 150
PAGE_SECONDS = 3.0  # a page that takes longer than this to follow (a crafted one) stops being followed: its remaining text is reported as not read, and the original is kept
MAX_STACK = 64

Matrix = tuple[float, float, float, float, float, float]
Box = tuple[float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
FILL_MODES, STROKE_MODES = frozenset({0, 2, 4, 6}), frozenset({1, 2, 5, 6})
NO_PAINT_MODES = frozenset({3, 7})
FILL_OPS = frozenset({"f", "F", "f*", "B", "B*", "b", "b*"})
PAINT_OPS = FILL_OPS | {"S", "s", "n"}


def mul(a: Matrix, b: Matrix) -> Matrix:
    """Apply a, then b."""
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3], a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def det(m: Matrix) -> float:
    return m[0] * m[3] - m[1] * m[2]


def bbox(points: list[tuple[float, float]]) -> Box:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def intersect(a: Box, b: Box) -> Box:
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inside(b: Box, p: tuple[float, float], slack: float) -> bool:
    return b[0] - slack <= p[0] <= b[2] + slack and b[1] - slack <= p[1] <= b[3] + slack


def polygon_area(points: list[tuple[float, float]]) -> float:
    return abs(sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points)))) / 2 if len(points) >= 3 else 0.0


def numbers(args: list) -> list[float] | None:
    try:
        return [float(a) for a in args]
    except (TypeError, ValueError):
        return None


def resolve(value):
    try:
        return value.get_object() if hasattr(value, "get_object") else value
    except Exception:  # noqa: BLE001 - a broken reference reads as nothing
        return None


def entry(d, key: str):
    """d[key] as an object, or None. A dictionary's `get` returns the reference, not the object."""
    try:
        return resolve(d.get(key)) if d is not None and hasattr(d, "get") else None
    except Exception:  # noqa: BLE001
        return None


def lightness(space: str | None, comps: list[float]) -> float | None:
    """How light a colour is, 0 black to 1 white, or None when the colour space is not one this can convert."""
    try:
        if space == "gray" and len(comps) == 1:
            return min(1.0, max(0.0, comps[0]))
        if space == "rgb" and len(comps) == 3:
            r, g, b = (min(1.0, max(0.0, c)) for c in comps)
            return 0.299 * r + 0.587 * g + 0.114 * b
        if space == "cmyk" and len(comps) == 4:
            c, m, y, k = (min(1.0, max(0.0, v)) for v in comps)
            return 0.299 * (1 - c) * (1 - k) + 0.587 * (1 - m) * (1 - k) + 0.114 * (1 - y) * (1 - k)
    except (TypeError, ValueError):
        pass
    return None


DEVICE_SPACES = {"/DeviceGray": "gray", "/G": "gray", "/CalGray": "gray", "/DeviceRGB": "rgb", "/RGB": "rgb", "/CalRGB": "rgb", "/DeviceCMYK": "cmyk", "/CMYK": "cmyk"}
BY_COMPONENTS = {1: "gray", 3: "rgb", 4: "cmyk"}


def space_of(value) -> str | None:
    """'gray', 'rgb' or 'cmyk' for a colour space name or array, or None for one that cannot be converted (Separation, DeviceN, Lab, Indexed, a pattern)."""
    value = resolve(value)
    if isinstance(value, str):
        return DEVICE_SPACES.get(str(value))
    if isinstance(value, list) and value:
        head = str(resolve(value[0]))
        if head in DEVICE_SPACES:
            return DEVICE_SPACES[head]
        if head == "/ICCBased" and len(value) > 1:
            n = entry(resolve(value[1]), "/N")
            return BY_COMPONENTS.get(int(n)) if isinstance(n, (int, float)) else None
    return None


@dataclass(frozen=True)
class Gfx:
    """The part of the graphics state that decides whether text can be read. q saves it and Q brings it back."""
    ctm: Matrix = IDENTITY
    fill: float | None = 0.0
    stroke: float | None = 0.0
    fill_space: str | None = "gray"
    stroke_space: str | None = "gray"
    fill_alpha: float = 1.0
    stroke_alpha: float = 1.0
    mode: int = 0
    hscale: float = 1.0
    rise: float = 0.0
    size: float = 0.0
    clip: Box = (-1e9, -1e9, 1e9, 1e9)


@dataclass(frozen=True)
class PageRead:
    text: str
    hidden: list[str]
    why: list[str]
    ocr_chars: int = 0


@dataclass
class _Frame:
    """What a `Do` changed, so that its end puts it back (a form is drawn inside its own q and Q)."""
    gfx: Gfx
    pushed_resources: bool = False
    marked_depth: int = 0  # how many marked content sections were open when the Do began


def _string_length(operands: list, op: str) -> int:
    if op == "TJ":
        return sum(len(x) for x in (operands[0] if operands and isinstance(operands[0], list) else []) if isinstance(x, (str, bytes)))
    item = operands[2] if op == '"' and len(operands) >= 3 else operands[0] if operands else ""
    return len(item) if isinstance(item, (str, bytes)) else 0


class Layers:
    """Which optional content groups (layers) are switched off when the file is opened."""

    def __init__(self, root) -> None:
        props = entry(root, "/OCProperties")
        default = entry(props, "/D")
        self.base_off = str(entry(default, "/BaseState") or "/ON") == "/OFF"
        self.off = self._ids(default, "/OFF")
        self.on = self._ids(default, "/ON")

    @staticmethod
    def _ids(d, key: str) -> set[int]:
        raw = d.get(key) if d is not None and hasattr(d, "get") else None
        items = resolve(raw)
        return {i for i in (getattr(r, "idnum", None) for r in (items if isinstance(items, list) else [])) if i is not None}

    def _group_off(self, idnum: int | None) -> bool:
        if idnum is None:
            return False
        return idnum not in self.on if self.base_off else idnum in self.off

    def hidden(self, raw) -> bool:
        """Is this layer (an OCG, or an OCMD that combines layers) switched off by default?"""
        obj = resolve(raw)
        kind = str(entry(obj, "/Type") or "")
        if kind == "/OCG":
            return self._group_off(getattr(raw, "idnum", None))
        if kind == "/OCMD":
            groups = obj.get("/OCGs") if hasattr(obj, "get") else None
            listed = resolve(groups)
            refs = listed if isinstance(listed, list) else [groups] if groups is not None else []
            states = [self._group_off(getattr(r, "idnum", None)) for r in refs]
            policy = str(entry(obj, "/P") or "/AnyOn")
            if not states:
                return False
            return {"/AnyOn": all(states), "/AllOn": any(states), "/AnyOff": not any(states), "/AllOff": not all(states)}.get(policy, False)
        return False


@dataclass
class PageInk:
    """Follows one page. Pass `before`, `after` and `text` to pypdf's extract_text as the operand and text visitors."""
    page: object
    root: object
    gfx: Gfx = field(default_factory=Gfx)
    saved: list[Gfx] = field(default_factory=list)
    frames: list[_Frame] = field(default_factory=list)
    marked: list[bool] = field(default_factory=list)
    resources: list = field(default_factory=list)
    boxes: list[tuple[Box, float]] = field(default_factory=list)
    path: list[tuple[float, float]] = field(default_factory=list)
    rects: list[Box] = field(default_factory=list)
    only_rects: bool = True
    clip_next: bool = False
    shown: list[str | None] = field(default_factory=list)
    pending: str | None = None
    has_pending: bool = False
    pieces: list[tuple[str, str | None]] = field(default_factory=list)
    big_image: bool = False
    crop: Box = (0.0, 0.0, 612.0, 792.0)
    layers: Layers | None = None
    deadline: float = 0.0

    def __post_init__(self) -> None:
        self.layers = Layers(self.root)
        self.deadline = time.monotonic() + PAGE_SECONDS
        try:
            box = self.page.cropbox
            self.crop = (float(box.left), float(box.bottom), float(box.right), float(box.top))
        except Exception:  # noqa: BLE001
            pass
        self.gfx = replace(self.gfx, clip=self.crop)
        self.resources = [entry(self.page, "/Resources")]

    # -- resources
    def _resource(self, kind: str, name) -> tuple[object, object]:
        """(the object, the raw entry) for a named resource of the drawing in progress."""
        group = entry(self.resources[-1], kind) if self.resources else None
        raw = group.get(str(name)) if group is not None and hasattr(group, "get") else None
        return resolve(raw), raw

    # -- the operator visitors
    def before(self, op, operands, _cm, tm) -> None:
        o = op.decode("latin-1", "replace") if isinstance(op, bytes) else str(op)
        try:
            self._operator(o, list(operands or []), tuple(float(x) for x in tm) if tm is not None else IDENTITY)
        except Exception:  # noqa: BLE001 - a drawing instruction this cannot follow leaves the state as it was; the next one is read
            pass

    def after(self, op, _operands, _cm, _tm) -> None:
        o = op.decode("latin-1", "replace") if isinstance(op, bytes) else str(op)
        if self.has_pending:  # a ' or " shows text after moving to the next line, and that move may hand the earlier text over first; its state belongs to what comes next
            self.shown.append(self.pending)
            self.pending, self.has_pending = None, False
        if o == "Do" and self.frames:
            frame = self.frames.pop()
            self.gfx = frame.gfx
            if frame.pushed_resources and len(self.resources) > 1:
                self.resources.pop()
            del self.marked[frame.marked_depth:]  # a section left open inside a form does not carry on after it

    def _operator(self, o: str, a: list, tm: Matrix) -> None:
        g = self.gfx
        nums = numbers(a)
        if o == "q":
            if len(self.saved) < MAX_STACK:
                self.saved.append(g)
        elif o == "Q":
            if self.saved:
                self.gfx = self.saved.pop()
        elif o == "cm" and nums and len(nums) == 6:
            self.gfx = replace(g, ctm=mul(tuple(nums), g.ctm))
        elif o == "gs" and a:
            self._extgstate(a[0])
        elif o in ("g", "G", "rg", "RG", "k", "K") and nums:
            self._device_colour(o, nums)
        elif o in ("cs", "CS") and a:
            self._colour_space(o, a[0])
        elif o in ("sc", "scn", "SC", "SCN"):
            self._colour(o, a, nums)
        elif o == "Tr" and nums:
            self.gfx = replace(g, mode=int(nums[0]))
        elif o == "Tz" and nums:
            self.gfx = replace(g, hscale=nums[0] / 100.0)
        elif o == "Ts" and nums:
            self.gfx = replace(g, rise=nums[0])
        elif o == "Tf" and len(a) >= 2 and numbers(a[1:2]):
            self.gfx = replace(g, size=float(a[1]))
        elif o in ("Tj", "TJ"):
            self.shown.append(self._reason(tm, _string_length(a, o)))
        elif o in ("'", '"'):
            self.pending, self.has_pending = self._reason(tm, _string_length(a, o)), True
        elif o == "BMC":
            self._mark(False)
        elif o == "BDC":
            self._mark(len(a) >= 2 and str(a[0]) == "/OC" and self._layer_off(a[1]))
        elif o == "EMC" and self.marked:
            self.marked.pop()
        elif o == "Do":
            self._do(a[0] if a else "")
        elif o in ("INLINE IMAGE", "BI"):
            self._image()
        elif o in ("m", "l") and nums and len(nums) >= 2:
            self.path.append(apply(g.ctm, nums[0], nums[1]))
            self.only_rects = False
        elif o in ("c", "v", "y") and nums and len(nums) >= 4:
            self.path.extend(apply(g.ctm, nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2))
            self.only_rects = False
        elif o == "re" and nums and len(nums) == 4:
            x, y, w, h = nums
            corners = [apply(g.ctm, x, y), apply(g.ctm, x + w, y), apply(g.ctm, x + w, y + h), apply(g.ctm, x, y + h)]
            self.path.extend(corners)
            self.rects.append(bbox(corners))
        elif o in ("W", "W*"):
            self.clip_next = True
        elif o in PAINT_OPS:
            self._paint(o in FILL_OPS)

    # -- the graphics state
    def _extgstate(self, name) -> None:
        state, _raw = self._resource("/ExtGState", name)
        fill, stroke = entry(state, "/ca"), entry(state, "/CA")
        self.gfx = replace(self.gfx, fill_alpha=float(fill) if isinstance(fill, (int, float)) else self.gfx.fill_alpha, stroke_alpha=float(stroke) if isinstance(stroke, (int, float)) else self.gfx.stroke_alpha)

    def _device_colour(self, o: str, nums: list[float]) -> None:
        space = {"g": "gray", "rg": "rgb", "k": "cmyk"}[o.lower()]
        value = lightness(space, nums)
        self.gfx = replace(self.gfx, **({"fill": value, "fill_space": space} if o.islower() else {"stroke": value, "stroke_space": space}))

    def _colour_space(self, o: str, name) -> None:
        if str(name) in DEVICE_SPACES:
            space = DEVICE_SPACES[str(name)]
        else:
            obj, _raw = self._resource("/ColorSpace", name)
            space = space_of(obj)
        initial = {"gray": 0.0, "rgb": 0.0, "cmyk": 0.0}.get(space) if space else None  # the initial colour of these spaces is black
        self.gfx = replace(self.gfx, **({"fill": initial, "fill_space": space} if o == "cs" else {"stroke": initial, "stroke_space": space}))

    def _colour(self, o: str, a: list, nums: list[float] | None) -> None:
        space = self.gfx.fill_space if o.islower() else self.gfx.stroke_space
        value = lightness(space, nums) if nums else None  # a pattern name, or a space this cannot convert, is no known lightness
        self.gfx = replace(self.gfx, **({"fill": value} if o.islower() else {"stroke": value}))

    # -- optional content
    def _mark(self, hidden: bool) -> None:
        self.marked.append(hidden)

    def _layer_off(self, props) -> bool:
        if isinstance(props, str):
            obj, raw = self._resource("/Properties", props)
            return bool(self.layers and obj is not None and self.layers.hidden(raw if getattr(raw, "idnum", None) is not None else obj))
        return False

    # -- drawing a picture or a form
    def _image(self) -> None:
        if area(intersect(bbox([apply(self.gfx.ctm, 0, 0), apply(self.gfx.ctm, 1, 0), apply(self.gfx.ctm, 0, 1), apply(self.gfx.ctm, 1, 1)]), self.crop)) >= BIG_IMAGE_SHARE * (area(self.crop) or 1.0):
            self.big_image = True

    def _do(self, name) -> None:
        frame = _Frame(self.gfx, False, len(self.marked))
        self.frames.append(frame)  # always: pypdf reports the end of every Do, whatever it drew
        obj, _raw = self._resource("/XObject", name)
        kind = str(entry(obj, "/Subtype") or "")
        if kind == "/Image":
            self._image()
        elif kind == "/Form" and len(self.frames) <= MAX_STACK:
            matrix = numbers(list(resolve(obj.get("/Matrix")) or []))
            ctm = mul(tuple(matrix), self.gfx.ctm) if matrix and len(matrix) == 6 else self.gfx.ctm
            clip = self.gfx.clip
            box = numbers(list(resolve(obj.get("/BBox")) or []))
            if box and len(box) == 4:
                clip = intersect(clip, bbox([apply(ctm, box[0], box[1]), apply(ctm, box[2], box[1]), apply(ctm, box[2], box[3]), apply(ctm, box[0], box[3])]))
            own = entry(obj, "/Resources")
            self.resources.append(own if own is not None else self.resources[-1])
            frame.pushed_resources = True
            self.gfx = replace(self.gfx, ctm=ctm, clip=clip)
            if "/OC" in obj and self.layers is not None and self.layers.hidden(obj.get("/OC")):
                self.marked.append(True)

    # -- painting
    def _paint(self, fill: bool) -> None:
        g = self.gfx
        if self.path:
            if fill and g.fill is not None and g.fill_alpha >= BACKDROP_ALPHA:
                for box in self._shapes():
                    self.boxes.append((box, g.fill))
                del self.boxes[:-MAX_BOXES]
            if self.clip_next:
                self.gfx = replace(g, clip=intersect(g.clip, bbox(self.path)))
        self.path, self.rects, self.only_rects, self.clip_next = [], [], True, False

    def _shapes(self) -> list[Box]:
        """What a fill covers: each rectangle on its own, or the box of any other shape that fills most of its box (a line or a thin diagonal covers nothing)."""
        if self.only_rects and self.rects:
            return list(self.rects)
        box = bbox(self.path)
        return [box] if area(box) > 0 and polygon_area(self.path) >= 0.5 * area(box) else []

    # -- text
    def _reason(self, tm: Matrix, chars: int) -> str | None:
        """Why the text shown now could not be read by a person, or None."""
        g = self.gfx
        if time.monotonic() > self.deadline:
            return "slow"
        if any(self.marked):
            return "layer_off"
        if g.mode in NO_PAINT_MODES:
            return "invisible"
        m = mul(tm, g.ctm)
        size = abs(g.size) * (abs(det(m)) ** 0.5)
        if size < MIN_VISIBLE_POINTS or abs(g.hscale) < MIN_HSCALE:
            return "tiny"
        width = chars * GLYPH_EM * abs(g.size) * abs(g.hscale)
        low, high = g.rise, g.rise + ASCENT_EM * abs(g.size)
        corners = [apply(m, 0, low), apply(m, width, low), apply(m, 0, high), apply(m, width, high)]
        if not inside(g.clip, corners[0], EDGE):
            return "off_page"
        channels = ([(g.fill, g.fill_alpha)] if g.mode in FILL_MODES else []) + ([(g.stroke, g.stroke_alpha)] if g.mode in STROKE_MODES else [])
        painted = [lum for lum, alpha in channels if alpha > MIN_ALPHA]
        if not painted:
            return "invisible"
        if any(lum is None for lum in painted):
            return None  # a colour this cannot convert is read as visible
        behind = self._behind(corners)
        return "white" if all(abs(lum - behind) < MIN_CONTRAST for lum in painted) else None

    def _behind(self, corners: list[tuple[float, float]]) -> float:
        for box, lum in reversed(self.boxes):
            if all(inside(box, c, 1.0) for c in corners):
                return lum
        return 1.0

    def text(self, text, _cm, _tm, _font, _size) -> None:
        """A piece of text pypdf handed over. It is hidden when any text shown since the last piece was."""
        shown, self.shown = self.shown, []
        text = text if isinstance(text, str) else ""
        reasons = [r for r in shown if r is not None]
        self.pieces.append((text, (reasons[0] if reasons else None) if text.strip() else None))

    # -- the page as a whole
    def result(self, plain: str) -> PageRead:
        """The text of the page with the hidden pieces taken out where they stand. Invisible text on a page that is only a picture is the text layer of a scan: it is read, and counted."""
        pieces = self.pieces
        visible_typed = any(r is None and t.strip() for t, r in pieces)
        scan = self.big_image and not visible_typed
        ocr_chars, hidden, why, kept = 0, [], [], []
        for piece, reason in pieces:
            if reason == "invisible" and scan:
                ocr_chars += len(piece.strip())
                reason = None
            if reason is None:
                kept.append(piece)
            else:
                hidden.append(piece)
                why.append(reason)
        if not hidden or not pieces:
            return PageRead(plain, [], [], ocr_chars if pieces else 0)
        return PageRead("".join(kept), hidden, why, ocr_chars)


def read_page(page, root) -> PageRead:
    ink = PageInk(page, root)
    plain = page.extract_text(visitor_operand_before=ink.before, visitor_operand_after=ink.after, visitor_text=ink.text) or ""
    return ink.result(plain)
