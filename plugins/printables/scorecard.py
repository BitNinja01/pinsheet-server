"""SVG scorecard generation for the printables plugin."""
from __future__ import annotations

from pathlib import Path

import svgwrite

PAGE_W = 306.0
PAGE_H = 1008.0
MARGIN = 18.0
FONT_FAMILY = "JetBrainsMonoNL NFM, JetBrainsMono, monospace"
FONT_WEIGHT = "900"

HEADERS = ["Hole", "Score", "FW", "GIR", "Putts", "Pen"]
NUM_ROWS = 18
SUMMARY_ROWS = ["OUT", "IN", "TOT"]

TABLE_TOP = 18.0
CORNER_RADIUS = 4.0
ROW_H = (PAGE_H / 2 - TABLE_TOP - 35 - 108) / (1 + NUM_ROWS + len(SUMMARY_ROWS))
COL_WIDTHS = [30, 48, 48, 48, 48, 48]
COL_STARTS: list[float] = []
x = MARGIN
for w in COL_WIDTHS:
    COL_STARTS.append(x)
    x += w
TABLE_W = x - MARGIN


def _col_x(col_index: int, dx: float = 0.0) -> float:
    return COL_STARTS[col_index] + dx


def _row_y(row_index: int, dy: float = 0.0) -> float:
    return TABLE_TOP + row_index * ROW_H + dy


def _draw_corner_marks(
    dwg: svgwrite.Drawing,
    x: float,
    y: float,
    w: float,
    h: float,
    arm: float = 8.0,
) -> None:
    s = {"stroke": svgwrite.rgb(0, 0, 0), "stroke_width": 0.5, "stroke_linecap": "square"}
    dwg.add(dwg.line(start=(x, y), end=(x + arm, y), **s))
    dwg.add(dwg.line(start=(x, y), end=(x, y + arm), **s))
    dwg.add(dwg.line(start=(x + w, y), end=(x + w - arm, y), **s))
    dwg.add(dwg.line(start=(x + w, y), end=(x + w, y + arm), **s))
    dwg.add(dwg.line(start=(x, y + h), end=(x + arm, y + h), **s))
    dwg.add(dwg.line(start=(x, y + h), end=(x, y + h - arm), **s))
    dwg.add(dwg.line(start=(x + w, y + h), end=(x + w - arm, y + h), **s))
    dwg.add(dwg.line(start=(x + w, y + h), end=(x + w, y + h - arm), **s))


