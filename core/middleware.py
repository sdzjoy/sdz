from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class CanonicalHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        redirect_host = settings.WWW_REDIRECT_HOST.lower()
        request_host = request.get_host().partition(":")[0].lower()
        if redirect_host and request_host == redirect_host:
            destination = f"{settings.PUBLIC_SITE_ORIGIN.rstrip('/')}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(destination, preserve_request=True)
        return self.get_response(request)
