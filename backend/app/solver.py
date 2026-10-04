"""Решатель CP-SAT (SPEC «Решатель»). Всё в целых клетках сетки GRID; препятствия округлены наружу,
размеры предметов — вверх, поэтому принятое решателем проходит валидатор по правилам 1–3, 5, 6.
Правило 4 проверяется валидатором после каждого решения, провал запрещается отсечением."""
import math
import time

from ortools.sat.python import cp_model

from .catalog import CATALOG, GRID, MIN_PASS, NEAR_EL, SNAP, STRIP, TALL
from .models import (Plan, SolveResult, Variant, door_square, el_rect, gaps, notch_rect, radiator_body,
                     radiator_keepout, side_dir, size_at, wall_normal, walls)
from .validator import EL_KINDS, entrance_strip, metrics, passage_ok, passages, validate, wall_of

VARIANT_SECONDS = 10.0
CALL_SECONDS = 3.0  # одна попытка CP-SAT; после неё — проверка прохода
ROTS = (0, 90, 180, 270)
EPS = 1e-6


def _out(r):
    """Неподвижный прямоугольник в клетках, округлённый наружу: (x0, y0, x1, y1)."""
    return (math.floor(r[0] / GRID + EPS), math.floor(r[1] / GRID + EPS),
            math.ceil(r[2] / GRID - EPS), math.ceil(r[3] / GRID - EPS))


