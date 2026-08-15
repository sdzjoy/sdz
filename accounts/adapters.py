import base64
import hashlib

from allauth.idp.oidc.adapter import DefaultOIDCAdapter
from allauth.mfa.adapter import DefaultMFAAdapter
from cryptography.fernet import Fernet
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class EncryptedMFAAdapter(DefaultMFAAdapter):
    def _fernet(self):
        seed = settings.MFA_ENCRYPTION_KEY or settings.SECRET_KEY
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, text):
        return self._fernet().encrypt(text.encode("utf-8")).decode("ascii")

    def decrypt(self, encrypted_text):
        return self._fernet().decrypt(encrypted_text.encode("ascii")).decode("utf-8")


class SDZJOYOIDCAdapter(DefaultOIDCAdapter):
    scope_display = {
        **DefaultOIDCAdapter.scope_display,
        "membership": _("查看你的少惰主会员等级"),
    }

    def get_claims(self, purpose, user, client, scopes, **kwargs):
        claims = super().get_claims(purpose, user, client, scopes, **kwargs)
        if "profile" in scopes and user.display_name:
            claims["name"] = user.display_name
        if "membership" in scopes:
            claims["membership_level"] = user.membership_level
        return claims
