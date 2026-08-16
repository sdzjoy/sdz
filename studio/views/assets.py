from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from publishing.models import Asset
from publishing.uploads import ImageUploadError, asset_reference_map

from ..permissions import CONTENT_ROLES, studio_context, studio_role_required
from ..services.assets import soft_delete_asset, upload_image_asset


@require_http_methods(["GET", "POST"])
@studio_role_required(*CONTENT_ROLES)
def asset_library(request):
    if request.method == "POST":
        uploaded = request.FILES.get("image")
        if uploaded is None:
            messages.error(request, "请选择要上传的图片。")
        else:
            try:
                upload_image_asset(uploaded, actor=request.user)
            except ImageUploadError as error:
                messages.error(request, error.message)
            else:
                messages.success(request, "图片已安全上传。")
        return redirect("studio:assets")

    query = request.GET.get("q", "").strip()[:200]
    assets = Asset.objects.filter(kind=Asset.Kind.IMAGE, deleted_at__isnull=True)
    if query:
        assets = assets.filter(
            Q(title__icontains=query)
            | Q(original_name__icontains=query)
            | Q(alt_text__icontains=query)
        )
    assets = list(assets[:80])
    references = asset_reference_map(asset.pk for asset in assets)
    items = [
        {"asset": asset, "references": references[asset.pk]} for asset in assets
    ]
    context = studio_context(request.user)
    context.update(
        {
            "studio_section": "assets",
            "asset_items": items,
            "asset_query": query,
        }
    )
    return render(request, "studio/assets/list.html", context)


@require_POST
@studio_role_required(*CONTENT_ROLES)
def delete_asset(request, pk):
    asset = get_object_or_404(
        Asset.objects.filter(kind=Asset.Kind.IMAGE, deleted_at__isnull=True),
        pk=pk,
    )
    deleted, references = soft_delete_asset(asset, actor=request.user)
    if deleted is None:
        messages.error(request, f"图片仍有 {len(references)} 处引用，不能删除。")
    else:
        messages.success(request, "图片已移入素材回收状态。")
    return redirect("studio:assets")
