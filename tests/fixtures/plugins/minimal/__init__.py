plugin_info = {"name": "minimal", "version": "1.0.0"}

def register(app):
    app.config["plugins.minimal"] = "loaded"

def unregister(app):
    del app.config["plugins.minimal"]
