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


@register.filter
def text_to_words(amount):
    """
    Convert a number to its words representation.
    Example: 100 -> "One Hundred", 1500 -> "One Thousand Five Hundred"
    """
    if not amount:
        return ""
    
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return str(amount)
    
    # If amount is small, just return the number as words
    if amount < 100:
        return str(int(amount))
    
    # For larger amounts, use a simpler representation
    num = int(amount)
    
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    
    def convert_hundreds(n):
        if n < 20:
            return ones[n]
        elif n < 100:
            return tens[n // 10] + ("" if n % 10 == 0 else " " + ones[n % 10])
        else:
            return ones[n // 100] + " Hundred" + ("" if n % 100 == 0 else " " + convert_hundreds(n % 100))
    
    if num < 1000:
        return convert_hundreds(num)
    elif num < 1000000:
        return convert_hundreds(num // 1000) + " Thousand" + ("" if num % 1000 == 0 else " " + convert_hundreds(num % 1000))
    else:
        # For very large amounts, just return the number
        return str(int(amount))
