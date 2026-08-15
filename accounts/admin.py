from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class SDZUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "display_name", "membership_level", "is_active", "is_staff")
    search_fields = ("email", "display_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("display_name", "first_name", "last_name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "membership_level",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "display_name",
                    "membership_level",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
