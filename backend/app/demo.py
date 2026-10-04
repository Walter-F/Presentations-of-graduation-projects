"""«Демо-комната» 3,4 × 4,6 м — расстановка «как сейчас».

Стул выдвинут в проход между кроватью и столом: проход к окну и шкафу уже 60 см
(правило 4), поэтому первый вариант обязан что-то сдвинуть."""
from .catalog import CATALOG
from .models import Item, Plan, Room, WallElement


def _item(id, type, x, y, rot, confidence=0.9):
    c = CATALOG[type]
    return Item(id=id, type=type, label=c["label"], w=c["w"], d=c["d"], h=c["h"], x=x, y=y, rot=rot,
                confidence=confidence)


def demo_plan() -> Plan:
    return Plan(
        room=Room(w=340, d=460, height=260),
        elements=[
            WallElement(id="window", kind="window", wall=0, offset=95, width=150, sill=85),
            WallElement(id="radiator", kind="radiator", wall=0, offset=120, width=100),
            WallElement(id="door", kind="door", wall=2, offset=250, width=80, swing="in_right", entrance=True),
        ],
        items=[
            _item("bed", "bed_double", 100, 240, 270),         # x 0–200, y 160–320, изголовье у левой стены
            _item("nightstand", "nightstand", 20, 137.5, 270, confidence=0.5),
            _item("wardrobe", "wardrobe", 310, 50, 90),        # x 280–340, y 0–100
            _item("desk", "desk", 310, 210, 90),               # x 280–340, y 150–270
            _item("chair", "chair", 250, 212.5, 270),          # x 225–275 — в проходе
            _item("dresser", "dresser", 60, 437.5, 180),       # x 20–100, y 415–460
            _item("armchair", "armchair", 180, 420, 180),      # x 140–220, y 380–460
        ],
    )
