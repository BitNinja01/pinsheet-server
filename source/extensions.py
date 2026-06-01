from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect


def init_app(app):
    limiter = Limiter(get_remote_address, app=app, default_limits=[])
    csrf = CSRFProtect(app)
    return limiter, csrf