class _Model:
    def __init__(self, plan: Plan, wishes, base_items):
        m = self.m = cp_model.CpModel()
        self.plan, room = plan, plan.room
        self.items = items = plan.items
        self.idx = {it.id: i for i, it in enumerate(items)}
        W, H = math.floor(room.w / GRID + EPS), math.floor(room.d / GRID + EPS)
        self.walls = walls(room)
        self._at = {}

        def fixed(r):
            x0, y0, x1, y1 = _out(r)
            return m.new_fixed_size_interval_var(x0, x1 - x0, ""), m.new_fixed_size_interval_var(y0, y1 - y0, "")

        def no_overlap(rects):
            m.add_no_overlap_2d([r[0] for r in rects], [r[1] for r in rects])

        # предметы: левый верхний угол (x, y) и 4 опциональных прямоугольника по поворотам
        self.x, self.y, self.p, self.real, self.rects, self.ex, self.ey, self.grid0 = [], [], [], [], [], [], [], []
        zones = []  # по предметам: прямоугольники зон
        for it in items:
            sw, sd = math.ceil(it.w / GRID - EPS), math.ceil(it.d / GRID - EPS)
            sizes = [size_at(sw, sd, r) for r in ROTS]
            x, y = m.new_int_var(0, W, ""), m.new_int_var(0, H, "")
            p = [m.new_bool_var("") for _ in ROTS]
            m.add_exactly_one(p)
            rects, zr = [], []
            for o, (sx, sy) in enumerate(sizes):
                m.add(x + sx <= W).only_enforce_if(p[o])
                m.add(y + sy <= H).only_enforce_if(p[o])
                rects.append((m.new_optional_fixed_size_interval_var(x, sx, p[o], ""),
                              m.new_optional_fixed_size_interval_var(y, sy, p[o], "")))
            side = m.new_bool_var("") if CATALOG[it.type]["one_side"] else None
            for s, z in CATALOG[it.type]["zones"].items():
                zg = math.ceil(z / GRID - EPS)
                for o, (sx, sy) in enumerate(sizes):
                    dx, dy, zw, zh = {(1, 0): (sx, 0, zg, sy), (-1, 0): (-zg, 0, zg, sy),
                                      (0, 1): (0, sy, sx, zg), (0, -1): (0, -zg, sx, zg)}[side_dir(s, ROTS[o])]
                    lit = p[o]
                    if side is not None:  # односпальная: зона только с выбранной длинной стороны
                        lit = m.new_bool_var("")
                        sl = side if s == "left" else ~side
                        m.add_bool_and([p[o], sl]).only_enforce_if(lit)
                        m.add_bool_or([~p[o], ~sl, lit])
                    m.add(x + dx >= 0).only_enforce_if(lit)
                    m.add(y + dy >= 0).only_enforce_if(lit)
                    m.add(x + dx + zw <= W).only_enforce_if(lit)
                    m.add(y + dy + zh <= H).only_enforce_if(lit)
                    zr.append((m.new_optional_fixed_size_interval_var(x + dx, zw, lit, ""),
                               m.new_optional_fixed_size_interval_var(y + dy, zh, lit, "")))
            zones.append(zr)
            self.x.append(x), self.y.append(y), self.p.append(p), self.rects.append(rects)
            self.real.append([size_at(it.w, it.d, r) for r in ROTS])
            self.ex.append(x + sum(sizes[o][0] * p[o] for o in range(4)))
            self.ey.append(y + sum(sizes[o][1] * p[o] for o in range(4)))
            self.grid0.append(self._grid_pos(it))
        all_items = [r for rs in self.rects for r in rs]

        # свободные зоны из пожеланий: прямоугольник у стены / в углу, только для предметов
        assumptions = []
        self.free = []
        for k, wsh in enumerate(w for w in wishes if w.kind == "free_zone"):
            f = m.new_bool_var(f"free{k}")
            fw, fd = math.ceil(wsh.w / GRID - EPS), math.ceil(wsh.d / GRID - EPS)
            fx, fy = m.new_int_var(0, W, ""), m.new_int_var(0, H, "")
            q = [m.new_bool_var(""), m.new_bool_var("")]
            m.add_exactly_one([q[0], q[1], ~f])
            szs = [(fw, fd), (fd, fw)]
            rs = [(m.new_optional_fixed_size_interval_var(fx, sx, q[o], ""),
                   m.new_optional_fixed_size_interval_var(fy, sy, q[o], "")) for o, (sx, sy) in enumerate(szs)]
            fex, fey = fx + szs[0][0] * q[0] + szs[1][0] * q[1], fy + szs[0][1] * q[0] + szs[1][1] * q[1]
            m.add(fex <= W), m.add(fey <= H)
            t = [m.new_bool_var("") for _ in range(4)]  # касается левой, верхней, правой, нижней стены
            m.add(fx == 0).only_enforce_if(t[0]), m.add(fy == 0).only_enforce_if(t[1])
            m.add(fex == W).only_enforce_if(t[2]), m.add(fey == H).only_enforce_if(t[3])
            if wsh.at == "wall":
                m.add_bool_or(t).only_enforce_if(f)
            else:
                c = [m.new_bool_var("") for _ in range(4)]
                for i in range(4):
                    m.add_bool_and([t[i], t[(i + 1) % 4]]).only_enforce_if(c[i])
                m.add_bool_or(c).only_enforce_if(f)
            all_items += rs
            self.free.append((fx, fy, fex, fey))
            assumptions.append((f, ("zone", wsh)))
        no_overlap(all_items)  # правила 1 и 6: предметы не пересекаются и не занимают свободные зоны

        # неподвижные препятствия — каждое в своём наборе (между собой они могут пересекаться)
        notch = notch_rect(room)
        walls_fixed = [fixed(notch)] if notch else []
        if notch:
            no_overlap(all_items + walls_fixed)
        walls_fixed += [fixed(radiator_body(room, e)) for e in plan.elements if e.kind == "radiator"]
        for e in plan.elements:
            sq = door_square(room, e)
            if sq:
                no_overlap([r for rs in self.rects for r in rs] + [fixed(sq)])  # правило 3
            if e.kind == "radiator":
                no_overlap([r for rs in self.rects for r in rs] + [fixed(radiator_keepout(room, e))])  # правило 5
            if e.kind in ("window", "radiator"):
                tall = [r for it, rs in zip(items, self.rects) if it.h > TALL for r in rs]
                if tall:
                    no_overlap(tall + [fixed(el_rect(room, e, STRIP))])
        # правило 2: зоны предмета j против остальных предметов, выреза и батарей
        for j, it in enumerate(items):
            if zones[j]:
                allow = CATALOG[it.type]["allow_in_zone"]
                others = [r for i, o in enumerate(items) if i != j and o.type not in allow for r in self.rects[i]]
                no_overlap(zones[j] + others + walls_fixed)

        # закрепления (pinned и keep) — assumptions, чтобы объяснить несовместимость
        keep = {w.item for w in wishes if w.kind == "keep"}
        self.pinned = {it.id for it in items if it.pinned or it.id in keep}
        for i, it in enumerate(items):
            if it.id in self.pinned:
                assumptions.append((self._stays(i, self.grid0[i]), ("pin", it)))
        self.assumptions = assumptions
        m.add_assumptions([a for a, _ in assumptions])

        # мягкое: пожелания, затем число перемещений; при равенстве — предметы спинкой к стене
        # (середина комнаты остаётся под проход, и проверок правила 4 нужно меньше)
        K = len(items) + 1
        cost = []
        for wsh in wishes:
            if wsh.kind not in ("free_zone", "keep"):
                sat = m.new_bool_var("")
                self._wish(wsh, sat)
                cost.append(K * K * (1 - sat))
        base = {it.id: it for it in base_items}
        for i, it in enumerate(items):
            if it.id in base:
                cost.append(K * (1 - self._stays(i, self._grid_pos(base[it.id]))))
            wall = m.new_bool_var("")
            m.add_bool_or([self.at(i, k) for k in range(len(self.walls))]).only_enforce_if(wall)
            cost.append(1 - wall)
            gx, gy, o = self.grid0[i]
            m.add_hint(self.x[i], gx), m.add_hint(self.y[i], gy)
            for oo in range(4):
                m.add_hint(self.p[i][oo], oo == o)
        m.minimize(sum(cost))

    def _stays(self, i, pos):
        """Литерал «предмет i стоит в клетке pos = (x, y, индекс поворота)»."""
        lit = self.m.new_bool_var("")
        self.m.add_implication(lit, self.p[i][pos[2]])
        self.m.add(self.x[i] == pos[0]).only_enforce_if(lit)
        self.m.add(self.y[i] == pos[1]).only_enforce_if(lit)
        return lit

    def _grid_pos(self, it):
        sx, sy = size_at(it.w, it.d, it.rot)
        return round((it.x - sx / 2) / GRID), round((it.y - sy / 2) / GRID), it.rot // 90

    def at(self, i, k):
        """Литерал «предмет i стоит спинкой к стене k» (как validator.wall_of)."""
        if (i, k) in self._at:
            return self._at[i, k]
        m, lit = self.m, self.m.new_bool_var("")
        nx, ny = wall_normal(self.plan.room, k)
        o = next(o for o in range(4) if side_dir("back", ROTS[o]) == (-nx, -ny))
        rx, ry = self.real[i][o]
        (px, py), (qx, qy) = self.walls[k]
        m.add_implication(lit, self.p[i][o])
        if ny:  # горизонтальная стена: зазор по y, перекрытие проекции по x
            c, v, rv, u, ru, a, b = py, self.y[i], ry, self.x[i], rx, min(px, qx), max(px, qx)
            s = ny
        else:
            c, v, rv, u, ru, a, b = px, self.x[i], rx, self.y[i], ry, min(py, qy), max(py, qy)
            s = nx
        if s > 0:
            m.add(v <= math.floor((c + SNAP) / GRID + EPS)).only_enforce_if(lit)
        else:
            m.add(v >= math.ceil((c - SNAP - rv) / GRID - EPS)).only_enforce_if(lit)
        m.add(u <= math.ceil(b / GRID - EPS) - 1).only_enforce_if(lit)
        m.add(u >= math.floor((a - ru) / GRID + EPS) + 1).only_enforce_if(lit)
        self._at[i, k] = lit
        return lit

    def _or(self, sat, conds):
        """sat ⇒ хотя бы одно из линейных условий (sat=None — всегда)."""
        lits = []
        for c in conds:
            lit = self.m.new_bool_var("")
            self.m.add(c).only_enforce_if(lit)
            lits.append(lit)
        ct = self.m.add_bool_or(lits)
        if sat is not None:
            ct.only_enforce_if(sat)

    def _wish(self, w, sat):
        m, ix = self.m, self.idx
        if w.kind == "near_wall":
            i = ix[w.item]
            if w.target == "any":
                m.add_bool_or([self.at(i, k) for k in range(len(self.walls))]).only_enforce_if(sat)
                return
            lits = []
            for e in self.plan.elements:
                if e.kind in EL_KINDS[w.target]:
                    r = el_rect(self.plan.room, e, 0)
                    lit = m.new_bool_var("")
                    m.add(self.x[i] <= math.floor((r[2] + NEAR_EL) / GRID + EPS)).only_enforce_if(lit)
                    m.add(self.ex[i] >= math.ceil((r[0] - NEAR_EL) / GRID - EPS)).only_enforce_if(lit)
                    m.add(self.y[i] <= math.floor((r[3] + NEAR_EL) / GRID + EPS)).only_enforce_if(lit)
                    m.add(self.ey[i] >= math.ceil((r[1] - NEAR_EL) / GRID - EPS)).only_enforce_if(lit)
                    lits.append(lit)
            m.add_bool_or(lits).only_enforce_if(sat)
        elif w.kind == "near":
            a, b, g = ix[w.a], ix[w.b], math.floor(w.max_cm / GRID + EPS)
            for c in (self.x[b] - self.ex[a] <= g, self.x[a] - self.ex[b] <= g,
                      self.y[b] - self.ey[a] <= g, self.y[a] - self.ey[b] <= g):
                m.add(c).only_enforce_if(sat)
        elif w.kind == "far_from":
            a, b, g = ix[w.a], ix[w.b], math.ceil(w.min_cm / GRID - EPS)
            self._or(sat, [self.x[b] - self.ex[a] >= g, self.x[a] - self.ex[b] >= g,
                           self.y[b] - self.ey[a] >= g, self.y[a] - self.ey[b] >= g])
        elif w.kind == "facing":  # центр b в полосе перед фронтом a (координаты ×2)
            a, b = ix[w.a], ix[w.b]
            cx, cy = self.x[b] + self.ex[b], self.y[b] + self.ey[b]
            for o in range(4):
                fx, fy = side_dir("front", ROTS[o])
                if fy:
                    conds = [cx >= 2 * self.x[a], cx <= 2 * self.ex[a],
                             cy >= 2 * self.ey[a] if fy > 0 else cy <= 2 * self.y[a]]
                else:
                    conds = [cy >= 2 * self.y[a], cy <= 2 * self.ey[a],
                             cx >= 2 * self.ex[a] if fx > 0 else cx <= 2 * self.x[a]]
                for c in conds:
                    m.add(c).only_enforce_if([sat, self.p[a][o]])
        elif w.kind == "hidden_from_entrance":
            i = ix[w.item]
            x0, y0, x1, y1 = _out(entrance_strip(self.plan))
            self._or(sat, [self.ex[i] <= x0, self.x[i] >= x1, self.ey[i] <= y0, self.y[i] >= y1])

    def moved_lits(self, i, sol, k):
        """Литералы «предмет i сдвинут на ≥ k клеток по x или y либо повёрнут» относительно sol."""
        gx, gy, o = sol[i]
        lits = [~self.p[i][o]]
        for v, c in ((self.x[i], gx), (self.y[i], gy)):
            for cond in (v >= c + k, v <= c - k):
                lit = self.m.new_bool_var("")
                self.m.add(cond).only_enforce_if(lit)
                lits.append(lit)
        return lits

    def decode(self, s):
        items, sol = [], []
        for i, it in enumerate(self.items):
            gx, gy = s.value(self.x[i]), s.value(self.y[i])
            o = next(o for o in range(4) if s.boolean_value(self.p[i][o]))
            sol.append((gx, gy, o))
            if (gx, gy, o) == self.grid0[i]:
                items.append(it)  # не сдвинут — точные координаты «как сейчас»
            else:
                rx, ry = self.real[i][o]
                items.append(it.model_copy(update={"x": gx * GRID + rx / 2, "y": gy * GRID + ry / 2,
                                                   "rot": ROTS[o]}))
        zones = [tuple(float(s.value(v) * GRID) for v in f) for f in self.free]
        return items, zones, sol

    def diversify(self, prev):
        """Новый вариант: ≥ 2 крупных предмета у другой стены или сдвинуты > 100 см (по центру, L∞)."""
        m, diffs = self.m, []
        for i, (it, pv) in enumerate(zip(self.items, prev)):
            if not CATALOG[it.type]["big"] or it.pinned:
                continue
            k0 = wall_of(self.plan.room, pv)
            lits = [self.at(i, k) for k in range(len(self.walls)) if k != k0]
            cx, cy = self.x[i] + self.ex[i], self.y[i] + self.ey[i]  # центр × 2 / GRID
            for v, c in ((cx, pv.x), (cy, pv.y)):
                for cond in (v >= math.floor((c + 100) * 2 / GRID + EPS) + 1,
                             v <= math.ceil((c - 100) * 2 / GRID - EPS) - 1):
                    lit = m.new_bool_var("")
                    m.add(cond).only_enforce_if(lit)
                    lits.append(lit)
            d = m.new_bool_var("")
            m.add_bool_or(lits).only_enforce_if(d)
            diffs.append(d)
        m.add(sum(diffs) >= 2)

    def _span(self, rect, iid, axis):
        """Начало и конец по оси: у предмета — выражения решателя, у стены — константы."""
        if iid is None:
            g = _out(rect)
            return g[axis], g[axis + 2]
        i = self.idx[iid]
        return (self.x[i], self.ex[i]) if axis == 0 else (self.y[i], self.ey[i])

    def _no_narrow_gap(self, pair):
        """Пара препятствий у узкого места больше не стоит друг напротив друга с зазором 5…55 см."""
        (ra, a), (rb, b) = pair
        gx, gy = gaps(ra, rb)
        if (gx > 0) == (gy > 0):
            return
        ax = 0 if gx > 0 else 1
        (a0, a1), (b0, b1) = self._span(ra, a, ax), self._span(rb, b, ax)
        (c0, c1), (d0, d1) = self._span(ra, a, 1 - ax), self._span(rb, b, 1 - ax)
        n = math.ceil(MIN_PASS / GRID - EPS)
        for lo, hi in ((a1, b0), (b1, a0)):
            self._or(None, [hi - lo <= 0, hi - lo >= n, c0 >= d1, d0 >= c1])

    def cut(self, cand, conflicts, sol):
        """Запретить решение. Проход: кто-то у узкого места (или владелец цели) сдвигается
        на нехватку или поворачивается; если там все закреплены — кто-то по краю области, куда от входа
        проходят 60 см. Дополнительно пара препятствий узкого места больше не образует узкую щель.
        Прочие конфликты — точный запрет по их предметам."""
        for p in passages(cand):
            if not passage_ok(p):
                short = max(GRID, MIN_PASS - min(p.gap, p.width))
                k = math.ceil(short / GRID - EPS)
                ids = [i for i in dict.fromkeys(([p.owner] if p.owner else []) + p.ids) if i not in self.pinned]
                ids = ids or [i for i in p.around if i not in self.pinned]
                self.m.add_bool_or([lit for i in ids for lit in self.moved_lits(self.idx[i], sol, k)])
                if p.pair and any(i is not None and i not in self.pinned for _, i in p.pair):
                    self._no_narrow_gap(p.pair)
        for c in conflicts:
            if c.rule != 4:
                ids = c.item_ids or [it.id for it in self.items]
                self.m.add_bool_or([lit for i in ids for lit in self.moved_lits(self.idx[i], sol, 1)])


