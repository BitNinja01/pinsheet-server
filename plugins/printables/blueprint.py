"""Printables Blueprint — routes for viewing and downloading printable PDFs."""

from __future__ import annotations

import shutil
from pathlib import Path

from flask import (
    Blueprint, current_app, jsonify, render_template,
    send_from_directory, g,
)
from flask_login import current_user, login_required

bp = Blueprint("printables", __name__, template_folder="templates")


@bp.route("/")
@login_required
def printables_page():
    view_user = getattr(g, "view_user", None)
    if view_user is None:
        return "No user", 400

    output_dir = Path(current_app.config["DATA_DIR"]) / "plugins" / "printables"
    pdfs = []
    for name in [
        "scorecard_shorthand.pdf",
        "scorecard_shorthand_letter.pdf",
        "bingo.pdf",
        "bingo_letter.pdf",
    ]:
        path = output_dir / name
        pdfs.append({
            "name": name,
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
        })

    return render_template(
        "printables.html",
        pdfs=pdfs,
        is_admin=current_user.is_admin,
        current_page="printables",
    )


@bp.route("/download/<name>")
@login_required
def download_pdf(name):
    output_dir = Path(current_app.config["DATA_DIR"]) / "plugins" / "printables"
    return send_from_directory(str(output_dir), name)


@bp.route("/regenerate", methods=["POST"])
@login_required
def regenerate():
    if not current_user.is_admin:
        return jsonify({"error": "admin only"}), 403

    from . import generate_pdfs

    output_dir = Path(current_app.config["DATA_DIR"]) / "plugins" / "printables"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    try:
        generate_pdfs(output_dir)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
