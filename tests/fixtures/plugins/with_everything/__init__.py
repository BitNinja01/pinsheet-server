plugin_info = {
    "name": "with_everything",
    "version": "2.0.0",
    "description": "Has templates and static files.",
    "author": "Test Author",
}

def register(app):
    app.config["plugins.with_everything"] = "loaded"

def unregister(app):
    app.config.pop("plugins.with_everything", None)