def _solver(seconds, workers=8):
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = seconds
    s.parameters.num_workers = workers
    s.parameters.random_seed = 0
    return s


def _no_fit(plan: Plan) -> SolveResult:
    big = sorted(plan.items, key=lambda i: -i.w * i.d)[:3]
    names = ", ".join(f"«{i.label}» {i.w:g}×{i.d:g} см" for i in big)
    return SolveResult(reason=f"Решения нет: мебель с зонами обслуживания не помещается. Самые крупные предметы: "
                              f"{names}. Уберите один из них или уменьшите размеры.",
                       reason_item_ids=[i.id for i in big])


def _explain(M: _Model) -> SolveResult:
    s = _solver(VARIANT_SECONDS, workers=1)
    if s.solve(M.m) != cp_model.INFEASIBLE:
        return _no_fit(M.plan)
    core = set(s.sufficient_assumptions_for_infeasibility())
    used = [what for a, what in M.assumptions if a.index in core]
    if not used:
        return _no_fit(M.plan)
    nom, acc = [], []
    for kind, x in used:
        if kind == "pin":
            nom.append(f"закрепление «{x.label}»"), acc.append(f"закрепление «{x.label}»")
        else:
            where = "у стены" if x.at == "wall" else "в углу"
            nom.append(f"свободная зона {x.w:g}×{x.d:g} см {where}")
            acc.append(f"свободную зону {x.w:g}×{x.d:g} см {where}")
    if len(nom) == 1:
        text = f"Решения нет: {nom[0]} не оставляет места остальной мебели. Снимите {acc[0]}."
    else:
        text = (f"Решения нет: несовместимы {', '.join(nom[:-1])} и {nom[-1]}. "
                f"Снимите одно из них: {' или '.join(acc)}.")
    return SolveResult(reason=text, reason_item_ids=[x.id for k, x in used if k == "pin"])


def solve(plan: Plan, wishes, base_items=None, n=3) -> SolveResult:
    base_items = base_items or plan.items
    M = _Model(plan, wishes, base_items)
    variants = []
    while len(variants) < n:
        t0, found = time.monotonic(), None
        while not found and (left := VARIANT_SECONDS - (time.monotonic() - t0)) > 0.5:
            s = _solver(min(CALL_SECONDS, left - 0.4))
            st = s.solve(M.m)
            if st == cp_model.INFEASIBLE and not variants:
                return _explain(M)
            if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                break
            items, zones, sol = M.decode(s)
            cand = plan.model_copy(update={"items": items})
            conflicts = validate(cand, ref_items=plan.items, free_zones=zones)
            if conflicts:
                M.cut(cand, conflicts, sol)
            else:
                found = (cand, zones)
        if not found:
            break
        cand, zones = found
        variants.append(Variant(items=cand.items, free_zones=zones,
                                metrics=metrics(cand, wishes, zones, base_items),
                                seconds=round(time.monotonic() - t0, 2)))
        M.diversify(cand.items)
    if not variants:
        return _no_fit(plan)
    return SolveResult(variants=variants)
