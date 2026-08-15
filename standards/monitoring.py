import hashlib
import ipaddress
import json
from dataclasses import dataclass
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import CandidateChange, CheckBatch, MonitoringSource, SourceSnapshot, Standard

MAX_ITEMS_PER_FEED = 100


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: dict
    body: bytes


def candidate_fingerprint(*, external_key, change_type, proposed_data):
    canonical = json.dumps(
        {
            "external_key": external_key,
            "change_type": change_type,
            "proposed_data": proposed_data,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _validate_remote_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationError("检查来源必须是公开的 HTTP(S) 地址。")
    if parsed.username or parsed.password:
        raise ValidationError("检查来源不能在网址中携带账号凭据。")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValidationError("检查来源不能指向本机地址。")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise ValidationError("检查来源不能指向内网或保留地址。")


def _http_get(source):
    headers = {
        "Accept": "application/json",
        "User-Agent": "SDZJOY-Standards-Monthly-Checker/1.0",
    }
    if source.etag:
        headers["If-None-Match"] = source.etag
    if source.last_modified:
        headers["If-Modified-Since"] = source.last_modified
    _validate_remote_url(source.source_url)
    request = Request(source.source_url, headers=headers)  # noqa: S310 -- validated HTTP(S)
    try:
        with urlopen(request, timeout=source.timeout_seconds) as response:  # noqa: S310
            body = response.read(source.max_response_bytes + 1)
            return HTTPResult(response.status, dict(response.headers.items()), body)
    except HTTPError as exc:
        body = exc.read(source.max_response_bytes + 1)
        return HTTPResult(exc.code, dict(exc.headers.items()), body)
    except (TimeoutError, URLError) as exc:
        raise ValidationError("来源暂时无法访问，正式数据保持不变。") from exc


def _finish_batch(batch, *, status, message, candidate_count=0):
    batch.status = status
    batch.message = message[:1000]
    batch.candidate_count = candidate_count
    batch.finished_at = timezone.now()
    batch.save(
        update_fields=("status", "message", "candidate_count", "finished_at")
    )


def _schedule_next_check(source, now):
    source.last_checked_at = now
    source.next_check_at = now + timedelta(days=source.interval_days)


def _record_rate_limit(source, batch, headers, now):
    retry_after = headers.get("Retry-After", "")
    try:
        seconds = max(3600, min(int(retry_after), 7 * 24 * 3600))
    except (TypeError, ValueError):
        seconds = 24 * 3600
    source.next_allowed_at = now + timedelta(seconds=seconds)
    source.last_checked_at = now
    source.save(update_fields=("next_allowed_at", "last_checked_at", "updated_at"))
    _finish_batch(
        batch,
        status=CheckBatch.Status.RATE_LIMITED,
        message="来源返回限流信号，已停止本批次并进入退避。",
    )


def _validate_feed(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValidationError("增量清单必须是包含 items 数组的 JSON 对象。")
    items = payload["items"]
    if len(items) > MAX_ITEMS_PER_FEED:
        raise ValidationError("单次增量条目超过安全上限。")
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("增量条目必须是对象。")
        required = {"external_key", "change_type", "proposed_data"}
        if not required.issubset(item):
            raise ValidationError("增量条目缺少 external_key、change_type 或 proposed_data。")
        if item["change_type"] not in CandidateChange.ChangeType.values:
            raise ValidationError("增量条目包含未知变化类型。")
        if not isinstance(item["proposed_data"], dict):
            raise ValidationError("proposed_data 必须是对象。")
    return items


def run_source_check(*, source, trigger=CheckBatch.Trigger.MANUAL, fetcher=None):
    source = MonitoringSource.objects.get(pk=source.pk)
    now = timezone.now()
    if source.feed_format != MonitoringSource.FeedFormat.SDZJOY_JSON:
        raise ValidationError("该来源仅支持管理员手工创建候选。")
    if not source.automated_access_allowed or not source.access_reviewed_at:
        raise ValidationError("尚未确认该来源允许自动访问。")
    if source.next_allowed_at and source.next_allowed_at > now:
        raise ValidationError("该来源仍在退避期，本次未发出请求。")
    try:
        with transaction.atomic():
            batch = CheckBatch.objects.create(source=source, trigger=trigger)
    except IntegrityError as exc:
        raise ValidationError("该来源已有一个检查任务在运行。") from exc

    fetcher = fetcher or _http_get
    try:
        result = fetcher(source)
        batch.request_count = 1
        batch.save(update_fields=("request_count",))

        if result.status == 304:
            _schedule_next_check(source, now)
            source.next_allowed_at = None
            source.save(
                update_fields=(
                    "last_checked_at",
                    "next_check_at",
                    "next_allowed_at",
                    "updated_at",
                )
            )
            _finish_batch(
                batch,
                status=CheckBatch.Status.NO_CHANGE,
                message="来源内容未变化，复用了条件请求缓存。",
            )
            return batch
        if result.status == 429:
            _record_rate_limit(source, batch, result.headers, now)
            return batch
        if result.status != 200:
            raise ValidationError(f"来源返回 HTTP {result.status}，本批次已停止。")
        if len(result.body) > source.max_response_bytes:
            raise ValidationError("来源响应超过安全大小上限。")

        try:
            payload = json.loads(result.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("来源返回的不是有效 UTF-8 JSON。") from exc
        items = _validate_feed(payload)
        content_hash = hashlib.sha256(result.body).hexdigest()
        snapshot = SourceSnapshot.objects.create(
            source=source,
            batch=batch,
            source_url=source.source_url,
            response_status=result.status,
            etag=result.headers.get("ETag", "")[:300],
            last_modified=result.headers.get("Last-Modified", "")[:300],
            content_hash=content_hash,
            payload=payload,
        )

        created_count = 0
        for item in items:
            standard = None
            standard_slug = str(item.get("standard_slug", "")).strip()
            if standard_slug:
                standard = Standard.objects.filter(slug=standard_slug).first()
            fingerprint = candidate_fingerprint(
                external_key=str(item["external_key"]),
                change_type=item["change_type"],
                proposed_data=item["proposed_data"],
            )
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            _, created = CandidateChange.objects.get_or_create(
                source=source,
                fingerprint=fingerprint,
                defaults={
                    "snapshot": snapshot,
                    "standard": standard,
                    "external_key": str(item["external_key"])[:200],
                    "change_type": item["change_type"],
                    "proposed_data": item["proposed_data"],
                    "differences": item.get("differences", {}),
                    "evidence_title": str(evidence.get("title") or source.name)[:300],
                    "evidence_url": str(evidence.get("url") or source.source_url),
                },
            )
            created_count += int(created)

        _schedule_next_check(source, now)
        source.next_allowed_at = None
        source.etag = result.headers.get("ETag", "")[:300]
        source.last_modified = result.headers.get("Last-Modified", "")[:300]
        source.save(
            update_fields=(
                "last_checked_at",
                "next_check_at",
                "next_allowed_at",
                "etag",
                "last_modified",
                "updated_at",
            )
        )
        status = CheckBatch.Status.COMPLETED if created_count else CheckBatch.Status.NO_CHANGE
        message = (
            f"生成 {created_count} 条待人工审核候选。"
            if created_count
            else "内容已读取，但没有新的候选变化。"
        )
        _finish_batch(
            batch,
            status=status,
            message=message,
            candidate_count=created_count,
        )
        return batch
    except ValidationError as exc:
        _finish_batch(
            batch,
            status=CheckBatch.Status.FAILED,
            message="；".join(exc.messages),
        )
        return batch
    except Exception:
        _finish_batch(
            batch,
            status=CheckBatch.Status.FAILED,
            message="检查过程发生未预期异常；已停止，本批次未修改正式数据。",
        )
        return batch
