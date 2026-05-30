from flask import render_template, request, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user

from store import verify_user, get_user, real_user_count, create_user, is_invite_code_valid, consume_invite_code


def register_auth_routes(app, limiter, User):
    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("5 per minute")
    def login_page():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            remember = request.form.get("remember") == "on"

            user_dict = verify_user(username, password)
            if user_dict:
                user = User(user_dict)
                login_user(user, remember=remember)
                next_page = request.args.get("next")
                if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                    return redirect(next_page)
                return redirect(url_for("dashboard"))

            return render_template("login.html", error="Invalid username or password")

        return render_template("login.html", error=None)

    @app.route("/register", methods=["GET", "POST"])
    @limiter.limit("5 per minute")
    def register_page():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        invite_code = request.args.get("code", "")
        first_run = real_user_count() == 0

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            display_name = request.form.get("display_name", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")
            code = request.form.get("code", "").strip().upper()

            errors = []
            if len(username) < 3 or len(username) > 30 or not all(c.isalnum() or c == "_" for c in username):
                errors.append("Username must be 3-30 characters (letters, numbers, underscores).")
            if not display_name or len(display_name) > 50:
                errors.append("Display name is required (max 50 characters).")
            if len(password) < 8:
                errors.append("Password must be at least 8 characters.")
            if password != confirm:
                errors.append("Passwords do not match.")
            if get_user(username):
                errors.append("Username is already taken.")

            if not first_run:
                if not code or not is_invite_code_valid(code):
                    errors.append("Invalid or expired invite code.")

            if errors:
                return render_template("register.html", errors=errors, code=code, first_run=first_run)

            user_dict = create_user(username, display_name, password)
            if not first_run:
                consume_invite_code(code, user_dict["id"])

            user = User(user_dict)
            login_user(user)
            return redirect(url_for("dashboard"))

        return render_template("register.html", errors=None, code=invite_code, first_run=first_run)

    @app.route("/logout")
    def logout():
        logout_user()
        return redirect(url_for("login_page"))
