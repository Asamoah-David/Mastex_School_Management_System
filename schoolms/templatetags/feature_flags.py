from django import template

from schools.features import is_feature_enabled

register = template.Library()


@register.simple_tag(takes_context=True)
def feature_enabled(context, key: str) -> bool:
    request = context.get("request")
    if not request:
        return True
    return is_feature_enabled(request, key)

