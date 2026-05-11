# STUDENT ID CARD PDF FIX - Circular Clipping

@login_required
def id_card_pdf(request, pk):
    """Generate PDF ID card for student."""
    from accounts.permissions import user_can_manage_school
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from io import BytesIO
    from reportlab.lib.path import Path
    from core.qr_utils import generate_student_qr_data, generate_qr_code_bytes
    
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    id_card = get_object_or_404(StudentIDCard, pk=pk, school=school)
    student = id_card.student
    
    # Create PDF
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # Card dimensions (standard ID card ratio 3.375" x 2.125")
    card_width = 243  # 3.375 inch in points
    card_height = 153  # 2.125 inch in points
    card_x = (width - card_width) / 2
    card_y = (height - card_height) / 2
    
    # Card background
    c.setFillColor(colors.white)
    c.rect(card_x, card_y, card_width, card_height, fill=1)
    
    # Card border
    c.setStrokeColor(colors.darkblue)
    c.setLineWidth(2)
    c.rect(card_x, card_y, card_width, card_height)
    
    # Inner border
    c.setStrokeColor(colors.gold)
    c.setLineWidth(1)
    c.rect(card_x + 5, card_y + 5, card_width - 10, card_height - 10)
    
    # School name
    c.setFillColor(colors.darkblue)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width/2, card_y + card_height - 25, school.name)
    
    # Student photo - positioned on LEFT side
    photo = None
    
    # Try multiple sources for the photo - use helper that handles both local and cloud URLs
    # Source 1: ID card uploaded photo (could be local path or Supabase URL)
    if id_card.photo:
        try:
            photo = _get_image_reader_for_pdf(id_card.photo)
        except Exception:
            logger.warning("Error reading id_card.photo for student ID PDF", exc_info=True)
            photo = None
    
    # Source 2: Student user's profile_photo (could be local path or Supabase URL)
    if not photo and student and student.user:
        try:
            user = student.user
            if hasattr(user, 'profile_photo') and user.profile_photo:
                photo = _get_image_reader_for_pdf(user.profile_photo)
        except Exception:
            logger.warning("Error reading student profile_photo for ID PDF", exc_info=True)
            photo = None
    
    # Draw student photo - LEFT side of card
    photo_x = card_x + 15
    photo_y = card_y + card_height - 85
    photo_size = 55
    
    if photo:
        c.saveState()
        # Create circular clipping path
        circle = Path()
        circle.addCircle(photo_x + 27.5, photo_y + 27.5, 27.5)
        c.clipPath(circle, stroke=0, fill=0)
        c.drawImage(photo, photo_x, photo_y, width=photo_size, height=photo_size, preserveAspectRatio=True, mask='auto')
        c.restoreState()
    else:
        c.setStrokeColor(colors.lightgrey)
        c.setLineWidth(1)
        c.setFillColor(colors.lightgrey)
        c.circle(photo_x + 27.5, photo_y + 27.5, 27.5, fill=1, stroke=1)
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.darkgrey)
        c.drawCentredString(photo_x + 27.5, photo_y + 22, "PHOTO")
    
    # "STUDENT ID CARD" text - positioned on RIGHT side (next to photo)
    c.setFillColor(colors.gold)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(card_x + 85, card_y + card_height - 40, "STUDENT ID CARD")
    
    # Student info section - LEFT BOTTOM corner
    info_x = card_x + 15
    info_y = card_y + 40
    
    # Student name
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    student_name = student.user.get_full_name() if student and student.user else "Student"
    c.drawString(info_x, info_y + 28, student_name.upper())
    
    # Class
    c.setFont("Helvetica", 8)
    c.drawString(info_x, info_y + 16, f"Class: {student.class_name or 'N/A'}")
    
    # Card number
    c.setFont("Helvetica", 8)
    c.drawString(info_x, info_y + 4, f"Card No: {id_card.card_number}")
    
    # Issue date
    c.setFont("Helvetica", 8)
    c.drawString(info_x, info_y - 8, f"Issue: {id_card.issue_date|date:'M d, Y'}")
    
    # Expiry date
    c.setFont("Helvetica", 8)
    c.drawString(info_x, info_y - 20, f"Expiry: {id_card.expiry_date|date:'M d, Y'|default:'N/A'}")
    
    # QR Code
    qr_data = generate_student_qr_data(student, id_card)
    qr_code_bytes = generate_qr_code_bytes(qr_data, size=60)
    qr_reader = ImageReader(BytesIO(qr_code_bytes))
    qr_size = 40
    qr_x = card_x + card_width - qr_size - 20
    qr_y = card_y + card_height - qr_size - 20
    c.drawImage(qr_reader.getImage(), qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True, mask='auto')
    
    c.showPage()
    c.save()
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="student_id_card_{id_card.card_number}.pdf"'
    return response
