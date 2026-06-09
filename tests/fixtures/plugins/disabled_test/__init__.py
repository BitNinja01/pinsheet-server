plugin_info = {"name": "disabled_test", "version": "1.0.0"}

def register(app):
    app.config["plugins.disabled_test"] = "loaded"

def unregister(app):
    app.config.pop("plugins.disabled_test", None)
