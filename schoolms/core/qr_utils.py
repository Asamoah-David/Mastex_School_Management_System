"""
QR Code utilities for Mastex SchoolOS
Generates QR codes for student attendance and ID cards
"""

import qrcode
import io
import base64
from PIL import Image


def generate_student_qr_data(student):
    """
    Generate QR code data string for a student.
    Contains student ID and admission number for quick lookup.
    """
    return f"MASEXTICKET:{student.id}:{student.admission_number}"


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


def validate_qr_data(data):
    """
    Validate and parse QR code data.
    
    Args:
        data: QR code string data
    
    Returns:
        Dict with validation result and student info
    """
    if not data:
        return {'valid': False, 'error': 'Empty data'}
    
    if not data.startswith('MASEXTICKET:'):
        return {'valid': False, 'error': 'Invalid QR code format'}
    
    try:
        parts = data.split(':')
        if len(parts) != 3:
            return {'valid': False, 'error': 'Invalid QR code structure'}
        
        _, student_id, admission_number = parts
        
        return {
            'valid': True,
            'student_id': int(student_id),
            'admission_number': admission_number
        }
    except (ValueError, IndexError) as e:
        return {'valid': False, 'error': str(e)}


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
