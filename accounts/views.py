from allauth.account.decorators import reauthentication_required, verified_email_required
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AccountRequest


@verified_email_required
def account_center(request):
    return render(
        request,
        "accounts/account_center.html",
        {"account_requests": request.user.account_requests.all()[:10]},
    )


@require_POST
@verified_email_required
@reauthentication_required
def export_account_data(request):
    user = request.user
    account_request = AccountRequest.objects.create(
        user=user,
        request_type=AccountRequest.RequestType.EXPORT,
        status=AccountRequest.Status.COMPLETED,
        processed_at=timezone.now(),
        processed_by=user,
        resolution_note="由用户完成强验证后即时导出。",
    )
    payload = {
        "generated_at": timezone.now().isoformat(),
        "request_id": account_request.pk,
        "account": {
            "email": user.email,
            "display_name": user.display_name,
            "membership_level": user.membership_level,
            "email_verified_at": (
                user.email_verified_at.isoformat() if user.email_verified_at else None
            ),
            "date_joined": user.date_joined.isoformat(),
            "is_active": user.is_active,
        },
        "membership_history": [
            {
                "from": change.from_level,
                "to": change.to_level,
                "reason": change.reason,
                "created_at": change.created_at.isoformat(),
            }
            for change in user.membership_changes.all()
        ],
        "account_requests": [
            {
                "type": item.request_type,
                "status": item.status,
                "requested_at": item.requested_at.isoformat(),
            }
            for item in user.account_requests.all()
        ],
    }
    response = JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    response["Content-Disposition"] = 'attachment; filename="sdzjoy-account-export.json"'
    response["Cache-Control"] = "no-store, private"
    return response


@require_POST
@verified_email_required
@reauthentication_required
def request_account_deletion(request):
    AccountRequest.objects.get_or_create(
        user=request.user,
        request_type=AccountRequest.RequestType.DELETE,
        status=AccountRequest.Status.PENDING,
        defaults={"note": request.POST.get("note", "").strip()[:1000]},
    )
    return redirect("account_center")


@require_POST
@verified_email_required
@reauthentication_required
def deactivate_account(request):
    user = request.user
    AccountRequest.objects.create(
        user=user,
        request_type=AccountRequest.RequestType.DEACTIVATE,
        status=AccountRequest.Status.COMPLETED,
        processed_at=timezone.now(),
        processed_by=user,
        resolution_note="用户完成强验证后自行停用。",
    )
    user.is_active = False
    user.save(update_fields=("is_active",))
    logout(request)
    return redirect("/")
