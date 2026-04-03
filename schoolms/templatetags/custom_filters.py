from django import template
import calendar

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
    if isinstance(photo, str) and photo.startswith(('http://', 'https://')):
        return photo
    # If it's an ImageField or file, call .url
    if hasattr(photo, 'url'):
        return photo.url
    # Otherwise return as-is (might be a URL string)
    return photo

@register.filter
def month_name(month_number):
    """Convert month number to month name."""
    if not month_number:
        return ""
    try:
        month = int(month_number)
        if 1 <= month <= 12:
            return calendar.month_name[month]
    except (ValueError, TypeError):
        pass
    return ""