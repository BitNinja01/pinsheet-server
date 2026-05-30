from flask import g

from store import load_settings, get_courses, get_all_rounds


def get_settings():
    if not hasattr(g, '_settings'):
        g._settings = load_settings(g.view_user["id"])
    return g._settings


def get_courses():
    if not hasattr(g, '_courses'):
        g._courses = get_courses()
    return g._courses


def get_all_rounds_for_user():
    if not hasattr(g, '_all_rounds'):
        g._all_rounds = get_all_rounds(g.view_user["id"])
    return g._all_rounds
