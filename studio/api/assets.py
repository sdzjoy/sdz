from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from publishing.models import Asset
from publishing.uploads import ImageUploadError

from ..permissions import CONTENT_ROLES, studio_role_required
from ..services.assets import soft_delete_asset, upload_image_asset


def _asset_json(asset):
    return {
        "id": asset.pk,
        "url": asset.file.url,
        "alt": asset.alt_text,
        "title": asset.title,
        "width": asset.width,
        "height": asset.height,
        "mime_type": asset.mime_type,
        "byte_size": asset.byte_size,
    }


@require_POST
@studio_role_required(*CONTENT_ROLES)
def upload_image(request):
    uploaded = request.FILES.get("image")
    if uploaded is None:
        return JsonResponse(
            {"ok": False, "code": "missing_image", "message": "请选择图片。"},
            status=400,
        )
    try:
        asset = upload_image_asset(uploaded, actor=request.user)
    except ImageUploadError as error:
        return JsonResponse(
            {"ok": False, "code": error.code, "message": error.message},
            status=400,
        )
    return JsonResponse({"ok": True, "asset": _asset_json(asset)}, status=201)


@require_POST
@studio_role_required(*CONTENT_ROLES)
def delete_image(request, pk):
    asset = get_object_or_404(
        Asset.objects.filter(kind=Asset.Kind.IMAGE, deleted_at__isnull=True),
        pk=pk,
    )
    deleted, references = soft_delete_asset(asset, actor=request.user)
    if deleted is None:
        return JsonResponse(
            {
                "ok": False,
                "code": "asset_in_use",
                "message": "这张图片仍在使用，不能删除。",
                "references": references,
            },
            status=409,
        )
    return JsonResponse({"ok": True})
