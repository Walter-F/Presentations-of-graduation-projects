"""Один валидатор для вариантов, ручной правки и порядка перестановки (SPEC «Правила корректности»)."""
import heapq
import math
from itertools import combinations
from typing import NamedTuple

import cv2
import numpy as np

from .catalog import CATALOG, GRID, MIN_PASS, NEAR_EL, RADIATOR_GAP, SNAP, TALL
from .models import (Conflict, Item, Metrics, Plan, Room, band, door_square, el_rect, footprint, gaps, inter,
                     notch_rect, overlaps, radiator_body, radiator_keepout, side_dir, strip60, wall_normal,
                     wall_rects, walls, zone_rects)

INF = 1e9
_NB = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def fmt(v: float) -> str:
    """Число для текста: целые без дробной части, иначе через запятую."""
    return f"{round(v, 1):g}".replace(".", ",")


def moved(a: Item, b: Item) -> bool:
    return math.hypot(a.x - b.x, a.y - b.y) > 2.5 or a.rot != b.rot


def _obstacles(plan: Plan) -> list[tuple]:
    """Стены, вырез и корпуса батарей: (прямоугольник, None)."""
    return [(r, None) for r in wall_rects(plan.room)] + \
        [(radiator_body(plan.room, e), None) for e in plan.elements if e.kind == "radiator"]


# ---------- правило 2: зоны обслуживания ----------

def _zone_problems(plan: Plan, it: Item, side: str, z) -> list[tuple[float, str | None]]:
    """[(сколько не хватает вдоль глубины зоны, id мешающего предмета или None для стены)]."""
    axis = 0 if side_dir(side, it.rot)[0] else 1
    allow = CATALOG[it.type]["allow_in_zone"]
    obs = _obstacles(plan) + [(footprint(o), o.id) for o in plan.items
                              if o.id != it.id and o.type not in allow]
    return [(inter(z, r)[axis], oid) for r, oid in obs if overlaps(z, r)]


def _zones(plan: Plan, it: Item) -> list[tuple[list, list]]:
    """Зоны предмета: [(прямоугольники, проблемы)]. У односпальной кровати хватает одной длинной
    стороны, поэтому её стороны — одна цель: годные стороны, а если годных нет — худшая проблема."""
    zs = [([z], _zone_problems(plan, it, s, z)) for s, z in zone_rects(it)]
    if not CATALOG[it.type]["one_side"] or not zs:
        return zs
    good = [z[0] for z, p in zs if not p]
    if good:
        return [(good, [])]
    return [min(zs, key=lambda zp: max(n for n, _ in zp[1]))]


# ---------- правило 4: проходы ----------

class Passage(NamedTuple):
    name: str               # «окну», «балконной двери», «Шкаф распашной»
    owner: str | None       # id предмета, чья это зона
    width: float | None     # ширина по сетке: 2 × наименьшее расстояние на самом широком пути; None — ∞
    gap: float | None       # точный зазор между препятствиями в узком месте; 0 — не пройти
    ids: list[str]          # предметы у узкого места
    around: list[str]       # предметы по краю области, куда от входа проходят 60 см (для отсечения решателя)
    pair: tuple | None      # два препятствия по бокам узкого места (для отсечения решателя)


def _raster(shape, rects) -> np.ndarray:
    """Узлы сетки, попавшие в замкнутые прямоугольники (округление наружу)."""
    m = np.zeros(shape, bool)
    for x0, y0, x1, y1 in rects:
        i0, i1 = math.floor(x0 / GRID + 1e-6), math.ceil(x1 / GRID - 1e-6)
        j0, j1 = math.floor(y0 / GRID + 1e-6), math.ceil(y1 / GRID - 1e-6)
        if i1 >= 0 and j1 >= 0:
            m[max(j0, 0):j1 + 1, max(i0, 0):i1 + 1] = True
    return m


def _rect_dist(a, b) -> float:
    return math.hypot(*gaps(a, b))


