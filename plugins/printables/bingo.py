"""SVG bingo card generation for the printables plugin."""
from __future__ import annotations

from pathlib import Path

import svgwrite

PAGE_W = 306.0
PAGE_H = 1008.0
MARGIN = 18.0

FONT_FAMILY = "JetBrainsMonoNL NFM, JetBrainsMono, monospace"
FONT_WEIGHT = "900"

TABLE_TOP = 18.0
CORNER_RADIUS = 4.0

COLS = 3
ROWS = 6
NUM_CELLS = COLS * ROWS

CONTENT_H = PAGE_H / 2 - TABLE_TOP
CONTENT_W = PAGE_W - 2 * MARGIN
CELL_W = CONTENT_W / COLS
TITLE_H = 24.0
SEASON_Y = CONTENT_H - 32.0
INSTR_Y = CONTENT_H - 14.0
CELL_H = (SEASON_Y - TABLE_TOP - TITLE_H - 6) / ROWS


def _col_x(col: int, dx: float = 0.0) -> float:
    return MARGIN + col * CELL_W + dx


def _row_y(row: int, dy: float = 0.0) -> float:
    return TABLE_TOP + TITLE_H + 6 + row * CELL_H + dy


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


def _render_bingo_half(dwg: svgwrite.Drawing, dy: float, dx: float = 0.0) -> None:
    grid_w = COLS * CELL_W
    grid_h = ROWS * CELL_H
    grid_x = MARGIN + dx
    grid_y = _row_y(0, dy)

    for ri in range(ROWS + 1):
        y = _row_y(ri, dy)
        sw = 1.0 if ri in (0, ROWS) else 0.5
        dwg.add(
            dwg.line(
                start=(grid_x, y),
                end=(grid_x + grid_w, y),
                stroke=svgwrite.rgb(0, 0, 0),
                stroke_width=sw,
            )
        )

    for ci in range(COLS + 1):
        x = _col_x(ci, dx)
        sw = 1.0 if ci in (0, COLS) else 0.5
        dwg.add(
            dwg.line(
                start=(x, _row_y(0, dy)),
                end=(x, _row_y(ROWS, dy)),
                stroke=svgwrite.rgb(0, 0, 0),
                stroke_width=sw,
            )
        )

    dwg.add(
        dwg.rect(
            insert=(grid_x, grid_y),
            size=(grid_w, grid_h),
            rx=CORNER_RADIUS,
            ry=CORNER_RADIUS,
            fill="none",
            stroke=svgwrite.rgb(0, 0, 0),
            stroke_width=1.0,
        )
    )

    dwg.add(
        dwg.text(
            "PAR BINGO",
            insert=(MARGIN + dx + CONTENT_W / 2, TABLE_TOP + 0 + dy + TITLE_H - 6),
            text_anchor="middle",
            font_family=FONT_FAMILY,
            font_size=12,
            font_weight=FONT_WEIGHT,
        )
    )

    for cell in range(NUM_CELLS):
        hole = cell + 1
        col = cell % COLS
        row = cell // COLS
        cx = _col_x(col, dx) + CELL_W / 2
        cy = _row_y(row, dy)

        dwg.add(
            dwg.text(
                str(hole),
                insert=(cx, cy + 25),
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=20,
                font_weight=FONT_WEIGHT,
            )
        )

        dwg.add(
            dwg.text(
                "PAR",
                insert=(cx, cy + 41),
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=9,
                font_weight=FONT_WEIGHT,
            )
        )

        dwg.add(
            dwg.text(
                "BIRDIE",
                insert=(cx, cy + 53),
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=9,
                font_weight=FONT_WEIGHT,
            )
        )

    season_y = TABLE_TOP + dy + SEASON_Y
    dwg.add(
        dwg.text(
            "Season:",
            insert=(MARGIN + 6 + dx, season_y),
            font_family=FONT_FAMILY,
            font_size=10,
            font_weight=FONT_WEIGHT,
        )
    )
    dwg.add(
        dwg.line(
            start=(MARGIN + 64 + dx, season_y + 1),
            end=(MARGIN + dx + CONTENT_W, season_y + 1),
            stroke=svgwrite.rgb(0, 0, 0),
            stroke_width=0.5,
        )
    )

    instr_y = TABLE_TOP + dy + INSTR_Y
    dwg.add(
        dwg.text(
            "Cross off each as you earn it.",
            insert=(MARGIN + 6 + dx, instr_y),
            font_family=FONT_FAMILY,
            font_size=9,
            font_weight=FONT_WEIGHT,
        )
    )

    _draw_corner_marks(dwg, MARGIN + dx, TABLE_TOP + dy, CONTENT_W, CONTENT_H)


def build_bingo_svg() -> str:
    dwg = svgwrite.Drawing(
        size=(f"{PAGE_W}pt", f"{PAGE_H}pt"),
        viewBox=f"0 0 {PAGE_W} {PAGE_H}",
    )
    _render_bingo_half(dwg, 0.0)
    _render_bingo_half(dwg, PAGE_H / 2 - TABLE_TOP)
    return dwg.tostring()


def build_bingo_letter_svg() -> str:
    dwg = svgwrite.Drawing(
        size=("612pt", "792pt"),
        viewBox="0 0 612 792",
    )
    _render_bingo_half(dwg, 0.0, 0.0)
    _render_bingo_half(dwg, 0.0, 306.0)
    return dwg.tostring()


def generate_bingo_pdf(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    svg = build_bingo_svg()
    import cairosvg
    narrow_pdf = cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))

    from io import BytesIO
    from pypdf import PdfWriter, PdfReader, Transformation

    narrow_page = PdfReader(BytesIO(narrow_pdf)).pages[0]

    single_path = output_dir / "bingo.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(612, 1008)
    page.merge_transformed_page(narrow_page, Transformation().translate(0, 0))
    page.merge_transformed_page(narrow_page, Transformation().translate(PAGE_W, 0))
    with open(single_path, "wb") as f:
        writer.write(f)

    double_path = output_dir / "bingo_double.pdf"
    writer2 = PdfWriter()
    for _ in range(2):
        page2 = writer2.add_blank_page(612, 1008)
        page2.merge_transformed_page(narrow_page, Transformation().translate(0, 0))
        page2.merge_transformed_page(narrow_page, Transformation().translate(PAGE_W, 0))
    with open(double_path, "wb") as f:
        writer2.write(f)

    return single_path


def generate_bingo_letter_pdf(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    svg = build_bingo_letter_svg()
    import cairosvg
    pdf_bytes = cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))
    path = output_dir / "bingo_letter.pdf"
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    return path
