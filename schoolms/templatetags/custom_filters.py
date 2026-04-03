from django import template\nimport calendar

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
  
@register.filter  
def month_name(value):  
    month_map = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'}  
