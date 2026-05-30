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


def make_chart_data(hi_values):
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
