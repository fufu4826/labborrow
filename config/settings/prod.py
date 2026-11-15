from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env, env_bool

if SECRET_KEY.startswith("dev-insecure") or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("Set a long random SECRET_KEY in .env for production (see deploy/DEPLOY.md).")

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "0"))
SECURE_CONTENT_TYPE_NOSNIFF = True
