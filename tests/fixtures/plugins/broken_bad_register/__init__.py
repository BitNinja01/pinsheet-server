plugin_info = {"name": "bad_register", "version": "0.0.0"}

def register(app):
    raise RuntimeError("boom")

def unregister(app):
    pass
