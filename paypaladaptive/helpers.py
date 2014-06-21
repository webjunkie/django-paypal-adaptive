from django.conf import settings


def get_http_protocol():
    return getattr(settings, 'DEFAULT_HTTP_PROTOCOL', 'http')
