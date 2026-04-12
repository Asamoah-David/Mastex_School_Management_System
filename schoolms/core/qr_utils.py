"""
QR Code utilities for Mastex SchoolOS
Generates QR codes for student attendance and ID cards
"""

import base64
import io

import qrcode
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from PIL import Image

_QR_STUDENT_SALT = "mastex.qr.student.v1"


def generate_student_qr_data(student):
    """
    Time-limited signed payload (replay-resistant vs static IDs).
    Legacy scanners still accept plain MASEXTICKET:id:adm format.
    """
    signer = TimestampSigner(salt=_QR_STUDENT_SALT)
    payload = f"{student.id}:{student.admission_number}"
    token = signer.sign(payload)
    return f"MASEXTICKET:v2:{token}"


def generate_qr_code_base64(data, box_size=10, border=2):
    """
    Generate a QR code image and return as base64 string.
    
    Args:
        data: String data to encode in QR code
        box_size: Size of each QR code box (pixels)
        border: Border size (boxes)
    
    Returns:
        Base64 encoded PNG image string
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return img_base64


def generate_qr_code_bytes(data, box_size=10, border=2):
    """
    Generate a QR code image and return as bytes.
    
    Args:
        data: String data to encode in QR code
        box_size: Size of each QR code box (pixels)
        border: Border size (boxes)
    
    Returns:
        PNG image bytes
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


def validate_qr_data(data, *, max_age_seconds: int = 90 * 24 * 3600):
    """
    Validate and parse QR code data (signed v2 or legacy v1).
    """
    if not data:
        return {"valid": False, "error": "Empty data"}

    if not data.startswith("MASEXTICKET:"):
        return {"valid": False, "error": "Invalid QR code format"}

    if data.startswith("MASEXTICKET:v2:"):
        signer = TimestampSigner(salt=_QR_STUDENT_SALT)
        raw = data[len("MASEXTICKET:v2:") :]
        try:
            unsigned = signer.unsign(raw, max_age=max_age_seconds)
            student_id_s, admission_number = unsigned.split(":", 1)
            return {
                "valid": True,
                "student_id": int(student_id_s),
                "admission_number": admission_number,
            }
        except SignatureExpired:
            return {"valid": False, "error": "QR code has expired; print a new card or refresh the code."}
        except (BadSignature, ValueError, IndexError) as e:
            return {"valid": False, "error": str(e)}

    try:
        parts = data.split(":")
        if len(parts) != 3:
            return {"valid": False, "error": "Invalid QR code structure"}

        _, student_id, admission_number = parts

        return {
            "valid": True,
            "student_id": int(student_id),
            "admission_number": admission_number,
            "legacy": True,
        }
    except (ValueError, IndexError) as e:
        return {"valid": False, "error": str(e)}


def generate_student_qr_base64(student):
    """
    Generate QR code for a student and return as base64.
    
    Args:
        student: Student model instance
    
    Returns:
        Base64 encoded PNG image string
    """
    data = generate_student_qr_data(student)
    return generate_qr_code_base64(data)


def generate_staff_qr_data(user):
    """
    Generate QR code data string for staff/teachers.
    Contains user ID and staff ID for quick lookup.
    """
    return f"MASEXTICKET:STAFF:{user.id}:{user.username}"


def generate_staff_qr_base64(user):
    """
    Generate QR code for a staff member and return as base64.
    
    Args:
        user: User model instance (staff/teacher)
    
    Returns:
        Base64 encoded PNG image string
    """
    data = generate_staff_qr_data(user)
    return generate_qr_code_base64(data)


def validate_staff_qr_data(data):
    """
    Validate and parse staff QR code data.
    
    Args:
        data: QR code string data
    
    Returns:
        Dict with validation result and staff info
    """
    if not data:
        return {'valid': False, 'error': 'Empty data'}
    
    if not data.startswith('MASEXTICKET:STAFF:'):
        return {'valid': False, 'error': 'Invalid QR code format'}
    
    try:
        parts = data.split(':')
        if len(parts) != 4:
            return {'valid': False, 'error': 'Invalid QR code structure'}
        
        _, _, staff_id, username = parts
        
        return {
            'valid': True,
            'staff_id': int(staff_id),
            'username': username
        }
    except (ValueError, IndexError) as e:
        return {'valid': False, 'error': str(e)}
