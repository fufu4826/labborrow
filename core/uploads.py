"""Storage names for uploaded files.

Uploads are saved under a random ASCII name (`<folder>/<32 hex>.<ext>`) instead of the user's file name:
Thai or other non-ASCII names are not served by some static file servers (PythonAnywhere returns 404),
and the original name may leak personal information.
"""
import os
import re
import uuid

from django.utils.deconstruct import deconstructible

_EXT = re.compile(r"^\.[a-z0-9]{1,5}$")


@deconstructible
class RandomName:
    def __init__(self, folder):
        self.folder = folder.strip("/")

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower()
        if not _EXT.match(ext):
            ext = ".jpg"
        return f"{self.folder}/{uuid.uuid4().hex}{ext}"

    def __eq__(self, other):
        return isinstance(other, RandomName) and other.folder == self.folder
