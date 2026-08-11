"""Secure Plugin Contract helpers (eng-architect threat model §5, ADR-06/ADR-07).

Plugins MUST register routes and nav/blocks through these helpers rather
than touching `app.route` / `app._plugin_nav` / `app._plugin_blocks`
directly, so the security-relevant invariants (auth-mandatory routes,
app-relative nav URLs, allowlisted block content) hold by construction
instead of by plugin-author discipline.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from flask_login import login_required
from markupsafe import Markup

if TYPE_CHECKING:
    from flask import Flask

_log = logging.getLogger("pinsheet")


def plugin_route(app: "Flask", plugin_name: str, rule: str, **options):
    """Decorator factory that registers `rule` on `app`, force-wrapping the
    view function with `@login_required`.

    Closes T9 (High) / the "plugin route auth" gap: a plugin route
    registered by calling `app.route(...)` directly has no framework-level
    auth enforcement — it is entirely at the plugin author's discretion,
    which is a design-level trust-boundary gap (any plugin can ship an
    unauthenticated route by omission, not just by malice). Every stat
    plugin in this repo MUST use `plugin_route`, never `app.route`.

    Usage:
        @plugin_route(app, "my_plugin", "/my_plugin/page")
        def my_view():
            ...
    """
    endpoint = options.pop("endpoint", None)

    def decorator(view_func):
        wrapped = login_required(view_func)
        wrapped.__name__ = view_func.__name__
        ep = endpoint or f"plugin_{plugin_name}_{view_func.__name__}"
        app.add_url_rule(rule, endpoint=ep, view_func=wrapped, **options)
        return wrapped

    return decorator


def add_nav(app: "Flask", *, label: str, url: str, page_id: str) -> None:
    """Register a sidebar nav entry for a plugin.

    Closes T8 (Low/Medium): `item.url` is placed directly into an `href`
    attribute in base.html. HTML-entity escaping (Jinja autoescape) does
    NOT stop a `javascript:`-scheme URL or a protocol-relative `//evil`
    open-redirect. `url` MUST be an app-relative path beginning with a
    single `/` and containing no scheme.
    """
    if not isinstance(url, str) or not url.startswith("/") or url.startswith("//"):
        raise ValueError(f"add_nav: url must be an app-relative path starting with a single '/' (got {url!r})")
    if ":" in url.split("/", 1)[0]:
        raise ValueError(f"add_nav: url must not contain a scheme (got {url!r})")

    nav_list = getattr(app, "_plugin_nav", None)
    if nav_list is None:
        nav_list = []
        app._plugin_nav = nav_list
    nav_list.append({"label": label, "url": url, "page_id": page_id})


# T7 / VULN-05 mitigation: `plugin_blocks["head"/"foot"]` is a site-wide
# sink rendered on every page. base.html no longer marks it `|safe`, so a
# raw Python string assigned directly to `app._plugin_blocks[...]` is now
# HTML-escaped by Jinja's autoescaping by default (fails safe). This
# helper is the ONLY supported way to inject real (unescaped) markup, and
# it allowlists content to the two documented use cases — a stylesheet
# link or an external script tag pointing at the plugin's OWN static
# namespace — returning a `Markup` object so Jinja renders it unescaped.
# Inline script bodies, arbitrary tags, and references to another
# plugin's/the core app's static paths are rejected.
def _safe_block_pattern(plugin_name: str) -> re.Pattern:
    escaped = re.escape(plugin_name)
    href_src = rf'/plugins/{escaped}/static/[A-Za-z0-9_\-./]+'
    return re.compile(
        rf'^(?:<link rel="stylesheet" href="{href_src}"\s*/?>'
        rf'|<script src="{href_src}"></script>)$'
    )


def add_block(app: "Flask", plugin_name: str, slot: str, html: str) -> bool:
    """Append an allowlisted HTML fragment to `plugin_blocks[slot]`.

    Returns True if the fragment was accepted, False if it was rejected
    (rejection is logged, not raised, so a bad block doesn't abort the
    rest of `register()`).
    """
    if slot not in ("head", "foot"):
        _log.warning("plugin %s: add_block rejected unknown slot %r", plugin_name, slot)
        return False

    pattern = _safe_block_pattern(plugin_name)
    lines = [ln.strip() for ln in html.strip().splitlines() if ln.strip()]
    if not lines or not all(pattern.match(ln) for ln in lines):
        _log.warning(
            "plugin %s: add_block rejected content for slot %r — only <link rel=\"stylesheet\" "
            "href=\"/plugins/%s/static/...\"> and <script src=\"/plugins/%s/static/...\"></script> "
            "are permitted",
            plugin_name, slot, plugin_name, plugin_name,
        )
        return False

    blocks = getattr(app, "_plugin_blocks", None)
    if blocks is None:
        blocks = {}
        app._plugin_blocks = blocks
    existing = blocks.get(slot)
    combined = "\n".join(lines) if existing is None else f"{existing}\n" + "\n".join(lines)
    blocks[slot] = Markup(combined)
    return True
