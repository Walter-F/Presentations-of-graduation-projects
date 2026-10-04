"""Этап 1 SPEC: ядро без UI — валидатор, решатель, порядок перестановки."""
import math
import time
from itertools import combinations

import pytest

from app.catalog import CATALOG
from app.demo import demo_plan
from app.models import Item, Notch, Plan, Room, WallElement
from app.order import rearrange
from app.solver import solve
from app.validator import validate, wall_of


def item(id, type, x, y, rot=0, **kw):
    c = CATALOG[type]
    return Item(**{"id": id, "type": type, "label": c["label"], "w": c["w"], "d": c["d"], "h": c["h"],
                   "x": x, "y": y, "rot": rot, **kw})


def with_items(plan, items):
    return plan.model_copy(update={"items": items})


def moved_demo(**changes):
    """Демо, где у предметов заменены поля: moved_demo(armchair=dict(x=130))."""
    p = demo_plan()
    return with_items(p, [i.model_copy(update=changes.get(i.id, {})) for i in p.items])


@pytest.fixture(scope="module")
def demo_result():
    t = time.monotonic()
    r = solve(demo_plan(), [])
    return r, time.monotonic() - t


def replay(plan, steps):
    """Применяет шаги по одному; отдаёт (шаг, состояние после шага)."""
    state = {i.id: i for i in plan.items}
    for s in steps:
        if s.kind == "out":
            state.pop(s.item_id)
        else:
            state[s.item_id] = state.get(s.item_id, next(i for i in plan.items if i.id == s.item_id)) \
                .model_copy(update={"x": s.x, "y": s.y, "rot": s.rot})
        yield s, with_items(plan, list(state.values()))


def key(items):
    return sorted((i.id, round(i.x, 1), round(i.y, 1), i.rot) for i in items)


# 1. демо-комната → 3 разных корректных варианта, каждый ≤ 10 с
def test_demo_three_distinct_valid_variants(demo_result):
    r, total = demo_result
    p = demo_plan()
    assert len(r.variants) == 3, r.reason
    for v in r.variants:
        assert validate(with_items(p, v.items), ref_items=p.items, free_zones=v.free_zones) == []
        assert v.seconds <= 10
    assert total <= 10 * len(r.variants)
    big = [i.id for i in p.items if CATALOG[i.type]["big"]]
    for a, b in combinations(r.variants, 2):
        ia, ib = {i.id: i for i in a.items}, {i.id: i for i in b.items}
        differ = sum((wall_of(p.room, ib[k]) is not None and wall_of(p.room, ib[k]) != wall_of(p.room, ia[k]))
                     or math.hypot(ia[k].x - ib[k].x, ia[k].y - ib[k].y) > 100 for k in big)
        assert differ >= 2
    assert r.variants[0].metrics.moved >= 1  # стул в проходе — «как сейчас» некорректно


# 2. несовместимые закрепления → объяснение
def test_incompatible_pins_explained():
    p = moved_demo(bed=dict(pinned=True), wardrobe=dict(x=100, y=350, rot=0, pinned=True))
    r = solve(p, [])
    assert r.variants == []
    assert {"bed", "wardrobe"} <= set(r.reason_item_ids)
    assert "Кровать" in r.reason and "Шкаф" in r.reason and "Снимите" in r.reason


# 3. валидатор ловит пересечение, закрытую дверь, проход 55 см, предмет у батареи
def test_validator_overlap():
    c = [c for c in validate(moved_demo(armchair=dict(x=130))) if c.rule == 1]
    assert len(c) == 1 and "пересекаются на 10 см" in c[0].text and set(c[0].item_ids) == {"dresser", "armchair"}


def test_validator_door_blocked():
    c = [c for c in validate(moved_demo(dresser=dict(x=290))) if c.rule == 3]
    assert [x.text for x in c] == ["Входная дверь не откроется: мешает «Комод», не хватает 45 см"]
    assert c[0].item_ids == ["dresser"]


