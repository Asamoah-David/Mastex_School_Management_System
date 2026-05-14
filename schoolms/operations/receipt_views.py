"""Receipt views: HTML display + PDF download."""
import io
import logging
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect

logger = logging.getLogger(__name__)


def _get_school(request):
    school = getattr(request.user, "school", None)
    if school:
        return school
    if request.user.is_superuser or getattr(request.user, "is_super_admin", False):
        from schools.models import School
        sid = request.session.get("current_school_id")
        if sid:
            return School.objects.filter(pk=sid).first()
    return None


def _get_payment(pk, user, school):
    """Find payment across the live payment models: FeePayment, BusPayment,
    CanteenPayment, TextbookSale, HostelFee.

    Other model names that used to exist (StudentPayment / Payment) were
    removed; we no longer try them to avoid silent dead lookups.
    """
    from django.apps import apps

    candidates = (
        ("finance", "FeePayment"),
        ("operations", "CanteenPayment"),
        ("operations", "BusPayment"),
        ("operations", "TextbookSale"),
        ("operations", "HostelFee"),
    )
    for app_label, model_name in candidates:
        try:
            Model = apps.get_model(app_label, model_name)
        except Exception:
            continue
        obj = Model.objects.filter(pk=pk).first()
        if obj:
            return obj
    return None


def _user_can_view_receipt(user, payment) -> bool:
    """Authorise receipt access. Prevents IDOR — any logged-in user could
    previously fetch any other school's receipts by enumerating IDs.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, "is_super_admin", False):
        return True

    # Locate the student tied to the payment (varies per model).
    student = getattr(payment, "student", None)
    if student is None:
        # FeePayment links via .fee.student
        fee = getattr(payment, "fee", None)
        student = getattr(fee, "student", None)

    # Lazy-import to avoid circular at module load.
    try:
        from operations.payment_views import user_can_access_student_payment
        if student and user_can_access_student_payment(user, student):
            return True
    except Exception:
        pass

    # Fallback: school staff with finance permission viewing their own school.
    payment_school_id = getattr(payment, "school_id", None)
    if payment_school_id is None:
        fee = getattr(payment, "fee", None)
        payment_school_id = getattr(fee, "school_id", None)
    user_school_id = getattr(getattr(user, "school", None), "id", None)
    if payment_school_id and user_school_id and payment_school_id == user_school_id:
        try:
            from accounts.permissions import can_manage_finance, user_can_manage_school
            if can_manage_finance(user) or user_can_manage_school(user):
                return True
        except Exception:
            pass
    return False


@login_required
def receipt_view(request, payment_id):
    """HTML receipt page."""
    school = _get_school(request)
    payment = _get_payment(payment_id, request.user, school)
    if not payment:
        from django.http import Http404
        raise Http404("Payment not found")
    if not _user_can_view_receipt(request.user, payment):
        return HttpResponse("Forbidden", status=403)
    return render(request, "operations/receipt.html", {"payment": payment, "school": school})


@login_required
def receipt_pdf_view(request, payment_id):
    """Download PDF receipt."""
    school = _get_school(request)
    payment = _get_payment(payment_id, request.user, school)
    if not payment:
        return HttpResponse("Payment not found", status=404)
    if not _user_can_view_receipt(request.user, payment):
        return HttpResponse("Forbidden", status=403)

    try:
        pdf_bytes = _build_receipt_pdf(payment, school)
    except Exception as exc:
        logger.exception("Receipt PDF failed for payment %s: %s", payment_id, exc)
        return HttpResponse(f"PDF generation failed: {exc}", status=500, content_type="text/plain")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="receipt_{payment_id}.pdf"'
    return response


def _build_receipt_pdf(payment, school):
    """Build PDF bytes for a payment receipt."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A5,
                             rightMargin=1.5*cm, leftMargin=1.5*cm,
                             topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("N", parent=styles["Normal"], fontSize=9, leading=13)
    center = ParagraphStyle("C", parent=normal, alignment=TA_CENTER)
    heading = ParagraphStyle("H", parent=styles["Heading2"], fontSize=12,
                              textColor=colors.HexColor("#1e3a5f"), alignment=TA_CENTER)

    school_name = school.name if school else "School"
    elements = []
    elements.append(Paragraph(school_name.upper(), heading))
    if school and school.address:
        elements.append(Paragraph(school.address, center))
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1e3a5f")))
    elements.append(Paragraph("OFFICIAL RECEIPT", ParagraphStyle("RC", parent=heading, fontSize=11,
                               spaceAfter=4, spaceBefore=4)))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    elements.append(Spacer(1, 8))

    # Details grid
    currency = school.currency if school and hasattr(school, "currency") and school.currency else "GHS"
    student_name = ""
    if hasattr(payment, "student") and payment.student:
        student_name = payment.student.user.get_full_name() or str(payment.student)

    fee_type = ""
    if hasattr(payment, "get_fee_type_display"):
        try:
            fee_type = payment.get_fee_type_display()
        except Exception:
            fee_type = getattr(payment, "fee_type", "")

    # Convert date to datetime if needed to avoid format errors
    from datetime import datetime, time
    paid_at = getattr(payment, "paid_at", None) or getattr(payment, "created_at", None) or getattr(payment, "payment_date", None) or getattr(payment, "sale_date", None)
    
    if paid_at and not isinstance(paid_at, datetime):
        paid_at = datetime.combine(paid_at, time.min)
        
    paid_at_str = paid_at.strftime("%d %b %Y %H:%M") if paid_at else "N/A"

    info = [
        ["Receipt No.:", f"#{payment.id}", "Date:", paid_at_str],
        ["Student:", student_name, "Fee Type:", fee_type],
    ]
    info_table = Table(info, colWidths=[2.5*cm, 4*cm, 2.5*cm, 4*cm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#1e3a5f")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f7f9fc"), colors.white]),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 10))

    # Amount
    amount = float(getattr(payment, "amount", 0) or 0)
    amount_data = [
        [Paragraph("<b>Description</b>", normal), Paragraph("<b>Amount</b>", normal)],
        [Paragraph(fee_type or "Payment", normal), Paragraph(f"<b>{currency} {amount:,.2f}</b>",
              ParagraphStyle("Amt", parent=normal, fontSize=11, textColor=colors.HexColor("#1e3a5f")))],
    ]
    amount_table = Table(amount_data, colWidths=[8*cm, 5*cm])
    amount_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f4f8")]),
    ]))
    elements.append(amount_table)
    elements.append(Spacer(1, 10))

    # Status
    status = getattr(payment, "status", "paid")
    status_color = colors.HexColor("#16a34a") if status == "paid" else colors.HexColor("#ca8a04")
    status_text = "PAYMENT CONFIRMED" if status == "paid" else "PENDING"
    elements.append(Paragraph(f"✓ {status_text}", ParagraphStyle(
        "ST", parent=center, fontSize=11, textColor=status_color, spaceBefore=4
    )))

    elements.append(Spacer(1, 14))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    from datetime import date
    elements.append(Paragraph(
        f"Thank you for your payment. Official receipt from {school_name}. "
        f"Generated {date.today().strftime('%d %b %Y')} by Mastex SchoolOS.",
        ParagraphStyle("FT", parent=center, fontSize=7.5, textColor=colors.HexColor("#aaaaaa"), spaceBefore=4)
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
