from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import AccountRequest, MembershipChange, User
from .services import change_membership_level


@admin.register(User)
class SDZUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = (
        "email",
        "display_name",
        "membership_level",
        "email_verified_at",
        "is_active",
        "is_staff",
    )
    search_fields = ("email", "display_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {"fields": ("display_name", "first_name", "last_name", "email_verified_at")},
        ),
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

    def save_model(self, request, obj, form, change):
        requested_level = obj.membership_level
        original_level = None
        if change:
            original_level = User.objects.only("membership_level").get(
                pk=obj.pk
            ).membership_level
            obj.membership_level = original_level
        super().save_model(request, obj, form, change)
        if original_level and requested_level != original_level:
            change_membership_level(
                user=obj,
                to_level=requested_level,
                reason="管理员通过账号后台调整。",
                actor=request.user,
            )


@admin.register(MembershipChange)
class MembershipChangeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "from_level",
        "to_level",
        "reason",
        "changed_by",
        "created_at",
    )
    list_filter = ("from_level", "to_level", "created_at")
    search_fields = ("user__email", "reason", "changed_by__email")
    readonly_fields = (
        "user",
        "from_level",
        "to_level",
        "reason",
        "changed_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AccountRequest)
class AccountRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "request_type", "status", "requested_at", "processed_at")
    list_filter = ("request_type", "status", "requested_at")
    search_fields = ("user__email", "note", "resolution_note")
    readonly_fields = (
        "user",
        "request_type",
        "note",
        "requested_at",
        "processed_at",
        "processed_by",
    )

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if obj.status == AccountRequest.Status.PENDING:
            obj.processed_at = None
            obj.processed_by = None
        elif obj.processed_at is None:
            obj.processed_at = timezone.now()
            obj.processed_by = request.user
        super().save_model(request, obj, form, change)
