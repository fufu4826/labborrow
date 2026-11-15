from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = False
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIA_ROOT = BASE_DIR / ".test_media"
LINE_CHANNEL_SECRET = "test-secret"
LINE_CHANNEL_ACCESS_TOKEN = ""
LANGUAGE_CODE = "en"
