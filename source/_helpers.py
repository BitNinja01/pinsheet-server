from functools import wraps
from flask import g


def _make_chart_data(hi_values):
    chart = {"path": "", "area": "", "points": [], "label_x": "", "label_y": "", "label_v": ""}
    if len(hi_values) < 2:
        return chart
    lo, hi = min(hi_values) - 1.0, max(hi_values) + 1.0
    ml, mr, mt, mb = 36, 16, 22, 30
    cw, ch = 1000 - ml - mr, 230 - mt - mb
    n = len(hi_values) - 1
    pts = []
    for i, v in enumerate(hi_values):
        pts.append((ml + (i / n) * cw, mt + (1 - (v - lo) / (hi - lo)) * ch, v))
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}" for i, (x, y, _) in enumerate(pts))
    bx, by = pts[-1][0], mt + ch
    return {
        "path": path,
        "area": f"{path} L{bx:.1f} {by:.1f} L{pts[0][0]:.1f} {by:.1f} Z",
        "points": [{"x": f"{x:.1f}", "y": f"{y:.1f}", "v": f"{v:.1f}"} for x, y, v in pts],
        "label_x": f"{pts[-1][0] - 8:.1f}",
        "label_y": f"{pts[-1][1] - 12:.1f}",
        "label_v": f"{pts[-1][2]:.1f}",
    }


def sparkline_svg(holes_raw, sp_w=210, sp_h=28, sp_pad=2):
    if not holes_raw:
        return None
    sorted_nums = sorted(holes_raw.keys(), key=lambda x: int(x))
    scores = []
    for hn in sorted_nums:
        gv = holes_raw[hn].gross
        if gv:
            scores.append(int(gv))
    if len(scores) < 2:
        return None
    lo, hi = min(scores), max(scores)
    rng = hi - lo if hi != lo else 1
    iw = sp_w - sp_pad * 2
    ih = sp_h - sp_pad * 2
    n = len(scores) - 1
    pts = []
    for j, s in enumerate(scores):
        pts.append((
            sp_pad + (j / n) * iw,
            sp_pad + (1 - (s - lo) / rng) * ih,
        ))
    path = " ".join(
        f"{'M' if j == 0 else 'L'}{x:.1f} {y:.1f}"
        for j, (x, y) in enumerate(pts)
    )
    fx, fy = pts[-1]
    return {
        "path": path,
        "final_x": f"{fx:.1f}",
        "final_y": f"{fy:.1f}",
    }


def per_round_hole_stats(holes, course_holes_data):
    fir_hit = fir_attempts = 0
    gir_hit = gir_total = 0
    scr_updown = scr_opps = 0
    total_putts = 0
    for hn, h in holes.items():
        fw = h.fairway
        if fw and fw != "N":
            fir_attempts += 1
            if fw == "H":
                fir_hit += 1
        gi = h.gir
        if gi:
            gir_total += 1
            if gi == "H":
                gir_hit += 1
            if gi != "H":
                scr_opps += 1
                try:
                    hole_par = int(course_holes_data.get(hn, {}).get("par", 99))
                    if h.gross <= hole_par:
                        scr_updown += 1
                except (ValueError, TypeError):
                    pass
        try:
            total_putts += h.putts
        except (ValueError, TypeError):
            pass
    return {
        "fir_display": f"{fir_hit}/{fir_attempts}" if fir_attempts > 0 else None,
        "gir_display": f"{gir_hit}/{gir_total}" if gir_total > 0 else None,
        "scr_display": f"{scr_updown}/{scr_opps}" if scr_opps > 0 else None,
        "total_putts": total_putts,
    }


def stat_delta(current, previous, higher_better=False, precision=1, suffix=""):
    if current is None or previous is None or current == previous:
        return "", "\u2014", ""
    raw = current - previous
    is_up = (raw > 0 and higher_better) or (raw < 0 and not higher_better)
    cls = "is-up" if is_up else "is-down"
    cell_cls = "is-improved" if is_up else "is-declined"
    text = f"{raw:+.{precision}f}{suffix} vs L20"
    return cls, text, cell_cls


def requires_own_data(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.is_own_data:
            return "Forbidden", 403
        return f(*args, **kwargs)
    return decorated
