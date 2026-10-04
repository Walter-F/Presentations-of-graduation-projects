"""Порядок перестановки (SPEC шаг 8): по одному предмету, промежуточные состояния без пересечений.
Зоны и проходы на время переноски не проверяются. Цикл — предмет временно выносится в коридор
и возвращается последним."""
from .models import Item, Plan, Step, footprint, overlaps, wall_normal
from .validator import fmt, moved, validate, wall_of

_TURN = {90: "на 90° по часовой стрелке", 180: "на 180°", 270: "на 90° против часовой стрелки"}
_SIDE = {(0, 1): "верхней стене", (0, -1): "нижней стене", (1, 0): "левой стене", (-1, 0): "правой стене"}


def _area(it: Item) -> float:
    return it.w * it.d


def _wall_name(plan: Plan, k: int) -> str:
    kinds = {e.kind for e in plan.elements if e.wall == k}
    if "window" in kinds:
        return "стене с окном"
    if "door" in kinds:
        return "стене с дверью"
    if "balcony_door" in kinds:
        return "стене с балконной дверью"
    return _SIDE[wall_normal(plan.room, k)]


def _move_text(plan: Plan, a: Item, b: Item) -> str:
    dx, dy = b.x - a.x, b.y - a.y
    shift = []
    if abs(dx) > 2.5:
        shift.append(f"{'вправо' if dx > 0 else 'влево'} на {fmt(abs(dx))} см")
    if abs(dy) > 2.5:
        shift.append(f"{'вниз' if dy > 0 else 'вверх'} на {fmt(abs(dy))} см")
    turn = _TURN.get((b.rot - a.rot) % 360)
    if not shift:
        return f"Поверните «{a.label}» {turn}"
    k = wall_of(plan.room, b)
    to_wall = k is not None and k != wall_of(plan.room, a)
    text = (f"Переставьте «{a.label}» к {_wall_name(plan, k)}: " if to_wall else f"Сдвиньте «{a.label}» ") + \
        " и ".join(shift) + " по плану"
    return text + (f", поверните {turn}" if turn else "")


def _back_text(plan: Plan, b: Item) -> str:
    k = wall_of(plan.room, b)
    fp = footprint(b)
    where = f"к {_wall_name(plan, k)}" if k is not None else \
        f"в {fmt(fp[0])} см от левой и {fmt(fp[1])} см от верхней стены по плану"
    return f"Верните «{b.label}» из коридора и поставьте {where}"


def rearrange(plan_before: Plan, after_items: list[Item]) -> list[Step]:
    before = {i.id: i for i in plan_before.items}
    state = dict(before)
    pending = sorted((i for i in after_items if i.id in before and moved(before[i.id], i)), key=_area, reverse=True)
    steps, evicted = [], []

    def step(kind, it, text):
        steps.append(Step(n=len(steps) + 1, kind=kind, item_id=it.id, text=text, x=it.x, y=it.y, rot=it.rot))

    def blocked(t: Item) -> bool:
        trial = plan_before.model_copy(update={"items": [t if i.id == t.id else i for i in state.values()]})
        return any(t.id in c.item_ids for c in validate(trial, rules=(1,)))

    while pending:
        t = next((t for t in pending if not blocked(t)), None)
        if t:
            step("move", t, _move_text(plan_before, state[t.id], t))
            state[t.id] = t
        else:  # цикл: выносим самый маленький предмет, который стоит на чужом месте
            fps = {p.id: footprint(p) for p in pending}
            blockers = [p for p in pending if any(q.id != p.id and overlaps(footprint(state[p.id]), fps[q.id])
                                                  for q in pending)]
            t = min(blockers or pending, key=_area)
            step("out", state[t.id], f"Временно вынесите «{t.label}» в коридор")
            del state[t.id]
            evicted.append(t)
        pending.remove(t)
    for t in evicted:
        state[t.id] = t
        step("back", t, _back_text(plan_before, t))
    return steps
