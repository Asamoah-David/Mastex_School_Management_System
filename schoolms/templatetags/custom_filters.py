from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def get_photo_url(photo):
    """
    Get the URL for a photo field.
    Handles both ImageField (which needs .url) and URLField (which is already a URL).
    """
    if not photo:
        return None
    # If it's already a full URL (starts with http), return as-is
    if isinstance(photo, str) and photo.startswith('http'):
        return photo
    # Otherwise it's an ImageField and needs .url
    try:
        return photo.url
    except (AttributeError, ValueError):
        return None