def _between(u, v) -> bool:
    """Точка лежит на отрезке между ближайшими точками двух препятствий (векторы u, v от неё к ним)."""
    dx, dy = v[0] - u[0], v[1] - u[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return False
    t = min(max(-(u[0] * dx + u[1] * dy) / L2, 0), 1)
    return t not in (0, 1) and math.hypot(u[0] + t * dx, u[1] + t * dy) <= GRID


def _bottleneck(plan: Plan, px: float, py: float, r: float):
    """Узкое место (px, py) с расстоянием r до препятствий по сетке: точный зазор, предметы рядом
    и пара препятствий по обе стороны ((прямоугольник, id или None), ...) или None."""
    obs = _obstacles(plan) + [(footprint(i), i.id) for i in plan.items]
    near = []
    for rect, oid in obs:
        nx, ny = min(max(px, rect[0]), rect[2]), min(max(py, rect[1]), rect[3])
        if math.hypot(nx - px, ny - py) <= r + 1.5 * GRID:
            near.append((rect, oid, nx - px, ny - py))
    pairs = [(_rect_dist(a[0], b[0]), (a[:2], b[:2])) for a, b in combinations(near, 2) if _between(a[2:], b[2:])]
    gap, pair = min(pairs, key=lambda g: g[0], default=(2 * r, None))
    return gap, list(dict.fromkeys(oid for _, oid, _, _ in near if oid)), pair


def passages(plan: Plan) -> list[Passage]:
    room = plan.room
    nx, ny = math.ceil(room.w / GRID) + 1, math.ceil(room.d / GRID) + 1
    wall = _raster((ny, nx), [r for r, _ in _obstacles(plan)])
    free = ~(wall | _raster((ny, nx), [footprint(i) for i in plan.items]))
    d = cv2.distanceTransform(free.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE) * GRID
    trav = (~wall).ravel().tolist()
    dl = d.ravel().tolist()
    gx, gy = np.meshgrid(np.arange(nx) * GRID, np.arange(ny) * GRID)

    def near_mask(r, dist):
        dx = np.maximum(np.maximum(r[0] - gx, gx - r[2]), 0)
        dy = np.maximum(np.maximum(r[1] - gy, gy - r[3]), 0)
        return (np.hypot(dx, dy) <= dist + 1e-6) & ~wall

    # самый широкий путь (Дейкстра по максимуму минимума) от квадрата входной двери
    door = next(e for e in plan.elements if e.entrance)
    best, par, done = [-1.0] * len(dl), [-1] * len(dl), [False] * len(dl)
    heap = []
    for s in np.flatnonzero(near_mask(el_rect(room, door, door.width), 0)).tolist():
        best[s] = INF if dl[s] > 0 else 0.0
        heap.append((-best[s], s))
    heapq.heapify(heap)
    while heap:
        v, p = heapq.heappop(heap)
        if done[p]:
            continue
        done[p] = True
        i, j = p % nx, p // nx
        for di, dj in _NB:
            ii, jj = i + di, j + dj
            if 0 <= ii < nx and 0 <= jj < ny:
                q = jj * nx + ii
                if trav[q] and not done[q]:
                    w = min(-v, dl[q])
                    if w > best[q]:
                        best[q], par[q] = w, p
                        heapq.heappush(heap, (-w, q))
    best_a = np.array(best).reshape(ny, nx)

    targets = []
    for it in plan.items:
        targets += [(f"«{it.label}»", it.id, rects) for rects, _ in _zones(plan, it)]
    for e in plan.elements:
        if e.kind == "window":
            targets.append(("окну", None, [strip60(room, e)]))
        elif e.kind == "balcony_door":
            targets.append(("балконной двери", None, [el_rect(room, e, 0)]))

    out, around = [], None
    for name, owner, rects in targets:
        m = np.zeros_like(wall)
        for r in rects:
            m |= near_mask(r, MIN_PASS / 2)
        vals = np.where(m, best_a, -1.0)
        t = int(vals.argmax())
        if vals.flat[t] >= INF / 2:
            out.append(Passage(name, owner, None, None, [], [], None))
            continue
        b = q = t  # узкое место — ближайшая ко входу точка пути с наименьшим расстоянием
        while par[q] != -1:
            if dl[q] <= dl[b]:
                b = q
            q = par[q]
        width = 2 * max(float(vals.flat[t]), 0.0)
        gap, ids, pair = _bottleneck(plan, b % nx * GRID, b // nx * GRID, dl[b])
        if around is None:
            reach = best_a >= MIN_PASS / 2 - 1e-6
            around = [i.id for i in plan.items if (near_mask(footprint(i), MIN_PASS / 2 + 1.5 * GRID) & reach).any()]
        out.append(Passage(name, owner, width, gap if width > 0 else 0.0, ids, around, pair))
    return out


def passage_ok(p: Passage) -> bool:
    return p.width is None or p.width >= MIN_PASS - 1e-6


# ---------- валидатор ----------

def validate(plan: Plan, ref_items=None, free_zones=(), rules=(1, 2, 3, 4, 5, 6)) -> list[Conflict]:
    room, items = plan.room, plan.items
    fps = {i.id: footprint(i) for i in items}
    out: list[Conflict] = []

    def add(rule, text, ids):
        out.append(Conflict(rule=rule, text=text, item_ids=list(dict.fromkeys(ids))))

    if 1 in rules:
        for it in items:
            n = max((min(inter(fps[it.id], r)) for r in wall_rects(room) if overlaps(fps[it.id], r)), default=0)
            if n:
                add(1, f"«{it.label}» выходит за стену на {fmt(n)} см", [it.id])
        for a, b in combinations(items, 2):
            if overlaps(fps[a.id], fps[b.id]):
                add(1, f"«{a.label}» и «{b.label}» пересекаются на {fmt(min(inter(fps[a.id], fps[b.id])))} см",
                    [a.id, b.id])

    if 2 in rules:
        for it in items:
            for _, probs in _zones(plan, it):
                for n, oid in probs:
                    add(2, f"{CATALOG[it.type]['zone_text']}: не хватает {fmt(n)} см", [it.id, oid] if oid else [it.id])

    if 3 in rules:
        for e in plan.elements:
            sq = door_square(room, e)
            if not sq:
                continue
            name = "Входная дверь" if e.entrance else "Балконная дверь" if e.kind == "balcony_door" else "Дверь"
            axis = 1 if wall_normal(room, e.wall)[1] else 0
            for it in items:
                if overlaps(sq, fps[it.id]):
                    n = inter(sq, fps[it.id])[axis]
                    add(3, f"{name} не откроется: мешает «{it.label}», не хватает {fmt(n)} см", [it.id])

    if 4 in rules:
        seen = {}
        for p in passages(plan):
            if passage_ok(p):
                continue
            text = (f"К {p.name} не пройти от входа" if p.width == 0 else
                    f"Проход к {p.name} {fmt(p.gap if p.gap < MIN_PASS else p.width)} см, нужно минимум {MIN_PASS}")
            ids = ([p.owner] if p.owner else []) + p.ids
            if text in seen:
                seen[text].item_ids = list(dict.fromkeys(seen[text].item_ids + ids))
            else:
                add(4, text, ids)
                seen[text] = out[-1]

    if 5 in rules:
        for e in plan.elements:
            if e.kind == "radiator":
                keep, body = radiator_keepout(room, e), radiator_body(room, e)
                for it in items:
                    if overlaps(fps[it.id], keep):
                        g = max(gaps(fps[it.id], body))
                        add(5, f"«{it.label}» в {fmt(g)} см от батареи, нужно минимум {RADIATOR_GAP}", [it.id])
            if e.kind in ("window", "radiator"):
                what = "заслоняет окно" if e.kind == "window" else "закрывает батарею"
                where = "к окну" if e.kind == "window" else "к батарее"
                for it in items:
                    if it.h > TALL and overlaps(fps[it.id], strip60(room, e)):
                        add(5, f"«{it.label}» высотой {fmt(it.h)} см {what}: ближе 60 см {where} — "
                               f"только предметы до {TALL} см", [it.id])

    if 6 in rules:
        ref = {i.id: i for i in ref_items or []}
        for it in items:
            r = ref.get(it.id)
            if it.pinned and r and moved(it, r):
                how = f"сдвинут на {fmt(math.hypot(it.x - r.x, it.y - r.y))} см" if math.hypot(
                    it.x - r.x, it.y - r.y) > 2.5 else "повёрнут"
                add(6, f"«{it.label}»: предмет закреплён, его нельзя двигать ({how})", [it.id])
        for z in free_zones:
            for it in items:
                if overlaps(fps[it.id], z):
                    add(6, f"Свободная зона {fmt(z[2] - z[0])}×{fmt(z[3] - z[1])} см занята: «{it.label}»", [it.id])
    return out


# ---------- пожелания и метрики ----------

def wall_of(room: Room, it: Item) -> int | None:
    """Стена, к которой предмет стоит спинкой (зазор ≤ SNAP), иначе None."""
    fp = footprint(it)
    back = side_dir("back", it.rot)
    for k, ((px, py), (qx, qy)) in enumerate(walls(room)):
        nx, ny = wall_normal(room, k)
        if back != (-nx, -ny):
            continue
        if ny:
            gap = fp[1] - py if ny > 0 else py - fp[3]
            ov = min(fp[2], max(px, qx)) - max(fp[0], min(px, qx))
        else:
            gap = fp[0] - px if nx > 0 else px - fp[2]
            ov = min(fp[3], max(py, qy)) - max(fp[1], min(py, qy))
        if -1e-6 <= gap <= SNAP and ov > 0:
            return k
    return None


def entrance_strip(plan: Plan):
    """Полоса шириной в дверь от входа до противоположной стены."""
    door = next(e for e in plan.elements if e.entrance)
    return el_rect(plan.room, door, plan.room.d if wall_normal(plan.room, door.wall)[1] else plan.room.w)


EL_KINDS = {"window": ("window",), "door": ("door", "balcony_door"), "radiator": ("radiator",)}


def wish_ok(plan: Plan, wish, free_zones=()) -> bool:
    its = {i.id: i for i in plan.items}
    k = wish.kind
    if k == "near_wall":
        it = its[wish.item]
        if wish.target == "any":
            return wall_of(plan.room, it) is not None
        return any(max(gaps(footprint(it), el_rect(plan.room, e, 0))) <= NEAR_EL
                   for e in plan.elements if e.kind in EL_KINDS[wish.target])
    if k in ("near", "far_from"):
        g = max(gaps(footprint(its[wish.a]), footprint(its[wish.b])))
        return g <= wish.max_cm if k == "near" else g >= wish.min_cm
    if k == "facing":
        a, b = its[wish.a], its[wish.b]
        s = band(footprint(a), side_dir("front", a.rot), 1e5)
        return s[0] <= b.x <= s[2] and s[1] <= b.y <= s[3]
    if k == "hidden_from_entrance":
        return not overlaps(footprint(its[wish.item]), entrance_strip(plan))
    if k == "free_zone":
        need = sorted((wish.w, wish.d))
        return any(all(a >= b - 1e-6 for a, b in zip(sorted((z[2] - z[0], z[3] - z[1])), need))
                   and not any(overlaps(footprint(i), z) for i in plan.items) for z in free_zones)
    return True  # keep — закрепление, его держит решатель и правило 6


def room_area(room: Room) -> float:
    n = notch_rect(room)
    return room.w * room.d - ((n[2] - n[0]) * (n[3] - n[1]) if n else 0)


def metrics(plan: Plan, wishes, free_zones, base_items) -> Metrics:
    area = room_area(plan.room)
    free = area - sum((f[2] - f[0]) * (f[3] - f[1]) for f in map(footprint, plan.items))
    base = {i.id: i for i in base_items}
    gaps_ = [p.gap for p in passages(plan) if p.gap is not None]
    return Metrics(
        free_m2=round(free / 1e4, 2), free_pct=round(100 * free / area, 1),
        min_pass_cm=round(min(gaps_)) if gaps_ else None,
        doors_ok=not validate(plan, rules=(2, 3)),
        wishes_ok=sum(wish_ok(plan, w, free_zones) for w in wishes), wishes_total=len(wishes),
        moved=sum(moved(i, base[i.id]) for i in plan.items if i.id in base))
