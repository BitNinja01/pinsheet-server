from flask import g
from flask_login import current_user
import store


def get_settings():
    if not hasattr(g, '_settings'):
        g._settings = store.load_settings(current_user.id)
    return g._settings


def get_courses():
    if not hasattr(g, '_courses'):
        g._courses = store.get_courses()
    return g._courses


def get_all_rounds_for_user():
    if not hasattr(g, '_all_rounds'):
        g._all_rounds = store.get_all_rounds(current_user.id)
    return g._all_rounds


def get_users():
    if not hasattr(g, '_users'):
        g._users = store.get_users()
    return g._users


def _fmt(val, suffix="", precision=1):
    if val is None:
        return "\u2014"
    if suffix == "%":
        return f"{val:.{precision}f}%"
    return f"{val:.{precision}f}{suffix}"


def base_context(**extra):
    ctx = {"settings": get_settings(), "all_users": get_users(), "_fmt": _fmt}
    ctx.update(extra)
    return ctx
