"""Модель данных (провод = эти Pydantic-модели) и геометрия плана.

Сантиметры, градусы. Начало координат — левый верхний угол, x вправо, y вниз.
Прямоугольник везде — кортеж (x0, y0, x1, y1).
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from .catalog import CATALOG, RADIATOR_DEPTH, RADIATOR_GAP, STRIP

Rect = tuple[float, float, float, float]


class Notch(BaseModel):
    corner: Literal["tl", "tr", "br", "bl"]
    w: float
    d: float


class Room(BaseModel):
    w: float
    d: float
    height: float = 260
    notch: Notch | None = None


class WallElement(BaseModel):
    id: str
    kind: Literal["door", "balcony_door", "window", "radiator"]
    wall: int
    offset: float
    width: float
    swing: Literal["in_left", "in_right", "out"] | None = None
    entrance: bool = False
    sill: float | None = None


class Item(BaseModel):
    id: str
    type: str
    label: str
    w: float
    d: float
    h: float
    x: float
    y: float
    rot: int = 0
    pinned: bool = False
    confidence: float = Field(1.0, ge=0, le=1)

    @field_validator("rot", mode="before")
    @classmethod
    def _rot(cls, v):
        v = round(float(v)) % 360
        if v % 90:
            raise ValueError("rot must be 0, 90, 180 or 270")
        return v


class NearWall(BaseModel):
    kind: Literal["near_wall"] = "near_wall"
    item: str
    target: Literal["window", "door", "radiator", "any"]


class Near(BaseModel):
    kind: Literal["near"] = "near"
    a: str
    b: str
    max_cm: float


class FarFrom(BaseModel):
    kind: Literal["far_from"] = "far_from"
    a: str
    b: str
    min_cm: float


class Facing(BaseModel):
    kind: Literal["facing"] = "facing"
    a: str
    b: str


class HiddenFromEntrance(BaseModel):
    kind: Literal["hidden_from_entrance"] = "hidden_from_entrance"
    item: str


class FreeZone(BaseModel):
    kind: Literal["free_zone"] = "free_zone"
    w: float
    d: float
    at: Literal["wall", "corner"]


class Keep(BaseModel):
    kind: Literal["keep"] = "keep"
    item: str


Wish = Annotated[Union[NearWall, Near, FarFrom, Facing, HiddenFromEntrance, FreeZone, Keep],
                 Field(discriminator="kind")]


class Plan(BaseModel):
    room: Room
    elements: list[WallElement] = []
    items: list[Item] = []

    @model_validator(mode="after")
    def _check(self):
        ids = [i.id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("item ids must be unique")
        if sum(e.entrance and e.kind == "door" for e in self.elements) != 1:
            raise ValueError("exactly one entrance door is required")
        if any(e.wall >= len(walls(self.room)) for e in self.elements):
            raise ValueError("wall index out of range")
        if any(i.type not in CATALOG for i in self.items):
            raise ValueError("unknown item type")
        return self


class Conflict(BaseModel):
    rule: int
    text: str
    item_ids: list[str] = []


class Metrics(BaseModel):
    free_m2: float
    free_pct: float
    min_pass_cm: int | None
    doors_ok: bool
    wishes_ok: int
    wishes_total: int
    moved: int


class Variant(BaseModel):
    items: list[Item]
    free_zones: list[Rect] = []
    metrics: Metrics
    seconds: float


class SolveResult(BaseModel):
    variants: list[Variant] = []
    reason: str | None = None
    reason_item_ids: list[str] = []


class Step(BaseModel):
    n: int
    kind: Literal["move", "out", "back"]
    item_id: str
    text: str
    x: float
    y: float
    rot: int


# ---------- геометрия ----------

def room_poly(room: Room) -> list[tuple[float, float]]:
    """Вершины по часовой стрелке на экране, первая — с наименьшими (y, x)."""
    w, d, n = room.w, room.d, room.notch
    c = {"tl": [(0, 0)], "tr": [(w, 0)], "br": [(w, d)], "bl": [(0, d)]}
    if n:
        c[n.corner] = {"tl": [(0, n.d), (n.w, n.d), (n.w, 0)],
                       "tr": [(w - n.w, 0), (w - n.w, n.d), (w, n.d)],
                       "br": [(w, d - n.d), (w - n.w, d - n.d), (w - n.w, d)],
                       "bl": [(n.w, d), (n.w, d - n.d), (0, d - n.d)]}[n.corner]
    poly = c["tl"] + c["tr"] + c["br"] + c["bl"]
    k = poly.index(min(poly, key=lambda p: (p[1], p[0])))
    return poly[k:] + poly[:k]


def walls(room: Room) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    p = room_poly(room)
    return [(p[i], p[(i + 1) % len(p)]) for i in range(len(p))]


def wall_normal(room: Room, k: int) -> tuple[int, int]:
    """Единичная нормаль стены внутрь комнаты."""
    (px, py), (qx, qy) = walls(room)[k]
    return (0, 1 if qx > px else -1) if py == qy else (-1 if qy > py else 1, 0)


def notch_rect(room: Room) -> Rect | None:
    n = room.notch
    if not n:
        return None
    x0 = 0 if n.corner in ("tl", "bl") else room.w - n.w
    y0 = 0 if n.corner in ("tl", "tr") else room.d - n.d
    return (x0, y0, x0 + n.w, y0 + n.d)


def el_rect(room: Room, el: WallElement, depth: float) -> Rect:
    """Проём элемента × depth внутрь комнаты (depth=0 — сам проём)."""
    (px, py), (qx, qy) = walls(room)[el.wall]
    nx, ny = wall_normal(room, el.wall)
    if py == qy:
        a = min(px, qx) + el.offset
        return (a, py, a + el.width, py + depth) if ny > 0 else (a, py - depth, a + el.width, py)
    a = min(py, qy) + el.offset
    return (px, a, px + depth, a + el.width) if nx > 0 else (px - depth, a, px, a + el.width)


def door_square(room: Room, el: WallElement) -> Rect | None:
    if el.kind in ("door", "balcony_door") and el.swing in ("in_left", "in_right"):
        return el_rect(room, el, el.width)
    return None


def strip60(room: Room, el: WallElement) -> Rect:
    return el_rect(room, el, STRIP)


def radiator_body(room: Room, el: WallElement) -> Rect:
    return el_rect(room, el, RADIATOR_DEPTH)


def radiator_keepout(room: Room, el: WallElement) -> Rect:
    return grow(radiator_body(room, el), RADIATOR_GAP)


def size_at(w: float, d: float, rot: int) -> tuple[float, float]:
    return (w, d) if rot % 180 == 0 else (d, w)


def footprint(it: Item) -> Rect:
    sx, sy = size_at(it.w, it.d, it.rot)
    return (it.x - sx / 2, it.y - sy / 2, it.x + sx / 2, it.y + sy / 2)


_SIDE = {"front": (0, 1), "back": (0, -1), "left": (-1, 0), "right": (1, 0)}


def side_dir(side: str, rot: int) -> tuple[int, int]:
    """Направление стороны предмета; поворот по часовой стрелке на экране."""
    vx, vy = _SIDE[side]
    for _ in range(rot // 90):
        vx, vy = -vy, vx
    return vx, vy


def band(r: Rect, direction: tuple[int, int], depth: float) -> Rect:
    """Полоса глубины depth вдоль всей стороны прямоугольника в направлении direction."""
    x0, y0, x1, y1 = r
    return {(1, 0): (x1, y0, x1 + depth, y1), (-1, 0): (x0 - depth, y0, x0, y1),
            (0, 1): (x0, y1, x1, y1 + depth), (0, -1): (x0, y0 - depth, x1, y0)}[direction]


def zone_rects(it: Item) -> list[tuple[str, Rect]]:
    fp = footprint(it)
    return [(s, band(fp, side_dir(s, it.rot), z)) for s, z in CATALOG[it.type]["zones"].items()]


def grow(r: Rect, g: float) -> Rect:
    return (r[0] - g, r[1] - g, r[2] + g, r[3] + g)


def inter(a: Rect, b: Rect) -> tuple[float, float]:
    """Размеры пересечения; оба > 0 — прямоугольники пересекаются (касание не считается)."""
    return min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])


def overlaps(a: Rect, b: Rect) -> bool:
    ix, iy = inter(a, b)
    return ix > 1e-6 and iy > 1e-6


def gaps(a: Rect, b: Rect) -> tuple[float, float]:
    """Зазоры по x и по y (0, если проекции перекрываются)."""
    return max(0, b[0] - a[2], a[0] - b[2]), max(0, b[1] - a[3], a[1] - b[3])


def wall_rects(room: Room) -> list[Rect]:
    """Всё, что за стенами: четыре полосы снаружи и вырез."""
    B = 1e5
    out = [(-B, -B, 0, B), (room.w, -B, B, B), (-B, -B, B, 0), (-B, room.d, B, B)]
    n = notch_rect(room)
    return out + [n] if n else out
