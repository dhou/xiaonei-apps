from django.core.urlresolvers import reverse
import settings

def reverse_xn(viewname, app_url, urlconf=None, args=None, kwargs=None):
    """
    Returns the reversed url for the app
    """
    return app_url + reverse(viewname, urlconf, args, kwargs).replace(getattr(settings, "XIAONEI_CALLBACK_PATH", ""), '')