def test_validator_passage_55():
    p = demo_plan()
    bed = item("bed", "bed_double", 100, 230, 90)                      # x 0–200
    narrow = with_items(p, [bed, item("wardrobe", "wardrobe", 242.5, 180, w=85)])  # x 200–285, до стены 55
    c = [c for c in validate(narrow) if c.rule == 4]
    window = [x for x in c if x.text.startswith("Проход к окну")]
    assert window and "55 см" in window[0].text and "нужно минимум 60" in window[0].text
    assert "wardrobe" in window[0].item_ids
    wide = with_items(p, [bed, item("wardrobe", "wardrobe", 240, 180, w=80)])        # x 200–280, до стены 60
    assert [x for x in validate(wide) if x.rule == 4] == []


def test_validator_radiator():
    c = [c for c in validate(moved_demo(armchair=dict(x=170, y=55, rot=0))) if c.rule == 5]
    assert [x.text for x in c] == ["«Кресло» в 5 см от батареи, нужно минимум 10"]
    assert c[0].item_ids == ["armchair"]


# 4. каждый шаг порядка перестановки без пересечений; цикл → «в коридор»
def test_rearrange_steps_no_overlap(demo_result):
    p = demo_plan()
    for v in demo_result[0].variants:
        steps = rearrange(p, v.items)
        assert steps
        state = p
        for s, state in replay(p, steps):
            assert validate(state, rules=(1,)) == [], s.text
        assert key(state.items) == key(v.items)

    swap = [i.model_copy(update={"x": 180, "y": 437.5}) if i.id == "dresser" else
            i.model_copy(update={"x": 60, "y": 420}) if i.id == "armchair" else i for i in p.items]
    steps = rearrange(p, swap)
    assert any(s.kind == "out" and s.text == "Временно вынесите «Комод» в коридор" for s in steps)
    assert steps[-1].kind == "back" and steps[-1].item_id == "dresser"
    for s, state in replay(p, steps):
        assert validate(state, rules=(1,)) == [], s.text
    assert key(state.items) == key(swap)


# 5. Г-образная комната: вырез — препятствие, решатель находит вариант
def l_room():
    # стены: 0 верх, 1–2 выступ, 3 правая, 4 нижняя, 5 левая
    return Plan(
        room=Room(w=400, d=400, notch=Notch(corner="tr", w=150, d=150)),
        elements=[WallElement(id="window", kind="window", wall=0, offset=60, width=120, sill=85),
                  WallElement(id="door", kind="door", wall=4, offset=280, width=80, swing="in_left", entrance=True)],
        items=[item("bed", "bed_double", 130, 280, 0), item("wardrobe", "wardrobe", 370, 230, 90),
               item("desk", "desk", 30, 90, 270), item("chair", "chair", 85, 90, 90),
               item("dresser", "dresser", 200, 22.5, 0)])


def test_l_room():
    p = l_room()
    notch = with_items(p, [i.model_copy(update={"x": 330, "y": 60}) if i.id == "dresser" else i for i in p.items])
    assert any(c.rule == 1 and c.item_ids == ["dresser"] for c in validate(notch))
    r = solve(p, [], n=1)
    assert len(r.variants) == 1, r.reason
    v = r.variants[0]
    assert validate(with_items(p, v.items), ref_items=p.items, free_zones=v.free_zones) == []


# 6. «как сейчас» с пересечением — перестановка всё равно строится
def test_rearrange_from_overlapping_as_now():
    p = moved_demo(armchair=dict(x=130))
    r = solve(p, [], n=1)
    assert len(r.variants) == 1, r.reason
    target = r.variants[0].items
    steps = rearrange(p, target)
    state = p
    for s, state in replay(p, steps):
        assert not any(s.item_id in c.item_ids for c in validate(state, rules=(1,))), s.text
    assert key(state.items) == key(target)


# 7. слишком много мебели → «не помещается» с самыми крупными предметами
def test_too_much_furniture():
    p = Plan(room=Room(w=200, d=200),
             elements=[WallElement(id="door", kind="door", wall=2, offset=110, width=80, swing="in_left",
                                   entrance=True)],
             items=[item("bed", "bed_double", 100, 100), item("sofa", "sofa", 100, 45),
                    item("wardrobe", "wardrobe", 50, 170), item("desk", "desk", 140, 170)])
    r = solve(p, [])
    assert r.variants == []
    assert "не помещается" in r.reason and "«Кровать двуспальная»" in r.reason and "«Диван»" in r.reason
    assert {"bed", "sofa"} <= set(r.reason_item_ids)
