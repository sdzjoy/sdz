from urllib.parse import urlencode

from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse


class StaffMFARequiredMiddleware:
    protected_prefixes = ("/cms/", "/django-admin/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(self.protected_prefixes):
            return self.get_response(request)

        user = request.user
        if not user.is_authenticated:
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{settings.LOGIN_URL}?{query}")
        if request.path.startswith("/cms/"):
            from studio.permissions import get_studio_role

            if not user.is_active or get_studio_role(user) is None:
                raise PermissionDenied
        elif not user.is_active or not user.is_staff:
            raise PermissionDenied
        if not get_mfa_adapter().is_mfa_enabled(user):
            messages.error(request, "管理后台要求先启用通行密钥或动态验证码。")
            return redirect(reverse("mfa_index"))
        return self.get_response(request)


class PrivateResponseMiddleware:
    private_prefixes = (
        "/account/",
        "/identity/",
        "/resources/",
        "/search/",
        "/cms/",
        "/django-admin/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.private_prefixes):
            response["Cache-Control"] = "private, no-store"
            response["Pragma"] = "no-cache"
            vary = {item.strip() for item in response.get("Vary", "").split(",") if item}
            vary.add("Cookie")
            response["Vary"] = ", ".join(sorted(vary))
        return response
