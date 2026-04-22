"""
QR Code template tags for Mastex SchoolOS
"""
from django import template
from core import qr_utils

register = template.Library()

@register.simple_tag
def generate_student_qr_base64(student):
    """Generate QR code for a student and return as base64."""
    return qr_utils.generate_student_qr_base64(student)


@register.simple_tag
def generate_staff_qr_base64(user):
    """Generate QR code for a staff member and return as base64."""
    return qr_utils.generate_staff_qr_base64(user)