from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from standards.models import TaxonomyTerm

from .forms import NotificationPreferenceForm
from .models import Favorite, ItemSubscription, NotificationPreference, TopicSubscription
from .references import resolve_reference, resolved_items


@login_required
def inbox(request):
    notifications = request.user.notifications.select_related("event")[:100]
    return render(request, "notifications/inbox.html", {"notifications": notifications})


@require_POST
@login_required
def mark_read(request, notification_id):
    notification = request.user.notifications.filter(pk=notification_id).first()
    if not notification:
        raise Http404
    if not notification.read_at:
        notification.read_at = timezone.now()
        notification.save(update_fields=("read_at",))
    return redirect(notification.url or "notifications:inbox")


@login_required
def saved_items(request):
    taxonomies = TaxonomyTerm.objects.all()
    subscribed_topics = set(
        request.user.topic_subscriptions.values_list("taxonomy_id", flat=True)
    )
    return render(
        request,
        "notifications/saved_items.html",
        {
            "favorites": resolved_items(request.user.favorites.all(), request.user),
            "subscriptions": resolved_items(
                request.user.item_subscriptions.all(), request.user
            ),
            "taxonomies": taxonomies,
            "subscribed_topics": subscribed_topics,
        },
    )


@require_POST
@login_required
def toggle_item(request, mode):
    item_type = request.POST.get("item_type", "")[:16]
    object_id = request.POST.get("object_id", "")[:64]
    if not resolve_reference(item_type, object_id, request.user):
        raise PermissionDenied
    model = Favorite if mode == "favorite" else ItemSubscription
    saved = model.objects.filter(
        user=request.user, item_type=item_type, object_id=object_id
    ).first()
    if saved:
        saved.delete()
    else:
        model.objects.create(user=request.user, item_type=item_type, object_id=object_id)
    return redirect(request.POST.get("next") or "notifications:saved_items")


@require_POST
@login_required
def toggle_topic(request, taxonomy_id):
    taxonomy = TaxonomyTerm.objects.filter(pk=taxonomy_id).first()
    if not taxonomy:
        raise Http404
    subscription = TopicSubscription.objects.filter(
        user=request.user, taxonomy=taxonomy
    ).first()
    if subscription:
        subscription.delete()
    else:
        TopicSubscription.objects.create(user=request.user, taxonomy=taxonomy)
    return redirect("notifications:saved_items")


@login_required
def preferences(request):
    preference, _ = NotificationPreference.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = NotificationPreferenceForm(request.POST, instance=preference)
        if form.is_valid():
            form.save()
            return redirect("notifications:preferences")
    else:
        form = NotificationPreferenceForm(instance=preference)
    return render(request, "notifications/preferences.html", {"form": form})
