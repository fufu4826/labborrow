# WSGI file for PythonAnywhere. Copy over /var/www/<user>_pythonanywhere_com_wsgi.py:
#   cp ~/labborrow/deploy/pythonanywhere_wsgi.py /var/www/${USER}_pythonanywhere_com_wsgi.py
import os
import sys

path = os.path.expanduser("~/labborrow")
if path not in sys.path:
    sys.path.insert(0, path)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
