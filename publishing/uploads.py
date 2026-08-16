import hashlib
import io
import warnings
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from publishing.models import Asset, ContentEntry, SiteProfile

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_WIDTH = 12_000
MAX_IMAGE_HEIGHT = 12_000
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_IMAGE_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}


class ImageUploadError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreparedImage:
    content: bytes
    extension: str
    mime_type: str
    width: int
    height: int
    original_name: str
    sha256: str


def _safe_original_name(value):
    name = Path(value or "image").name.strip() or "image"
    return name[:255]


def _output_mode(image, image_format):
    if image_format == "JPEG":
        return image.convert("RGB")
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        return image.convert("RGBA")
    return image.convert("RGB")


def prepare_image(uploaded) -> PreparedImage:
    original_name = _safe_original_name(getattr(uploaded, "name", "image"))
    size = getattr(uploaded, "size", None)
    if size is not None and size > MAX_IMAGE_BYTES:
        raise ImageUploadError("file_too_large", "图片不能超过 8 MB。")
    raw = uploaded.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageUploadError("file_too_large", "图片不能超过 8 MB。")
    if not raw:
        raise ImageUploadError("empty_file", "图片文件是空的。")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                image_format = probe.format
                probe.verify()
            with Image.open(io.BytesIO(raw)) as source:
                if image_format not in ALLOWED_IMAGE_FORMATS:
                    raise ImageUploadError(
                        "unsupported_format",
                        "只支持 JPEG、PNG 和 WebP 图片。",
                    )
                if getattr(source, "n_frames", 1) != 1:
                    raise ImageUploadError("animated_image", "暂不支持动画图片。")
                width, height = source.size
                if (
                    width < 1
                    or height < 1
                    or width > MAX_IMAGE_WIDTH
                    or height > MAX_IMAGE_HEIGHT
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    raise ImageUploadError(
                        "image_dimensions",
                        "图片尺寸过大，最长边不能超过 12000 像素，总像素不能超过 4000 万。",
                    )
                normalized = _output_mode(ImageOps.exif_transpose(source), image_format)
                output = io.BytesIO()
                if image_format == "JPEG":
                    normalized.save(output, format="JPEG", quality=90, optimize=True)
                elif image_format == "PNG":
                    normalized.save(output, format="PNG", optimize=True)
                else:
                    normalized.save(output, format="WEBP", quality=90, method=6)
    except ImageUploadError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ImageUploadError("decompression_bomb", "图片像素量异常，已拒绝上传。") from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise ImageUploadError(
            "invalid_image",
            "文件不是有效的 JPEG、PNG 或 WebP 图片。",
        ) from error

    content = output.getvalue()
    extension, mime_type = ALLOWED_IMAGE_FORMATS[image_format]
    return PreparedImage(
        content=content,
        extension=extension,
        mime_type=mime_type,
        width=width,
        height=height,
        original_name=original_name,
        sha256=hashlib.sha256(content).hexdigest(),
    )


def create_image_asset(uploaded, *, uploaded_by, after_save=None):
    prepared = prepare_image(uploaded)
    title = Path(prepared.original_name).stem[:200]
    asset = Asset(
        kind=Asset.Kind.IMAGE,
        original_name=prepared.original_name,
        title=title,
        alt_text=title,
        mime_type=prepared.mime_type,
        byte_size=len(prepared.content),
        width=prepared.width,
        height=prepared.height,
        sha256=prepared.sha256,
        uploaded_by=uploaded_by,
    )
    stored_name = ""
    try:
        with transaction.atomic():
            asset.file.save(
                f"{uuid4().hex}{prepared.extension}",
                ContentFile(prepared.content),
                save=False,
            )
            stored_name = asset.file.name
            asset.save()
            if after_save:
                after_save(asset)
    except Exception:
        if stored_name:
            asset.file.storage.delete(stored_name)
        raise
    return asset


def document_asset_ids(value):
    found = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get("type") == "image":
                asset_id = item.get("attrs", {}).get("assetId")
                if isinstance(asset_id, int) and not isinstance(asset_id, bool):
                    found.add(asset_id)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def document_asset_references(value):
    references = {}
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get("type") == "image":
                attrs = item.get("attrs", {})
                asset_id = attrs.get("assetId")
                if isinstance(asset_id, int) and not isinstance(asset_id, bool):
                    references.setdefault(asset_id, set()).add(attrs.get("src"))
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return references


def asset_reference_map(asset_ids):
    asset_ids = set(asset_ids)
    reference_map = {asset_id: [] for asset_id in asset_ids}
    seen = {asset_id: set() for asset_id in asset_ids}
    contents = ContentEntry.objects.all().only(
        "pk",
        "kind",
        "title",
        "cover_asset_id",
        "published_cover_asset_id",
        "body_json",
        "published_body_json",
    )
    for content in contents.iterator():
        draft_ids = document_asset_ids(content.body_json)
        published_ids = document_asset_ids(content.published_body_json)
        for asset_id in asset_ids:
            locations = []
            if content.cover_asset_id == asset_id:
                locations.append("草稿封面")
            if content.published_cover_asset_id == asset_id:
                locations.append("线上封面")
            if asset_id in draft_ids:
                locations.append("草稿正文")
            if asset_id in published_ids:
                locations.append("线上正文")
            if locations and content.pk not in seen[asset_id]:
                seen[asset_id].add(content.pk)
                reference_map[asset_id].append(
                    {
                        "type": content.get_kind_display(),
                        "id": content.pk,
                        "label": content.title,
                        "locations": locations,
                    }
                )
    default_ids = set(
        SiteProfile.objects.filter(default_cover_id__in=asset_ids).values_list(
            "default_cover_id",
            flat=True,
        )
    )
    for asset_id in default_ids:
        reference_map[asset_id].append(
            {
                "type": "网站设置",
                "id": "site-profile",
                "label": "默认封面",
                "locations": ["默认封面"],
            }
        )
    return reference_map


def find_asset_references(asset):
    return asset_reference_map({asset.pk})[asset.pk]
