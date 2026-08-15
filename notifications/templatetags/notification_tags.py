from django import template

from notifications.models import Favorite, ItemSubscription

register = template.Library()


@register.inclusion_tag("notifications/item_actions.html", takes_context=True)
def item_actions(context, item_type, object_id):
    request = context["request"]
    user = request.user
    object_id = str(object_id)
    favorite = subscribed = False
    if user.is_authenticated:
        favorite = Favorite.objects.filter(
            user=user, item_type=item_type, object_id=object_id
        ).exists()
        subscribed = ItemSubscription.objects.filter(
            user=user, item_type=item_type, object_id=object_id
        ).exists()
    return {
        "request": request,
        "item_type": item_type,
        "object_id": object_id,
        "favorite": favorite,
        "subscribed": subscribed,
    }