def _render_half(dwg: svgwrite.Drawing, dy: float, dx: float = 0.0) -> None:
    num_cols = len(COL_WIDTHS)
    num_data_rows = 1 + NUM_ROWS + len(SUMMARY_ROWS)
    table_h = num_data_rows * ROW_H

    for ci in range(1, num_cols):
        x_pos = _col_x(ci, dx)
        dwg.add(
            dwg.line(
                start=(x_pos, _row_y(0, dy)),
                end=(x_pos, _row_y(num_data_rows, dy)),
                stroke=svgwrite.rgb(0, 0, 0),
                stroke_width=0.5,
            )
        )

    for ri in range(1, num_data_rows):
        y_pos = _row_y(ri, dy)
        is_boundary = ri in (1, 10, 11, 20)
        sw = 1.0 if is_boundary else 0.3
        dwg.add(
            dwg.line(
                start=(MARGIN + dx, y_pos),
                end=(MARGIN + TABLE_W + dx, y_pos),
                stroke=svgwrite.rgb(0, 0, 0),
                stroke_width=sw,
            )
        )

    dwg.add(
        dwg.rect(
            insert=(MARGIN + dx, _row_y(0, dy)),
            size=(TABLE_W, table_h),
            rx=CORNER_RADIUS,
            ry=CORNER_RADIUS,
            fill="none",
            stroke=svgwrite.rgb(0, 0, 0),
            stroke_width=1.0,
        )
    )

    for ci, header in enumerate(HEADERS):
        x_center = _col_x(ci, dx) + COL_WIDTHS[ci] / 2
        dwg.add(
            dwg.text(
                header,
                insert=(x_center, _row_y(0, dy) + ROW_H - 4),
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=10,
                font_weight=FONT_WEIGHT,
            )
        )

    for hi in range(9):
        hole_num = hi + 1
        dwg.add(
            dwg.text(
                str(hole_num),
                insert=(_col_x(0, dx) + COL_WIDTHS[0] / 2, _row_y(1 + hi, dy) + ROW_H - 4),
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=9,
                font_weight=FONT_WEIGHT,
            )
        )

    dwg.add(
        dwg.text(
            "OUT",
            insert=(_col_x(0, dx) + COL_WIDTHS[0] / 2, _row_y(10, dy) + ROW_H - 4),
            text_anchor="middle",
            font_family=FONT_FAMILY,
            font_size=9,
            font_weight=FONT_WEIGHT,
        )
    )

    for hi in range(9, 18):
        hole_num = hi + 1
        dwg.add(
            dwg.text(
                str(hole_num),
                insert=(_col_x(0, dx) + COL_WIDTHS[0] / 2, _row_y(2 + hi, dy) + ROW_H - 4),
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=9,
                font_weight=FONT_WEIGHT,
            )
        )

    for si, label in enumerate(["IN", "TOT"]):
        dwg.add(
            dwg.text(
                label,
                insert=(_col_x(0, dx) + COL_WIDTHS[0] / 2, _row_y(20 + si, dy) + ROW_H - 4),
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=9,
                font_weight=FONT_WEIGHT,
            )
        )

    for row in (10, 20, 21):
        for ci in (2, 3, 4, 5):
            cx = _col_x(ci, dx) + COL_WIDTHS[ci] / 2
            cy = _row_y(row, dy) + ROW_H / 2
            s = 3.5
            dwg.add(
                dwg.line(
                    start=(cx - s, cy - s), end=(cx + s, cy + s),
                    stroke=svgwrite.rgb(0, 0, 0), stroke_width=0.5,
                )
            )
            dwg.add(
                dwg.line(
                    start=(cx - s, cy + s), end=(cx + s, cy - s),
                    stroke=svgwrite.rgb(0, 0, 0), stroke_width=0.5,
                )
            )

    table_bottom = _row_y(num_data_rows, dy)
    header_y = table_bottom + 16
    line_end = MARGIN + TABLE_W + dx
    dwg.add(
        dwg.text(
            "Course:",
            insert=(MARGIN + 6 + dx, header_y),
            font_family=FONT_FAMILY,
            font_size=10,
            font_weight=FONT_WEIGHT,
        )
    )
    dwg.add(
        dwg.line(
            start=(MARGIN + 58 + dx, header_y + 1),
            end=(line_end, header_y + 1),
            stroke=svgwrite.rgb(0, 0, 0),
            stroke_width=0.5,
        )
    )
    dwg.add(
        dwg.text(
            "Date:",
            insert=(MARGIN + 6 + dx, header_y + 18),
            font_family=FONT_FAMILY,
            font_size=10,
            font_weight=FONT_WEIGHT,
        )
    )
    dwg.add(
        dwg.line(
            start=(MARGIN + 44 + dx, header_y + 18 + 1),
            end=(line_end, header_y + 18 + 1),
            stroke=svgwrite.rgb(0, 0, 0),
            stroke_width=0.5,
        )
    )

    _draw_corner_marks(dwg, MARGIN + dx, _row_y(0, dy), TABLE_W, PAGE_H / 2 - TABLE_TOP)


def build_scorecard_svg() -> str:
    dwg = svgwrite.Drawing(
        size=(f"{PAGE_W}pt", f"{PAGE_H}pt"),
        viewBox=f"0 0 {PAGE_W} {PAGE_H}",
    )
    _render_half(dwg, 0.0)
    _render_half(dwg, PAGE_H / 2 - TABLE_TOP)
    return dwg.tostring()


def build_scorecard_letter_svg() -> str:
    dwg = svgwrite.Drawing(
        size=("612pt", "792pt"),
        viewBox="0 0 612 792",
    )
    _render_half(dwg, 0.0, 0.0)
    _render_half(dwg, 0.0, 306.0)
    return dwg.tostring()


def generate_scorecard_letter_pdf(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    svg = build_scorecard_letter_svg()
    import cairosvg
    pdf_bytes = cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))
    path = output_dir / "scorecard_shorthand_letter.pdf"
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    return path


def generate_scorecard_pdf(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    svg = build_scorecard_svg()
    import cairosvg
    narrow_pdf = cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))

    from io import BytesIO
    from pypdf import PdfWriter, PdfReader, Transformation

    narrow_page = PdfReader(BytesIO(narrow_pdf)).pages[0]

    single_path = output_dir / "scorecard_shorthand_single.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(612, 1008)
    page.merge_transformed_page(narrow_page, Transformation().translate(0, 0))
    page.merge_transformed_page(narrow_page, Transformation().translate(PAGE_W, 0))
    with open(single_path, "wb") as f:
        writer.write(f)

    double_path = output_dir / "scorecard_shorthand_double.pdf"
    writer2 = PdfWriter()
    for _ in range(2):
        page2 = writer2.add_blank_page(612, 1008)
        page2.merge_transformed_page(narrow_page, Transformation().translate(0, 0))
        page2.merge_transformed_page(narrow_page, Transformation().translate(PAGE_W, 0))
    with open(double_path, "wb") as f:
        writer2.write(f)

    return single_path
