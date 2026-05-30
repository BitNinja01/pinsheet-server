from functools import wraps
from flask import g


def _last_n_rounds(all_rounds, courses, n: int) -> list:
    return [r for r in all_rounds[:n] if not r.get("excluded")]


def _best_n_rounds(all_rounds, courses, n: int) -> list:
    eligible = [r for r in all_rounds if not r.get("excluded") and r.get("differential") and r["differential"] != "0"]
    eligible.sort(key=lambda r: float(r["differential"]))
    return eligible[:min(n, len(eligible))]


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


def requires_own_data(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.is_own_data:
            return "Forbidden", 403
        return f(*args, **kwargs)
    return decorated
