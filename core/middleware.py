from django.conf import settings
from django.utils import translation


class UserLanguageMiddleware:
    """Pick the page language (FR-14). Thai is the default for everyone.

    1. logged-in user -> the language saved on the user (default "th")
    2. anonymous visitor who used the language switch -> that choice (language cookie)
    3. otherwise -> settings.LANGUAGE_CODE ("th"); the browser's Accept-Language is ignored
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        supported = dict(settings.LANGUAGES)
        if user is not None and user.is_authenticated and user.language in supported:
            lang = user.language
        else:
            lang = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
            if lang not in supported:
                lang = settings.LANGUAGE_CODE
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
        return self.get_response(request)
